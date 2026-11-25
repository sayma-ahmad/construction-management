# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.desk.desk_page import getpage
from frappe.tests.utils import FrappeTestCase

from construction_management import dashboard
from construction_management.construction_management import phase, project, task


class TestRBACPages(FrappeTestCase):
	"""Automated RBAC tests for Construction Management pages and backend APIs."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def _create_user_with_role(self, role):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"rbac_{role.lower().replace(' ', '_')}_{frappe.generate_hash(length=6)}@example.com",
				"first_name": "RBAC",
				"last_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
		return user.name

	def test_tus03_tc14_purchase_user_cannot_access_construction_dashboard(self):
		"""TUS-03 TC-14: Purchase User is blocked from Construction Dashboard page and API."""
		purchase_user = self._create_user_with_role("Purchase User")
		projects_user = self._create_user_with_role("Projects User")

		frappe.set_user(purchase_user)
		self.assertFalse(frappe.get_doc("Page", "construction-dashboard").is_permitted())
		with self.assertRaises(frappe.PermissionError):
			getpage("construction-dashboard")
		with self.assertRaises(frappe.PermissionError):
			dashboard.get_dashboard_data()

		frappe.set_user(projects_user)
		self.assertTrue(frappe.get_doc("Page", "construction-dashboard").is_permitted())
		self.assertIn("kpis", dashboard.get_dashboard_data())

	def test_stock_user_cannot_access_projects_details_tasks_or_phases(self):
		"""TUS-04 TC-15, TUS-05 TC-16, TUS-06 TC-15, TUS-07 TC-13: Stock User blocked from Project pages & APIs."""
		stock_user = self._create_user_with_role("Stock User")
		projects_user = self._create_user_with_role("Projects User")

		frappe.set_user(stock_user)
		for page_name in (
			"construction-projects",
			"construction-project-details",
			"construction-tasks",
			"construction-phases",
		):
			self.assertFalse(frappe.get_doc("Page", page_name).is_permitted(), f"{page_name} must deny Stock User")
			with self.assertRaises(frappe.PermissionError):
				getpage(page_name)

		with self.assertRaises(frappe.PermissionError):
			project.get_construction_projects()
		with self.assertRaises(frappe.PermissionError):
			project.get_construction_project("PRJ-0001")
		with self.assertRaises(frappe.PermissionError):
			task.get_construction_tasks()
		with self.assertRaises(frappe.PermissionError):
			phase.get_project_phases()

		frappe.set_user(projects_user)
		for page_name in (
			"construction-projects",
			"construction-project-details",
			"construction-tasks",
			"construction-phases",
		):
			self.assertTrue(frappe.get_doc("Page", page_name).is_permitted(), f"{page_name} must allow Projects User")
		self.assertIsInstance(project.get_construction_projects(), list)
		self.assertIn("tasks", task.get_construction_tasks())
