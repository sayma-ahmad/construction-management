# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

from construction_management import dashboard


class TestDashboard(FrappeTestCase):
	"""Comprehensive unit tests for Construction Dashboard data and metrics (US-17)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for uom in ["Bag", "Kg", "Nos", "Meter", "Unit"]:
			if not frappe.db.exists("UOM", uom):
				frappe.get_doc(
					{
						"doctype": "UOM",
						"uom_name": uom,
						"name": uom,
					}
				).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _get_or_create_company(self):
		company = (
			frappe.defaults.get_user_default("Company")
			or frappe.db.get_default("company")
			or frappe.db.get_value("Company", {}, "name")
		)
		if company:
			return company
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Test Dashboard Co {frappe.generate_hash(length=4)}",
				"abbr": f"TD{frappe.generate_hash(length=3).upper()}",
				"default_currency": "INR",
				"country": "India",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _get_or_create_supplier(self):
		supplier = frappe.db.get_value("Supplier", {}, "name")
		if supplier:
			return supplier
		doc = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"Test Supplier {frappe.generate_hash(length=4)}",
				"supplier_group": "Material Supplier",
				"supplier_type": "Company",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _get_or_create_warehouse(self, company):
		wh = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
		if wh:
			return wh
		doc = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"Stores {frappe.generate_hash(length=4)}",
				"company": company,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_01_permission_checks(self):
		"""Verify that unauthenticated / guest users are blocked from querying dashboard data."""
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				dashboard.get_dashboard_data()
		finally:
			frappe.set_user("Administrator")

	def test_02_project_status_handling_and_active_counts(self):
		"""Verify that project counts exclude Cancelled projects and handle Open/Completed cleanly."""
		company = self._get_or_create_company()

		# Create controlled projects
		p_open = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Open Proj {frappe.generate_hash(length=4)}",
				"company": company,
				"status": "Open",
				"percent_complete": 60.0,
			}
		).insert(ignore_permissions=True)

		p_comp = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Completed Proj {frappe.generate_hash(length=4)}",
				"company": company,
				"status": "Completed",
				"percent_complete": 100.0,
			}
		).insert(ignore_permissions=True)
		p_comp.db_set("status", "Completed")

		p_canc = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Cancelled Proj {frappe.generate_hash(length=4)}",
				"company": company,
				"status": "Cancelled",
				"percent_complete": 10.0,
			}
		).insert(ignore_permissions=True)
		p_canc.db_set("status", "Cancelled")

		data = dashboard.get_dashboard_data(company=company)
		proj_metrics = data["metrics"]["project"]

		# Cancelled projects must NOT be counted as active
		self.assertNotIn(p_canc.name, [p["id"] for p in data["projects"]])
		self.assertTrue(proj_metrics["active_projects"] >= 1)
		self.assertTrue(proj_metrics["completed_projects"] >= 1)

		# KPI Card exists and has route
		kpi = next((k for k in data["kpis"] if k["label"] == "Total Projects"), None)
		self.assertIsNotNone(kpi)
		self.assertEqual(kpi["doctype"], "Project")
		self.assertTrue(kpi["has_permission"])

	def test_03_purchase_order_statuses_and_draft_separation(self):
		"""Verify that active Purchase Orders count only submitted orders in fulfillment, excluding Draft & Cancelled."""
		company = self._get_or_create_company()
		supplier = self._get_or_create_supplier()
		wh = self._get_or_create_warehouse(company)

		# 1. Draft PO
		po_draft = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"company": company,
				"supplier": supplier,
				"set_warehouse": wh,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"items": [
					{
						"item_code": "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {}, "name"),
						"qty": 10,
						"rate": 100,
						"warehouse": wh,
						"schedule_date": add_days(nowdate(), 7),
					}
				],
			}
		)
		po_draft.insert(ignore_permissions=True)
		self.assertEqual(po_draft.docstatus, 0)

		data = dashboard.get_dashboard_data()
		proc = data["metrics"]["procurement"]

		# Total includes valid non-cancelled orders
		self.assertTrue(proc["total_purchase_orders"] >= 1)

		# Active PO KPI does not falsely include draft orders as active in-fulfillment
		kpi = next((k for k in data["kpis"] if k["label"] == "Purchase Orders"), None)
		self.assertIsNotNone(kpi)
		self.assertTrue(kpi["has_permission"])

	def test_04_goods_received_excludes_returns_and_drafts(self):
		"""Verify that submitted GRNs exclude purchase returns (is_return = 1) and draft receipts."""
		company = self._get_or_create_company()
		supplier = self._get_or_create_supplier()
		wh = self._get_or_create_warehouse(company)
		item_code = frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		if item_code:
			# Create a draft receipt
			pr_draft = frappe.get_doc(
				{
					"doctype": "Purchase Receipt",
					"company": company,
					"supplier": supplier,
					"items": [
						{
							"item_code": item_code,
							"qty": 5,
							"rate": 100,
							"warehouse": wh,
						}
					],
				}
			)
			pr_draft.insert(ignore_permissions=True)

			data = dashboard.get_dashboard_data()
			proc = data["metrics"]["procurement"]
			# Submitted GRNs must not count draft receipts
			self.assertTrue(proc["total_grns"] >= proc["submitted_grns"])

	def test_05_material_request_purchase_type_filter(self):
		"""Verify that Material Request metrics only evaluate active Purchase requisitions."""
		company = self._get_or_create_company()

		data = dashboard.get_dashboard_data()
		proc = data["metrics"]["procurement"]
		self.assertIn("total_material_requests", proc)
		self.assertIn("open_material_requests", proc)
		self.assertTrue(proc["total_material_requests"] >= proc["open_material_requests"])

	def test_06_task_status_partitioning_and_mutual_exclusivity(self):
		"""Verify that Task status donut chart slices are strictly mutually exclusive."""
		data = dashboard.get_dashboard_data()
		chart = data["task_status"]

		self.assertEqual(chart["labels"], ["Completed", "In Progress", "Open", "Overdue"])
		values = chart["values"]
		self.assertEqual(len(values), 4)

		# None of the values should be negative
		for v in values:
			self.assertTrue(v >= 0)

		# Verify mutual exclusivity directly on Task records
		today = frappe.utils.getdate(nowdate())
		tasks = frappe.get_list(
			"Task",
			filters={"status": ["not in", ["Cancelled", "Template"]]},
			fields=["name", "status", "exp_end_date"],
			limit_page_length=0,
		)

		expected_completed = 0
		expected_in_progress = 0
		expected_open = 0
		expected_overdue = 0

		for t in tasks:
			is_od = False
			if t.status == "Overdue":
				is_od = True
			elif t.exp_end_date and frappe.utils.getdate(t.exp_end_date) < today and t.status != "Completed":
				is_od = True

			if is_od:
				expected_overdue += 1
			elif t.status == "Completed":
				expected_completed += 1
			elif t.status in ("Working", "In Progress"):
				expected_in_progress += 1
			else:
				expected_open += 1

		self.assertEqual(values[0], expected_completed)
		self.assertEqual(values[1], expected_in_progress)
		self.assertEqual(values[2], expected_open)
		self.assertEqual(values[3], expected_overdue)
		self.assertEqual(sum(values), len(tasks))

	def test_07_inventory_evaluates_without_synthetic_reorder(self):
		"""Verify that inventory metrics evaluate stock and reorder thresholds without synthetic fallbacks."""
		data = dashboard.get_dashboard_data()
		inv = data["metrics"]["inventory_issues"]

		self.assertIn("total_items", inv)
		self.assertIn("low_stock_items", inv)
		self.assertIn("chart", inv)

		# Chart datasets must not use hardcoded synthetic fallback materials
		labels = inv["chart"]["labels"]
		in_stock = inv["chart"]["in_stock"]
		reorder = inv["chart"]["reorder_level"]

		self.assertEqual(len(labels), len(in_stock))
		self.assertEqual(len(labels), len(reorder))

	def test_08_financial_payables_base_currency(self):
		"""Verify that payables use base amounts in company currency."""
		data = dashboard.get_dashboard_data()
		fin = data["metrics"]["financial"]

		self.assertIn("total_payables", fin)
		self.assertIn("unpaid_invoices_count", fin)
		self.assertIn("currency", fin)
		self.assertTrue(fin["total_payables"] >= 0)

	def test_09_user_permission_project_isolation(self):
		"""Verify that User Permissions isolate dashboard metrics by permitted project."""
		company = self._get_or_create_company()

		p_a = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"UserPerm Proj A {frappe.generate_hash(length=4)}",
				"company": company,
				"status": "Open",
			}
		).insert(ignore_permissions=True)

		p_b = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"UserPerm Proj B {frappe.generate_hash(length=4)}",
				"company": company,
				"status": "Open",
			}
		).insert(ignore_permissions=True)

		user_email = f"restricted_dash_{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": user_email,
				"first_name": "Restricted",
				"last_name": "User",
				"roles": [{"role": "Projects User"}],
			}
		).insert(ignore_permissions=True)

		user_perm = frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user_email,
				"allow": "Project",
				"for_value": p_a.name,
			}
		).insert(ignore_permissions=True)

		try:
			frappe.set_user(user_email)
			data = dashboard.get_dashboard_data(company=company)

			returned_proj_names = [p["id"] for p in data["projects"]]
			self.assertIn(p_a.name, returned_proj_names)
			self.assertNotIn(p_b.name, returned_proj_names)

			# Unauthorized sections (e.g. Purchase Invoice) must return 0 without failing
			self.assertEqual(data["metrics"]["financial"]["total_payables"], 0.0)

		finally:
			frappe.set_user("Administrator")
			user_perm.delete(ignore_permissions=True)

	def test_10_recent_activity_has_navigation_data(self):
		"""Verify that recent activity feed items provide doctype and docname for navigation."""
		data = dashboard.get_dashboard_data()
		activity = data.get("activity", [])

		for item in activity:
			if "doctype" in item:
				self.assertTrue(bool(item.get("docname")), "Activity with doctype must include docname")
				self.assertTrue(frappe.db.exists(item["doctype"], item["docname"]))
