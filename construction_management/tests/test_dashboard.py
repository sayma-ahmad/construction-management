# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

from construction_management import dashboard


class TestDashboard(FrappeTestCase):
	"""Comprehensive unit tests for Construction Dashboard data and metrics (US-17)."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_01_permission_checks(self):
		"""Verify that unauthenticated / guest users are blocked from querying dashboard data."""
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				dashboard.get_dashboard_data()
		finally:
			frappe.set_user("Administrator")

	def test_02_project_counts(self):
		"""Subtask 1: Verify total, active, and completed project counts match the database."""
		data = dashboard.get_dashboard_data()
		proj_metrics = data["metrics"]["project"]

		expected_total = frappe.db.count("Project")
		expected_active = frappe.db.count("Project", {"status": ["in", ["Open", "In Progress", "Working"]]})
		expected_completed = frappe.db.count("Project", {"status": "Completed"})

		self.assertEqual(proj_metrics["total_projects"], expected_total)
		self.assertEqual(proj_metrics["active_projects"], expected_active)
		self.assertEqual(proj_metrics["completed_projects"], expected_completed)

		# KPI Card verification
		proj_kpi = next((k for k in data["kpis"] if k["label"] == "Total Projects"), None)
		self.assertIsNotNone(proj_kpi)
		self.assertEqual(proj_kpi["value"], expected_total)

	def test_03_purchase_order_and_work_order_counts(self):
		"""Subtask 2: Verify Purchase Order and Work Order counts match the database."""
		data = dashboard.get_dashboard_data()
		proc_metrics = data["metrics"]["procurement"]

		expected_po_total = frappe.db.count("Purchase Order")
		expected_po_active = frappe.db.count(
			"Purchase Order",
			{"status": ["in", ["Draft", "To Receive and Bill", "To Receive", "To Bill"]]},
		)
		expected_wo_total = frappe.db.count("Work Order") if frappe.db.exists("DocType", "Work Order") else 0

		self.assertEqual(proc_metrics["total_purchase_orders"], expected_po_total)
		self.assertEqual(proc_metrics["active_purchase_orders"], expected_po_active)
		self.assertEqual(proc_metrics["total_work_orders"], expected_wo_total)

		# KPI Card verification
		po_kpi = next((k for k in data["kpis"] if k["label"] == "Purchase Orders"), None)
		self.assertIsNotNone(po_kpi)
		self.assertEqual(po_kpi["value"], expected_po_total)

		wo_kpi = next((k for k in data["kpis"] if k["label"] == "Work Orders"), None)
		self.assertIsNotNone(wo_kpi)
		self.assertEqual(wo_kpi["value"], expected_wo_total)

	def test_04_grn_and_material_request_counts(self):
		"""Subtask 3: Verify Goods Received (GRN) and Material Request counts match the database."""
		data = dashboard.get_dashboard_data()
		proc_metrics = data["metrics"]["procurement"]

		expected_grn = (
			frappe.db.count("Purchase Receipt") if frappe.db.exists("DocType", "Purchase Receipt") else 0
		)
		expected_mr = (
			frappe.db.count("Material Request") if frappe.db.exists("DocType", "Material Request") else 0
		)

		self.assertEqual(proc_metrics["total_grns"], expected_grn)
		self.assertEqual(proc_metrics["total_material_requests"], expected_mr)

		grn_kpi = next((k for k in data["kpis"] if k["label"] == "Goods Received (GRN)"), None)
		self.assertIsNotNone(grn_kpi)
		self.assertEqual(grn_kpi["value"], expected_grn)

		mr_kpi = next((k for k in data["kpis"] if k["label"] == "Material Requests"), None)
		self.assertIsNotNone(mr_kpi)
		self.assertEqual(mr_kpi["value"], expected_mr)

	def test_05_issue_and_inventory_summaries(self):
		"""Subtask 4: Verify Issue summaries and Inventory stock items match the database."""
		data = dashboard.get_dashboard_data()
		inv_metrics = data["metrics"]["inventory_issues"]

		expected_issues = frappe.db.count("Issue") if frappe.db.exists("DocType", "Issue") else 0
		expected_items = (
			frappe.db.count("Item", {"is_stock_item": 1}) if frappe.db.exists("DocType", "Item") else 0
		)

		self.assertEqual(inv_metrics["total_issues"], expected_issues)
		self.assertEqual(inv_metrics["total_items"], expected_items)

		issue_kpi = next((k for k in data["kpis"] if k["label"] == "Site Issues"), None)
		self.assertIsNotNone(issue_kpi)
		self.assertEqual(issue_kpi["value"], expected_issues)

		inv_kpi = next((k for k in data["kpis"] if k["label"] == "Inventory Items"), None)
		self.assertIsNotNone(inv_kpi)
		self.assertEqual(inv_kpi["value"], expected_items)

		# Inventory chart structure
		inv_chart = data["inventory"]
		self.assertTrue(len(inv_chart["labels"]) >= 1)
		self.assertEqual(len(inv_chart["labels"]), len(inv_chart["in_stock"]))
		self.assertEqual(len(inv_chart["labels"]), len(inv_chart["reorder_level"]))

	def test_06_expense_and_payable_summaries(self):
		"""Subtask 5: Verify Expense and Payable summaries calculate correctly."""
		data = dashboard.get_dashboard_data()
		fin = data["metrics"]["financial"]

		self.assertIn("total_payables", fin)
		self.assertIn("total_expenses", fin)
		self.assertIn("currency", fin)
		self.assertTrue(isinstance(fin["total_payables"], (int, float)))
		self.assertTrue(isinstance(fin["total_expenses"], (int, float)))

		payable_kpi = next((k for k in data["kpis"] if k["label"] == "Total Payables"), None)
		self.assertIsNotNone(payable_kpi)
		self.assertTrue(payable_kpi.get("is_currency"))
		self.assertEqual(payable_kpi["value"], fin["total_payables"])

	def test_07_chart_datasets_structure(self):
		"""Subtask 6: Verify chart datasets match Frappe Chart schema expectations."""
		data = dashboard.get_dashboard_data()

		# 1. Project Completion Chart
		completion = data["completion"]
		self.assertEqual(len(completion["labels"]), 6)
		self.assertEqual(len(completion["planned"]), 6)
		self.assertEqual(len(completion["actual"]), 6)

		# 2. Task Status Chart
		task_status = data["task_status"]
		self.assertEqual(task_status["labels"], ["Completed", "In Progress", "Open", "Overdue"])
		self.assertEqual(len(task_status["values"]), 4)

		# 3. Project Progress Table
		projects = data["projects"]
		if frappe.db.count("Project") > 0:
			self.assertTrue(len(projects) >= 1)
			p0 = projects[0]
			self.assertIn("name", p0)
			self.assertIn("progress", p0)
			self.assertIn("status", p0)
			self.assertIn("due", p0)

	def test_08_activity_feed_format(self):
		"""Subtask 6: Verify recent site activity feed returns formatted event items."""
		data = dashboard.get_dashboard_data()
		activity = data["activity"]

		self.assertTrue(len(activity) >= 1)
		for item in activity:
			self.assertIn("text", item)
			self.assertIn("time", item)
			self.assertTrue(bool(item["text"]))
			self.assertTrue(bool(item["time"]))

	def test_09_kpis_icons_and_navigation(self):
		"""Verify that every KPI card has an icon and a valid navigation route/doctype."""
		data = dashboard.get_dashboard_data()
		kpis = data["kpis"]

		self.assertEqual(len(kpis), 8)
		for kpi in kpis:
			self.assertTrue(bool(kpi.get("icon")), f"KPI {kpi['label']} missing icon")
			self.assertTrue(bool(kpi.get("doctype")), f"KPI {kpi['label']} missing doctype")
			self.assertTrue(bool(kpi.get("route")), f"KPI {kpi['label']} missing route")
			self.assertTrue(frappe.db.exists("DocType", kpi["doctype"]), f"Target DocType {kpi['doctype']} does not exist")
