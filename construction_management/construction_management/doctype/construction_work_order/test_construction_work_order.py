# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.client import get as client_get
from frappe.client import get_list as client_get_list
from frappe.desk.search import search_link
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from construction_management.construction_management.doctype.construction_work_order.construction_work_order import (
	get_contractor_details,
	get_contractor_options,
	get_project_work_orders,
	get_work_order_list,
)
from construction_management.vendors import setup as setup_vendors


class TestConstructionWorkOrder(FrappeTestCase):
	"""Tests for Construction Work Order validations, lifecycle, APIs, and permissions."""

	def _get_or_create_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if company:
			return company
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Test Construction Co {frappe.generate_hash(length=4)}",
				"abbr": f"TC{frappe.generate_hash(length=3).upper()}",
				"default_currency": "INR",
				"country": "India",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _create_project(self, suffix, company=None):
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Test WO Project {suffix}",
				"company": company or self._get_or_create_company(),
			}
		)
		project.insert(ignore_permissions=True)
		return project

	def _create_supplier(
		self,
		suffix,
		supplier_group="Subcontractor",
		specialization="Civil Works",
		disabled=0,
	):
		setup_vendors()
		supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"Test Contractor {suffix}",
				"supplier_type": "Company",
				"supplier_group": supplier_group,
				"cm_specialization": specialization,
				"disabled": disabled,
				"country": frappe.db.get_default("country") or "India",
			}
		)
		supplier.insert(ignore_permissions=True)
		return supplier

	def _create_non_construction_supplier(self, suffix):
		setup_vendors()
		non_vendor_group = frappe.db.get_value(
			"Supplier Group",
			{"is_group": 0, "parent_supplier_group": ["!=", "Construction Vendors"]},
			"name",
		)
		if not non_vendor_group:
			non_vendor_group = frappe.get_doc(
				{
					"doctype": "Supplier Group",
					"supplier_group_name": f"General Non-CM Group {suffix}",
					"parent_supplier_group": "All Supplier Groups",
				}
			).insert(ignore_permissions=True).name

		return frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"General Supplier {suffix}",
				"supplier_type": "Company",
				"supplier_group": non_vendor_group,
				"country": frappe.db.get_default("country") or "India",
			}
		).insert(ignore_permissions=True)

	def _create_task(self, subject, project=None):
		task = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project,
			}
		)
		task.insert(ignore_permissions=True)
		return task

	def _create_user_with_role(self, role):
		email = f"cwo_{role.lower().replace(' ', '_')}_{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "CWO",
				"last_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		)
		user.insert(ignore_permissions=True)
		return user.name

	def _make_work_order(self, project, contractor, **kwargs):
		data = {
			"doctype": "Construction Work Order",
			"title": f"Foundation Formwork {frappe.generate_hash(length=5)}",
			"project": project,
			"contractor": contractor,
		}
		data.update(kwargs)
		return frappe.get_doc(data)

	def test_successful_creation_autonaming_and_default_status(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		supplier = self._create_supplier(suffix)

		wo = self._make_work_order(project.name, supplier.name, title="Tower A Concreting")
		wo.insert()

		current_year = nowdate()[:4]
		self.assertRegex(wo.name, rf"^CWO-{current_year}-\d{{5}}$")
		self.assertEqual(wo.status, "Open")
		self.assertEqual(wo.priority, "Medium")
		self.assertEqual(wo.project_name, project.project_name)
		self.assertEqual(wo.contractor_name, supplier.supplier_name)
		self.assertEqual(wo.specialization, "Civil Works")

	def test_missing_title_validation(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		supplier = self._create_supplier(suffix)

		wo_empty = self._make_work_order(project.name, supplier.name, title="")
		self.assertRaises(frappe.ValidationError, wo_empty.insert)

		wo_spaces = self._make_work_order(project.name, supplier.name, title="   ")
		self.assertRaises(frappe.ValidationError, wo_spaces.insert)

	def test_missing_and_invalid_project_validation(self):
		suffix = frappe.generate_hash(length=6)
		supplier = self._create_supplier(suffix)

		wo_missing = self._make_work_order(None, supplier.name)
		self.assertRaises(frappe.ValidationError, wo_missing.insert)

		wo_invalid = self._make_work_order(f"NONEXISTENT-PRJ-{suffix}", supplier.name)
		self.assertRaises(frappe.ValidationError, wo_invalid.insert)

	def test_missing_invalid_and_disabled_contractor_validation(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		disabled_supplier = self._create_supplier(f"dis-{suffix}", disabled=1)

		wo_missing = self._make_work_order(project.name, None)
		self.assertRaises(frappe.ValidationError, wo_missing.insert)

		wo_invalid = self._make_work_order(project.name, f"NONEXISTENT-SUP-{suffix}")
		self.assertRaises(frappe.ValidationError, wo_invalid.insert)

		wo_disabled = self._make_work_order(project.name, disabled_supplier.name)
		self.assertRaises(frappe.ValidationError, wo_disabled.insert)

	def test_non_construction_vendor_supplier_rejected(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		non_vendor_supplier = self._create_non_construction_supplier(suffix)

		wo = self._make_work_order(project.name, non_vendor_supplier.name)
		self.assertRaises(frappe.ValidationError, wo.insert)

	def test_planned_and_actual_date_validations(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		supplier = self._create_supplier(suffix)

		today = nowdate()
		yesterday = add_days(today, -1)

		wo_bad_planned = self._make_work_order(
			project.name,
			supplier.name,
			planned_start_date=today,
			planned_end_date=yesterday,
		)
		self.assertRaises(frappe.ValidationError, wo_bad_planned.insert)

		wo_bad_actual = self._make_work_order(
			project.name,
			supplier.name,
			actual_start_date=today,
			actual_completion_date=yesterday,
		)
		self.assertRaises(frappe.ValidationError, wo_bad_actual.insert)

	def test_negative_estimated_cost_rejected(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		supplier = self._create_supplier(suffix)

		wo = self._make_work_order(project.name, supplier.name, estimated_cost=-500)
		self.assertRaises(frappe.ValidationError, wo.insert)

	def test_task_project_validation(self):
		suffix = frappe.generate_hash(length=6)
		project_a = self._create_project(f"A-{suffix}")
		project_b = self._create_project(f"B-{suffix}")
		supplier = self._create_supplier(suffix)

		task_a = self._create_task("Task in A", project=project_a.name)
		task_b = self._create_task("Task in B", project=project_b.name)
		task_unlinked = self._create_task("Unlinked Task", project=None)

		wo_wrong = self._make_work_order(project_a.name, supplier.name, task=task_b.name)
		self.assertRaises(frappe.ValidationError, wo_wrong.insert)

		wo_unlinked = self._make_work_order(project_a.name, supplier.name, task=task_unlinked.name)
		self.assertRaises(frappe.ValidationError, wo_unlinked.insert)

		wo_valid = self._make_work_order(project_a.name, supplier.name, task=task_a.name)
		wo_valid.insert()
		self.assertEqual(wo_valid.task, task_a.name)

	def test_valid_status_transitions_and_auto_completion_date(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		supplier = self._create_supplier(suffix)

		wo = self._make_work_order(project.name, supplier.name)
		wo.insert()

		wo.status = "In Progress"
		wo.save()
		self.assertEqual(wo.status, "In Progress")

		wo.status = "On Hold"
		wo.save()
		self.assertEqual(wo.status, "On Hold")

		wo.status = "In Progress"
		wo.save()
		self.assertEqual(wo.status, "In Progress")

		wo.status = "Completed"
		wo.save()
		self.assertEqual(wo.status, "Completed")
		self.assertEqual(str(wo.actual_completion_date), nowdate())

		# Open -> Cancelled and In Progress -> Cancelled
		wo_cancel_open = self._make_work_order(project.name, supplier.name)
		wo_cancel_open.insert()
		wo_cancel_open.status = "Cancelled"
		wo_cancel_open.save()
		self.assertEqual(wo_cancel_open.status, "Cancelled")

		wo_cancel_prog = self._make_work_order(project.name, supplier.name)
		wo_cancel_prog.insert()
		wo_cancel_prog.status = "In Progress"
		wo_cancel_prog.save()
		wo_cancel_prog.status = "Cancelled"
		wo_cancel_prog.save()
		self.assertEqual(wo_cancel_prog.status, "Cancelled")

	def test_invalid_status_transitions_rejected(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		supplier = self._create_supplier(suffix)

		wo = self._make_work_order(project.name, supplier.name)
		wo.insert()

		# Open cannot jump directly to Completed or On Hold
		wo.status = "Completed"
		self.assertRaises(frappe.ValidationError, wo.save)
		wo.reload()

		wo.status = "On Hold"
		self.assertRaises(frappe.ValidationError, wo.save)
		wo.reload()

		# Completed is terminal
		wo.status = "In Progress"
		wo.save()
		wo.status = "Completed"
		wo.save()
		wo.status = "In Progress"
		self.assertRaises(frappe.ValidationError, wo.save)

		# Cancelled is terminal
		wo_cancelled = self._make_work_order(project.name, supplier.name)
		wo_cancelled.insert()
		wo_cancelled.status = "Cancelled"
		wo_cancelled.save()
		wo_cancelled.status = "Open"
		self.assertRaises(frappe.ValidationError, wo_cancelled.save)

	def test_contractor_options_follows_construction_vendors(self):
		suffix = frappe.generate_hash(length=6)
		subcontractor = self._create_supplier(
			f"sub-{suffix}", supplier_group="Subcontractor", specialization="Masonry"
		)
		service_provider = self._create_supplier(
			f"srv-{suffix}", supplier_group="Service Provider", specialization="Electrical"
		)
		disabled_sub = self._create_supplier(
			f"dis-{suffix}", supplier_group="Subcontractor", specialization="Plumbing", disabled=1
		)

		rows = get_contractor_options("Supplier", suffix, "name", 0, 20, None)
		names = {row[0] for row in rows}
		self.assertIn(subcontractor.name, names)
		self.assertIn(service_provider.name, names)
		self.assertNotIn(disabled_sub.name, names)

	def test_contractor_lookup_permissions_across_roles(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		subcontractor = self._create_supplier(
			f"sub-{suffix}", supplier_group="Subcontractor", specialization="Masonry"
		)
		equipment_vendor = self._create_supplier(
			f"eqp-{suffix}",
			supplier_group="Equipment Supplier",
			specialization="Construction Equipment",
		)
		disabled_vendor = self._create_supplier(
			f"dis-{suffix}", supplier_group="Subcontractor", specialization="Plumbing", disabled=1
		)
		unrelated_supplier = self._create_non_construction_supplier(f"non-{suffix}")

		projects_user = self._create_user_with_role("Projects User")
		projects_manager = self._create_user_with_role("Projects Manager")
		sys_manager = self._create_user_with_role("System Manager")
		purchase_user = self._create_user_with_role("Purchase User")
		stock_user = self._create_user_with_role("Stock User")
		website_mgr = self._create_user_with_role("Website Manager")
		sales_user = self._create_user_with_role("Sales User")
		self.addCleanup(frappe.set_user, "Administrator")

		for role_user in (projects_user, projects_manager, sys_manager, purchase_user, stock_user):
			frappe.set_user(role_user)
			rows = get_contractor_options("Supplier", suffix, "name", 0, 20, None)
			names = {row[0] for row in rows}
			self.assertIn(subcontractor.name, names)
			self.assertIn(equipment_vendor.name, names)
			self.assertNotIn(disabled_vendor.name, names)
			self.assertNotIn(unrelated_supplier.name, names)

			details = get_contractor_details(subcontractor.name)
			self.assertTrue(details["valid"])
			self.assertEqual(details["contractor_name"], subcontractor.supplier_name)
			self.assertEqual(details["specialization"], "Masonry")
			self.assertFalse(get_contractor_details(unrelated_supplier.name)["valid"])
			self.assertFalse(get_contractor_details(disabled_vendor.name)["valid"])

		# Projects User / Manager can search via search_link and create valid Work Orders,
		# cannot browse broad Supplier endpoints, and cannot bypass validation with unrelated Suppliers
		for project_role_user in (projects_user, projects_manager):
			frappe.set_user(project_role_user)
			link_results = search_link(
				"Supplier",
				suffix,
				query="construction_management.construction_management.doctype.construction_work_order.construction_work_order.get_contractor_options",
			)
			link_values = {item["value"] for item in link_results}
			self.assertIn(subcontractor.name, link_values)
			self.assertNotIn(unrelated_supplier.name, link_values)
			self.assertNotIn(disabled_vendor.name, link_values)

			self.assertFalse(frappe.has_permission("Supplier", "read", user=project_role_user))
			self.assertRaises(frappe.PermissionError, client_get, "Supplier", unrelated_supplier.name)
			self.assertRaises(frappe.PermissionError, client_get_list, "Supplier")

			valid_wo = self._make_work_order(project.name, subcontractor.name)
			valid_wo.insert()
			self.assertEqual(valid_wo.contractor_name, subcontractor.supplier_name)

			unrelated_wo = self._make_work_order(project.name, unrelated_supplier.name)
			self.assertRaises(frappe.ValidationError, unrelated_wo.insert)

		# Purchase User and Stock User retain native Supplier read access
		for sup_user in (purchase_user, stock_user):
			frappe.set_user(sup_user)
			self.assertTrue(frappe.has_permission("Supplier", "read", user=sup_user))

		# Unauthorized roles cannot call contractor lookup endpoints
		for unauth_user in (website_mgr, sales_user):
			frappe.set_user(unauth_user)
			self.assertRaises(
				frappe.PermissionError,
				get_contractor_options,
				"Supplier",
				suffix,
				"name",
				0,
				20,
				None,
			)
			self.assertRaises(
				frappe.PermissionError, get_contractor_details, subcontractor.name
			)

	def test_list_filters_search_pagination_and_project_mapping(self):
		suffix = frappe.generate_hash(length=6)
		project_a = self._create_project(f"A-{suffix}")
		project_b = self._create_project(f"B-{suffix}")
		supplier_1 = self._create_supplier(f"S1-{suffix}")
		supplier_2 = self._create_supplier(f"S2-{suffix}")

		wo_1 = self._make_work_order(
			project_a.name,
			supplier_1.name,
			title=f"Electrical Trunking {suffix}",
			priority="High",
		)
		wo_1.insert()
		wo_1.status = "In Progress"
		wo_1.save()

		wo_2 = self._make_work_order(
			project_a.name,
			supplier_2.name,
			title=f"Plumbing Risers {suffix}",
			priority="Urgent",
		)
		wo_2.insert()

		wo_3 = self._make_work_order(
			project_b.name,
			supplier_1.name,
			title=f"Boundary Painting {suffix}",
			priority="Low",
		)
		wo_3.insert()

		# Project filter
		proj_res = get_work_order_list(filters={"project": project_a.name})
		self.assertEqual(proj_res["total"], 2)
		self.assertEqual({r["name"] for r in proj_res["records"]}, {wo_1.name, wo_2.name})

		# Contractor, status, and priority filters
		combo_res = get_work_order_list(
			filters={
				"project": project_a.name,
				"contractor": supplier_1.name,
				"status": "In Progress",
				"priority": "High",
			}
		)
		self.assertEqual(combo_res["total"], 1)
		self.assertEqual(combo_res["records"][0]["name"], wo_1.name)

		# Search by ID and title
		id_search = get_work_order_list(search=wo_2.name)
		self.assertEqual(id_search["total"], 1)
		self.assertEqual(id_search["records"][0]["name"], wo_2.name)

		title_search = get_work_order_list(search=f"Electrical Trunking {suffix}")
		self.assertEqual(title_search["total"], 1)
		self.assertEqual(title_search["records"][0]["name"], wo_1.name)

		# Pagination
		page_1 = get_work_order_list(filters={"project": project_a.name}, start=0, page_length=1)
		page_2 = get_work_order_list(filters={"project": project_a.name}, start=1, page_length=1)
		self.assertEqual(page_1["total"], 2)
		self.assertEqual(len(page_1["records"]), 1)
		self.assertEqual(len(page_2["records"]), 1)
		self.assertNotEqual(page_1["records"][0]["name"], page_2["records"][0]["name"])

		# Project mapping API
		mapped = get_project_work_orders(project_name=project_a.project_name)
		self.assertEqual(mapped["mapped_project"], project_a.name)
		self.assertEqual({r["name"] for r in mapped["work_orders"]}, {wo_1.name, wo_2.name})

		unmapped = get_project_work_orders(
			project_name=f"Unknown Sample Project {suffix}", project_code="PRJ-UNKNOWN"
		)
		self.assertIsNone(unmapped["mapped_project"])
		self.assertEqual(unmapped["work_orders"], [])

	def test_project_access_and_role_permissions(self):
		suffix = frappe.generate_hash(length=6)
		project_allowed = self._create_project(f"Allowed-{suffix}")
		project_restricted = self._create_project(f"Restricted-{suffix}")
		supplier = self._create_supplier(suffix)

		wo_allowed = self._make_work_order(project_allowed.name, supplier.name)
		wo_allowed.insert()

		wo_restricted = self._make_work_order(project_restricted.name, supplier.name)
		wo_restricted.insert()

		projects_user = self._create_user_with_role("Projects User")
		projects_manager = self._create_user_with_role("Projects Manager")
		unauthorized_user = self._create_user_with_role("Website Manager")
		self.addCleanup(frappe.set_user, "Administrator")

		# Restrict Projects User to project_allowed via standard User Permission
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": projects_user,
				"allow": "Project",
				"for_value": project_allowed.name,
			}
		).insert(ignore_permissions=True)

		# Projects User: can read/write allowed project, cannot delete, cannot see restricted project
		frappe.set_user(projects_user)
		self.assertTrue(frappe.has_permission("Construction Work Order", "read", user=projects_user))
		self.assertTrue(frappe.has_permission("Construction Work Order", "create", user=projects_user))
		self.assertTrue(frappe.has_permission("Construction Work Order", "write", user=projects_user))
		self.assertFalse(frappe.has_permission("Construction Work Order", "delete", user=projects_user))

		visible = get_work_order_list(filters={"project": project_allowed.name})
		self.assertEqual([r["name"] for r in visible["records"]], [wo_allowed.name])

		unfiltered = get_work_order_list(filters="[]")
		visible_names = {r["name"] for r in unfiltered["records"]}
		self.assertIn(wo_allowed.name, visible_names)
		self.assertNotIn(wo_restricted.name, visible_names)

		hidden = get_work_order_list(filters={"project": project_restricted.name})
		self.assertEqual(hidden["total"], 0)
		self.assertEqual(hidden["records"], [])

		hidden_proj_map = get_project_work_orders(project_name=project_restricted.project_name)
		self.assertIsNone(hidden_proj_map["mapped_project"])
		self.assertEqual(hidden_proj_map["work_orders"], [])

		unauthorized_create = self._make_work_order(project_restricted.name, supplier.name)
		self.assertRaises(frappe.PermissionError, unauthorized_create.insert)

		self.assertFalse(
			frappe.has_permission(
				"Construction Work Order", "read", doc=wo_restricted, user=projects_user
			)
		)
		self.assertRaises(
			frappe.PermissionError, client_get, "Construction Work Order", wo_restricted.name
		)
		wo_restricted_doc = frappe.get_doc("Construction Work Order", wo_restricted.name)
		wo_restricted_doc.remarks = "Unauthorized edit attempt"
		self.assertRaises(frappe.PermissionError, wo_restricted_doc.save)

		user_doc = frappe.get_doc("Construction Work Order", wo_allowed.name)
		user_doc.status = "In Progress"
		user_doc.save()
		self.assertEqual(user_doc.status, "In Progress")

		self.assertRaises(
			frappe.PermissionError, frappe.delete_doc, "Construction Work Order", wo_allowed.name
		)

		# Unauthorized role cannot read or create
		frappe.set_user(unauthorized_user)
		self.assertFalse(
			frappe.has_permission("Construction Work Order", "read", user=unauthorized_user)
		)
		self.assertRaises(frappe.PermissionError, get_work_order_list)
		unauth_doc = self._make_work_order(project_allowed.name, supplier.name)
		self.assertRaises(frappe.PermissionError, unauth_doc.insert)

		# Projects Manager can delete
		frappe.set_user(projects_manager)
		self.assertTrue(frappe.has_permission("Construction Work Order", "delete", user=projects_manager))
		frappe.delete_doc("Construction Work Order", wo_allowed.name)
		self.assertFalse(frappe.db.exists("Construction Work Order", wo_allowed.name))
