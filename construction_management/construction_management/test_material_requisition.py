# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from construction_management.construction_management.material_request import (
	get_material_requisition_list,
	get_project_material_requests,
	validate_construction_material_request,
)


class TestMaterialRequisition(FrappeTestCase):
	"""Tests for construction Material Request extensions, APIs, and permissions."""

	def _get_or_create_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if company:
			return company
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": "Test Construction Co",
				"abbr": "TCC",
				"default_currency": "INR",
				"country": "India",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _get_or_create_warehouse(self, company):
		warehouse = frappe.db.get_value(
			"Warehouse", {"company": company, "is_group": 0}, "name"
		)
		if warehouse:
			return warehouse
		doc = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"Site Store {frappe.generate_hash(length=5)}",
				"company": company,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _get_or_create_item(self):
		item = frappe.db.get_value(
			"Item", {"is_stock_item": 1, "disabled": 0}, "name"
		)
		if item:
			return item
		uom = frappe.db.get_value("UOM", {"name": "Nos"}, "name") or "Unit"
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"CM-MAT-{frappe.generate_hash(length=6)}",
				"item_name": "Test Cement Bag",
				"item_group": item_group,
				"stock_uom": uom,
				"is_stock_item": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _create_project(self, suffix, company=None):
		doc = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Test MR Project {suffix}",
				"company": company or self._get_or_create_company(),
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _create_task(self, subject, project=None):
		doc = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _create_dpr(self, project):
		doc = frappe.get_doc(
			{
				"doctype": "Daily Progress Report",
				"project": project,
				"report_date": nowdate(),
				"work_completed": "Excavation and footing reinforcement.",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _create_user_with_role(self, role):
		email = f"mr_{role.lower().replace(' ', '_')}_{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "MR",
				"last_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		)
		user.insert(ignore_permissions=True)
		return user.name

	def _make_mr(self, **kwargs):
		company = self._get_or_create_company()
		warehouse = self._get_or_create_warehouse(company)
		item = self._get_or_create_item()
		schedule_date = add_days(nowdate(), 3)

		data = {
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": company,
			"transaction_date": nowdate(),
			"schedule_date": schedule_date,
			"items": [
				{
					"item_code": item,
					"qty": 10,
					"schedule_date": schedule_date,
					"warehouse": warehouse,
				}
			],
		}
		data.update(kwargs)
		return frappe.get_doc(data)

	def _require_migrated_fields(self):
		if not frappe.db.has_column("Material Request", "custom_project"):
			self.skipTest(
				"Requires `bench --site dev.localhost migrate` to install Material Request Custom Fields and Custom DocPerm fixtures."
			)

	def test_construction_mr_creation_and_project_propagation(self):
		project = self._create_project(frappe.generate_hash(length=6))
		task = self._create_task("Foundation Concrete", project=project.name)
		mr = self._make_mr(
			custom_project=project.name,
			custom_task=task.name,
			custom_site_location="Block A",
			custom_priority="High",
		)
		mr.insert()

		self.assertEqual(mr.custom_project, project.name)
		self.assertEqual(mr.items[0].project, project.name)
		self.assertEqual(mr.custom_requested_by, frappe.session.user)

	def test_task_wrong_project_rejected(self):
		project_a = self._create_project(f"A-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"B-{frappe.generate_hash(length=5)}")
		task_b = self._create_task("Other Project Task", project=project_b.name)

		mr = self._make_mr(custom_project=project_a.name, custom_task=task_b.name)
		self.assertRaises(frappe.ValidationError, mr.insert)

	def test_child_item_project_mismatch_rejected(self):
		project_a = self._create_project(f"A-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"B-{frappe.generate_hash(length=5)}")
		mr = self._make_mr(custom_project=project_a.name)
		mr.items[0].project = project_b.name

		self.assertRaises(frappe.ValidationError, mr.insert)

	def test_missing_project_with_selected_task_rejected(self):
		project = self._create_project(frappe.generate_hash(length=6))
		task = self._create_task("Site Clearing", project=project.name)
		mr = self._make_mr(custom_task=task.name)

		self.assertRaises(frappe.ValidationError, mr.insert)

	def test_dpr_wrong_project_rejected(self):
		project_a = self._create_project(f"A-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"B-{frappe.generate_hash(length=5)}")
		dpr_b = self._create_dpr(project_b.name)

		mr = self._make_mr(custom_project=project_a.name, custom_dpr=dpr_b.name)
		self.assertRaises(frappe.ValidationError, mr.insert)

	def test_custom_requested_by_set_server_side_and_validated(self):
		project = self._create_project(frappe.generate_hash(length=6))
		mr = self._make_mr(custom_project=project.name)
		validate_construction_material_request(mr)
		self.assertEqual(mr.get("custom_requested_by"), frappe.session.user)

		mr_invalid = self._make_mr(
			custom_project=project.name,
			custom_requested_by="nonexistent_user_12345@example.com",
		)
		self.assertRaises(frappe.ValidationError, validate_construction_material_request, mr_invalid)

	def test_standard_non_construction_mr_works(self):
		mr = self._make_mr()
		mr.insert()
		mr.submit()

		self.assertEqual(mr.docstatus, 1)
		self.assertIsNone(mr.items[0].project)

	def test_list_api_filters_search_and_pagination(self):
		self._require_migrated_fields()

		project = self._create_project(frappe.generate_hash(length=6))
		mr_1 = self._make_mr(
			custom_project=project.name,
			custom_site_location="North Tower",
			custom_priority="Urgent",
			transaction_date="2026-11-10",
		)
		mr_1.insert()
		mr_1.submit()

		mr_2 = self._make_mr(
			custom_project=project.name,
			custom_site_location="South Gate",
			custom_priority="Low",
			transaction_date="2026-11-14",
		)
		mr_2.insert()

		filtered = get_material_requisition_list(
			filters={
				"project": project.name,
				"priority": "Urgent",
				"from_date": "2026-11-09",
				"to_date": "2026-11-12",
			}
		)
		self.assertEqual(filtered["total"], 1)
		self.assertEqual(filtered["records"][0]["name"], mr_1.name)

		searched = get_material_requisition_list(search="North Tower")
		self.assertEqual(searched["total"], 1)
		self.assertEqual(searched["records"][0]["name"], mr_1.name)

		page_1 = get_material_requisition_list(filters={"project": project.name}, start=0, page_length=1)
		page_2 = get_material_requisition_list(filters={"project": project.name}, start=1, page_length=1)
		self.assertEqual(page_1["total"], 2)
		self.assertEqual(len(page_1["records"]), 1)
		self.assertEqual(len(page_2["records"]), 1)
		self.assertNotEqual(page_1["records"][0]["name"], page_2["records"][0]["name"])

	def test_project_mapping_and_unmapped_returns_empty(self):
		self._require_migrated_fields()

		project = self._create_project(frappe.generate_hash(length=6))
		mr = self._make_mr(custom_project=project.name)
		mr.insert()

		mapped = get_project_material_requests(project_name=project.project_name)
		self.assertEqual(mapped["mapped_project"], project.name)
		self.assertEqual(len(mapped["material_requests"]), 1)
		self.assertEqual(mapped["material_requests"][0]["name"], mr.name)

		unmapped = get_project_material_requests(
			project_name="Nonexistent Sample Project XYZ", project_code="PRJ-999"
		)
		self.assertIsNone(unmapped["mapped_project"])
		self.assertEqual(unmapped["material_requests"], [])

	def test_role_permissions_and_user_permission_scoping(self):
		self._require_migrated_fields()

		project_a = self._create_project(f"PA-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"PB-{frappe.generate_hash(length=5)}")

		mr_a = self._make_mr(custom_project=project_a.name)
		mr_a.insert()
		mr_b = self._make_mr(custom_project=project_b.name)
		mr_b.insert()

		projects_user = self._create_user_with_role("Projects User")
		projects_manager = self._create_user_with_role("Projects Manager")
		self.addCleanup(frappe.set_user, "Administrator")

		# Projects User can create and submit, but cannot delete, cancel, or amend
		frappe.set_user(projects_user)
		self.assertTrue(frappe.has_permission("Material Request", "create", user=projects_user))
		self.assertTrue(frappe.has_permission("Material Request", "submit", user=projects_user))
		self.assertFalse(frappe.has_permission("Material Request", "delete", user=projects_user))
		self.assertFalse(frappe.has_permission("Material Request", "cancel", user=projects_user))
		self.assertFalse(frappe.has_permission("Material Request", "amend", user=projects_user))

		# Neither role gets write/create/delete on Item master data
		self.assertTrue(frappe.has_permission("Item", "read", user=projects_user))
		self.assertFalse(frappe.has_permission("Item", "write", user=projects_user))
		self.assertFalse(frappe.has_permission("Item", "create", user=projects_user))
		self.assertFalse(frappe.has_permission("Item", "delete", user=projects_user))

		mr_user = self._make_mr(custom_project=project_a.name)
		mr_user.insert()
		mr_user.submit()
		self.assertEqual(mr_user.docstatus, 1)

		# Without User Permission scoping, Projects User sees all Material Requests
		unscoped = get_material_requisition_list()
		unscoped_names = {r["name"] for r in unscoped["records"]}
		self.assertIn(mr_a.name, unscoped_names)
		self.assertIn(mr_b.name, unscoped_names)

		# With User Permission on Project, get_material_requisition_list respects Project access
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": projects_user,
				"allow": "Project",
				"for_value": project_a.name,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(projects_user)
		scoped = get_material_requisition_list()
		scoped_names = {r["name"] for r in scoped["records"]}
		self.assertIn(mr_a.name, scoped_names)
		self.assertNotIn(mr_b.name, scoped_names)

		# Projects Manager can create, submit, and cancel Material Request, with read-only Item access
		frappe.set_user(projects_manager)
		self.assertTrue(frappe.has_permission("Material Request", "cancel", user=projects_manager))
		self.assertTrue(frappe.has_permission("Item", "read", user=projects_manager))
		self.assertFalse(frappe.has_permission("Item", "write", user=projects_manager))
		self.assertFalse(frappe.has_permission("Item", "create", user=projects_manager))
		mr_mgr = self._make_mr(custom_project=project_a.name)
		mr_mgr.insert()
		mr_mgr.submit()
		mr_mgr.cancel()
		self.assertEqual(mr_mgr.docstatus, 2)

		# Existing Purchase User and Stock User permissions remain intact
		frappe.set_user("Administrator")
		for role in ("Purchase User", "Stock User"):
			self.assertTrue(frappe.has_permission("Material Request", "create", user=self._create_user_with_role(role)))

	def test_child_item_project_listing_and_no_duplicates(self):
		self._require_migrated_fields()

		company = self._get_or_create_company()
		warehouse = self._get_or_create_warehouse(company)
		item = self._get_or_create_item()
		schedule_date = add_days(nowdate(), 3)
		project = self._create_project(frappe.generate_hash(length=6), company=company)

		# Material Request with empty parent custom_project and multiple items for the same Project
		mr_child_only = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"transaction_date": nowdate(),
				"schedule_date": schedule_date,
				"items": [
					{
						"item_code": item,
						"qty": 5,
						"schedule_date": schedule_date,
						"warehouse": warehouse,
						"project": project.name,
					},
					{
						"item_code": item,
						"qty": 8,
						"schedule_date": schedule_date,
						"warehouse": warehouse,
						"project": project.name,
					},
				],
			}
		)
		mr_child_only.insert()

		list_res = get_material_requisition_list(filters={"project": project.name})
		self.assertEqual(list_res["total"], 1)
		self.assertEqual(len(list_res["records"]), 1)
		self.assertEqual(list_res["records"][0]["name"], mr_child_only.name)
		self.assertEqual(list_res["records"][0]["project"], project.name)

		proj_res = get_project_material_requests(project_name=project.project_name)
		self.assertEqual(proj_res["mapped_project"], project.name)
		self.assertEqual(len(proj_res["material_requests"]), 1)
		self.assertEqual(proj_res["material_requests"][0]["name"], mr_child_only.name)
