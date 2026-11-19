# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import json
from pathlib import Path

import frappe
from erpnext.stock.doctype.material_request.material_request import update_status as mr_update_status
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from construction_management.construction_management.material_request import (
	get_material_requisition_list,
	get_project_material_requests,
	migrate_legacy_custom_project_to_cm_project,
	validate_construction_material_request,
)
from construction_management.construction_management.utils import (
	ensure_standard_docperms_for_customized_doctypes,
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

	def _get_or_create_item(self, exclude=None):
		filters = {"is_stock_item": 1, "disabled": 0}
		if exclude:
			excluded = [exclude] if isinstance(exclude, str) else list(exclude)
			filters["name"] = ["not in", excluded]
		item = frappe.db.get_value("Item", filters, "name")
		if item:
			return item
		uom = frappe.db.get_value("UOM", {"name": "Nos"}, "name") or "Unit"
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
		suffix = frappe.generate_hash(length=6)
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"CM-MAT-{suffix}",
				"item_name": f"Test Cement Bag {suffix}",
				"item_group": item_group,
				"cm_material_type": "Civil",
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
		if not frappe.db.has_column("Material Request", "cm_project"):
			self.skipTest(
				"Requires `bench --site dev.localhost migrate` to install Material Request Custom Fields and Custom DocPerm fixtures."
			)

	def test_construction_mr_creation_and_project_propagation(self):
		project = self._create_project(frappe.generate_hash(length=6))
		task = self._create_task("Foundation Concrete", project=project.name)
		mr = self._make_mr(
			cm_project=project.name,
			custom_task=task.name,
			custom_site_location="Block A",
			custom_priority="High",
		)
		mr.insert()

		self.assertEqual(mr.cm_project, project.name)
		self.assertEqual(mr.items[0].project, project.name)
		self.assertEqual(mr.custom_requested_by, frappe.session.user)

	def test_task_wrong_project_rejected(self):
		project_a = self._create_project(f"A-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"B-{frappe.generate_hash(length=5)}")
		task_b = self._create_task("Other Project Task", project=project_b.name)

		mr = self._make_mr(cm_project=project_a.name, custom_task=task_b.name)
		self.assertRaises(frappe.ValidationError, mr.insert)

	def test_child_item_project_mismatch_rejected(self):
		project_a = self._create_project(f"A-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"B-{frappe.generate_hash(length=5)}")
		mr = self._make_mr(cm_project=project_a.name)
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

		mr = self._make_mr(cm_project=project_a.name, custom_dpr=dpr_b.name)
		self.assertRaises(frappe.ValidationError, mr.insert)

	def test_custom_requested_by_set_server_side_and_validated(self):
		project = self._create_project(frappe.generate_hash(length=6))
		impersonated_user = self._create_user_with_role("Projects Manager")
		ordinary_user = self._create_user_with_role("Projects User")
		self.addCleanup(frappe.set_user, "Administrator")

		# Ordinary user cannot spoof custom_requested_by on create or modify after create
		frappe.set_user(ordinary_user)
		mr = self._make_mr(
			cm_project=project.name,
			custom_requested_by=impersonated_user,
		)
		mr.insert()
		self.assertEqual(mr.get("custom_requested_by"), ordinary_user)

		mr.custom_requested_by = impersonated_user
		self.assertRaises(frappe.PermissionError, mr.save)

		# Administrator / System Manager creation also records actual session user
		frappe.set_user("Administrator")
		mr_admin = self._make_mr(
			cm_project=project.name,
			custom_requested_by=ordinary_user,
		)
		mr_admin.insert()
		self.assertEqual(mr_admin.get("custom_requested_by"), "Administrator")

	def test_standard_non_construction_mr_works(self):
		mr = self._make_mr()
		mr.insert()
		mr.submit()

		self.assertEqual(mr.docstatus, 1)
		self.assertIsNone(mr.items[0].project)

	def test_list_api_filters_search_and_pagination(self):
		self._require_migrated_fields()

		project = self._create_project(frappe.generate_hash(length=6))
		other_project = self._create_project(f"OTHER-{frappe.generate_hash(length=5)}")
		mr_1 = self._make_mr(
			cm_project=project.name,
			custom_site_location="North Tower",
			custom_priority="Urgent",
			transaction_date="2026-11-10",
		)
		mr_1.insert()
		mr_1.submit()

		mr_2 = self._make_mr(
			cm_project=project.name,
			custom_site_location="South Gate",
			custom_priority="Low",
			transaction_date="2026-11-14",
		)
		mr_2.insert()

		mr_other = self._make_mr(
			cm_project=other_project.name,
			custom_site_location="East Wing",
			custom_priority="Urgent",
			transaction_date="2026-11-10",
		)
		mr_other.insert()

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

		by_project = get_material_requisition_list(filters={"project": project.name})
		self.assertEqual(by_project["total"], 2)
		self.assertNotIn(mr_other.name, {r["name"] for r in by_project["records"]})

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
		mr = self._make_mr(cm_project=project.name)
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

		mr_a = self._make_mr(cm_project=project_a.name)
		mr_a.insert()
		mr_b = self._make_mr(cm_project=project_b.name)
		mr_b.insert()

		projects_user = self._create_user_with_role("Projects User")
		projects_manager = self._create_user_with_role("Projects Manager")
		self.addCleanup(frappe.set_user, "Administrator")

		# Projects User can create and submit own MR, cannot read/modify/submit others' MRs, and cannot delete/cancel/amend
		frappe.set_user(projects_user)
		self.assertTrue(frappe.has_permission("Material Request", "create", user=projects_user))
		self.assertFalse(frappe.has_permission("Material Request", "delete", user=projects_user))
		self.assertFalse(frappe.has_permission("Material Request", "cancel", user=projects_user))
		self.assertFalse(frappe.has_permission("Material Request", "amend", user=projects_user))

		# Cannot modify or submit another user's Material Request
		other_mr = frappe.get_doc("Material Request", mr_a.name)
		self.assertRaises(frappe.PermissionError, other_mr.save)
		self.assertRaises(frappe.PermissionError, other_mr.submit)

		# Neither role gets write/create/delete on Item master data
		self.assertTrue(frappe.has_permission("Item", "read", user=projects_user))
		self.assertFalse(frappe.has_permission("Item", "write", user=projects_user))
		self.assertFalse(frappe.has_permission("Item", "create", user=projects_user))
		self.assertFalse(frappe.has_permission("Item", "delete", user=projects_user))

		mr_user = self._make_mr(cm_project=project_a.name)
		mr_user.insert()
		self.assertTrue(frappe.has_permission("Material Request", "submit", doc=mr_user, user=projects_user))
		mr_user.submit()
		self.assertEqual(mr_user.docstatus, 1)

		# With if_owner=1, Projects User sees only own MRs in get_material_requisition_list
		own_only = get_material_requisition_list()
		own_names = {r["name"] for r in own_only["records"]}
		self.assertIn(mr_user.name, own_names)
		self.assertNotIn(mr_a.name, own_names)
		self.assertNotIn(mr_b.name, own_names)

		# Projects Manager sees all projects unless restricted by User Permission
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": projects_manager,
				"allow": "Project",
				"for_value": project_a.name,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(projects_manager)
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
		mr_mgr = self._make_mr(cm_project=project_a.name)
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
		item_1 = self._get_or_create_item()
		item_2 = self._get_or_create_item(exclude=item_1)
		self.assertNotEqual(item_1, item_2)
		schedule_date = add_days(nowdate(), 3)
		project = self._create_project(frappe.generate_hash(length=6), company=company)

		# Material Request with empty parent cm_project and multiple distinct items for the same Project
		mr_child_only = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"transaction_date": nowdate(),
				"schedule_date": schedule_date,
				"items": [
					{
						"item_code": item_1,
						"qty": 5,
						"schedule_date": schedule_date,
						"warehouse": warehouse,
						"project": project.name,
					},
					{
						"item_code": item_2,
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

	def test_quantity_validation_and_status_flow(self):
		project = self._create_project(frappe.generate_hash(length=6))

		# Zero, negative, missing, and invalid quantities rejected
		for bad_qty in (0, -5, None, "abc"):
			mr_bad = self._make_mr(cm_project=project.name)
			mr_bad.items[0].qty = bad_qty
			self.assertRaises((frappe.ValidationError, ValueError, TypeError), mr_bad.insert)

		# Positive decimal quantity accepted when Item UOM allows fractions
		frac_uom = f"CMKg-{frappe.generate_hash(length=4)}"
		frappe.get_doc(
			{"doctype": "UOM", "uom_name": frac_uom, "must_be_whole_number": 0}
		).insert(ignore_permissions=True)
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
		frac_item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"CM-FRAC-{frappe.generate_hash(length=6)}",
				"item_name": "Test Sand Ton",
				"item_group": item_group,
				"cm_material_type": "Consumable",
				"stock_uom": frac_uom,
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
		mr_decimal = self._make_mr(cm_project=project.name)
		mr_decimal.items[0].item_code = frac_item.name
		mr_decimal.items[0].uom = frac_uom
		mr_decimal.items[0].stock_uom = frac_uom
		mr_decimal.items[0].qty = 2.5
		mr_decimal.insert()
		self.assertEqual(mr_decimal.items[0].qty, 2.5)

		# Valid positive integer quantity and status lifecycle: Draft -> Pending -> Stopped -> Pending -> Cancelled
		mr_valid = self._make_mr(cm_project=project.name)
		mr_valid.items[0].qty = 12
		mr_valid.insert()
		self.assertEqual(mr_valid.docstatus, 0)
		self.assertEqual(mr_valid.status, "Draft")

		# Cannot stop a Draft Material Request
		self.assertRaises(frappe.InvalidStatusError, mr_valid.update_status, "Stopped")

		mr_valid.submit()
		mr_valid.reload()
		self.assertEqual(mr_valid.docstatus, 1)
		self.assertEqual(mr_valid.status, "Pending")

		# Supported ERPNext status transitions: Pending -> Stopped -> Pending
		mr_valid.update_status("Stopped")
		mr_valid.reload()
		self.assertEqual(mr_valid.status, "Stopped")

		mr_valid.update_status("Pending")
		mr_valid.reload()
		self.assertEqual(mr_valid.status, "Pending")

		# Projects User cannot cancel submitted MR
		projects_user = self._create_user_with_role("Projects User")
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(projects_user)
		mr_user_view = frappe.get_doc("Material Request", mr_valid.name)
		self.assertRaises(frappe.PermissionError, mr_user_view.cancel)

		# Administrator / Manager can cancel -> status becomes Cancelled; cannot reopen Cancelled MR
		frappe.set_user("Administrator")
		mr_valid.cancel()
		mr_valid.reload()
		self.assertEqual(mr_valid.docstatus, 2)
		self.assertEqual(mr_valid.status, "Cancelled")
		self.assertRaises(frappe.InvalidStatusError, mr_valid.update_status, "Pending")

	def test_native_update_status_permissions(self):
		self._require_migrated_fields()

		project = self._create_project(frappe.generate_hash(length=6))
		projects_user = self._create_user_with_role("Projects User")
		projects_manager = self._create_user_with_role("Projects Manager")
		read_only_user = self._create_user_with_role("Manufacturing Manager")
		self.addCleanup(frappe.set_user, "Administrator")

		# MR created by Administrator (not owned by projects_user)
		mr_admin = self._make_mr(cm_project=project.name)
		mr_admin.insert()
		mr_admin.submit()

		# Projects User cannot call native update_status on another user's MR
		frappe.set_user(projects_user)
		self.assertRaises(frappe.PermissionError, mr_update_status, mr_admin.name, "Stopped")

		# Projects User CAN call native update_status on their own submitted MR
		mr_own = self._make_mr(cm_project=project.name)
		mr_own.insert()
		mr_own.submit()
		mr_update_status(mr_own.name, "Stopped")
		mr_own.reload()
		self.assertEqual(mr_own.status, "Stopped")

		# Read-only role (Manufacturing Manager) cannot change status via update_status
		frappe.set_user(read_only_user)
		self.assertRaises(frappe.PermissionError, mr_update_status, mr_admin.name, "Stopped")

		# Projects Manager CAN stop and reopen any permitted MR via native update_status
		frappe.set_user(projects_manager)
		mr_update_status(mr_admin.name, "Stopped")
		mr_admin.reload()
		self.assertEqual(mr_admin.status, "Stopped")

		mr_update_status(mr_admin.name, "Pending")
		mr_admin.reload()
		self.assertEqual(mr_admin.status, "Pending")

	def test_mixed_parent_and_child_project_filtering(self):
		self._require_migrated_fields()

		company = self._get_or_create_company()
		warehouse = self._get_or_create_warehouse(company)
		item = self._get_or_create_item()
		schedule_date = add_days(nowdate(), 3)
		project_a = self._create_project(f"MA-{frappe.generate_hash(length=5)}", company=company)
		project_b = self._create_project(f"MB-{frappe.generate_hash(length=5)}", company=company)

		mr_parent = self._make_mr(cm_project=project_a.name)
		mr_parent.insert()

		mr_child = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"transaction_date": nowdate(),
				"schedule_date": schedule_date,
				"items": [
					{
						"item_code": item,
						"qty": 4,
						"schedule_date": schedule_date,
						"warehouse": warehouse,
						"project": project_a.name,
					}
				],
			}
		)
		mr_child.insert()

		mr_other = self._make_mr(cm_project=project_b.name)
		mr_other.insert()

		list_res = get_material_requisition_list(filters={"project": project_a.name})
		listed_names = {r["name"] for r in list_res["records"]}
		self.assertEqual(list_res["total"], 2)
		self.assertEqual(listed_names, {mr_parent.name, mr_child.name})
		self.assertNotIn(mr_other.name, listed_names)

		proj_res = get_project_material_requests(project_name=project_a.project_name)
		proj_names = {r["name"] for r in proj_res["material_requests"]}
		self.assertEqual(proj_res["mapped_project"], project_a.name)
		self.assertEqual(proj_names, {mr_parent.name, mr_child.name})

	def test_custom_docperm_fixture_and_create_permissions(self):
		self._require_migrated_fields()

		fixture_path = Path(frappe.get_app_path("construction_management", "fixtures", "custom_docperm.json"))
		fixture_rows = json.loads(fixture_path.read_text())
		self.assertTrue(fixture_rows)
		self.assertTrue(
			all(row["role"] in {"Projects Manager", "Projects User"} for row in fixture_rows),
			"custom_docperm.json must not contain redundant overrides for standard ERPNext roles.",
		)

		ensure_standard_docperms_for_customized_doctypes()

		for role in ("Purchase User", "Stock User", "Purchase Manager", "Stock Manager"):
			role_user = self._create_user_with_role(role)
			self.assertTrue(frappe.has_permission("Material Request", "read", user=role_user))
			self.assertTrue(frappe.has_permission("Material Request", "create", user=role_user))

		item_mgr = self._create_user_with_role("Item Manager")
		self.assertTrue(frappe.has_permission("Item", "write", user=item_mgr))

		support_user = self._create_user_with_role("Support Team")
		self.assertTrue(frappe.has_permission("Issue", "create", user=support_user))
		self.assertTrue(frappe.has_permission("Issue", "delete", user=support_user))

		mfg_mgr = self._create_user_with_role("Manufacturing Manager")
		self.assertTrue(frappe.has_permission("Material Request", "read", user=mfg_mgr))
		self.assertFalse(frappe.has_permission("Material Request", "create", user=mfg_mgr))

	def test_legacy_custom_project_migration_idempotent(self):
		self._require_migrated_fields()
		if not frappe.db.has_column("Material Request", "custom_project"):
			self.skipTest("Legacy custom_project column is not present on this database.")

		project_legacy = self._create_project(f"LEG-{frappe.generate_hash(length=5)}")
		project_existing = self._create_project(f"CUR-{frappe.generate_hash(length=5)}")

		mr_legacy = self._make_mr()
		mr_legacy.insert()
		frappe.db.set_value(
			"Material Request",
			mr_legacy.name,
			{"custom_project": project_legacy.name, "cm_project": None},
			update_modified=False,
		)

		mr_existing = self._make_mr(cm_project=project_existing.name)
		mr_existing.insert()
		frappe.db.set_value(
			"Material Request",
			mr_existing.name,
			"custom_project",
			project_legacy.name,
			update_modified=False,
		)

		# Run migration twice to confirm idempotency
		migrate_legacy_custom_project_to_cm_project()
		migrate_legacy_custom_project_to_cm_project()

		mr_legacy.reload()
		mr_existing.reload()
		self.assertEqual(mr_legacy.cm_project, project_legacy.name)
		self.assertEqual(mr_legacy.items[0].project, project_legacy.name)
		self.assertEqual(mr_existing.cm_project, project_existing.name)
		self.assertFalse(frappe.db.exists("Custom Field", "Material Request-custom_project"))
