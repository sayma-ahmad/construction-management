# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.desk.form.assign_to import add as assign_to_doc
from frappe.tests.utils import FrappeTestCase

from construction_management.construction_management.issue import (
	get_issue_list,
	get_project_issues,
)


class TestConstructionIssue(FrappeTestCase):
	"""Tests for reusing ERPNext Issue for Construction Site Issues."""

	def _get_or_create_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if company:
			return company
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Test Issue Co {frappe.generate_hash(length=4)}",
				"abbr": f"TI{frappe.generate_hash(length=3).upper()}",
				"default_currency": "INR",
				"country": "India",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _create_project(self, suffix, company=None):
		doc = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Test Issue Project {suffix}",
				"company": company or self._get_or_create_company(),
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _create_user_with_role(self, role):
		email = f"issue_{role.lower().replace(' ', '_')}_{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Issue",
				"last_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		)
		user.insert(ignore_permissions=True)
		return user.name

	def _get_priority(self, name="Medium"):
		if frappe.db.exists("Issue Priority", name):
			return name
		return frappe.db.get_value("Issue Priority", {}, "name")

	def _make_issue(self, project, **kwargs):
		data = {
			"doctype": "Issue",
			"subject": f"Scaffolding inspection {frappe.generate_hash(length=5)}",
			"project": project,
			"priority": self._get_priority("Medium"),
			"status": "Open",
			"description": "<p>Guardrail missing on level 3 east wing.</p>",
		}
		data.update(kwargs)
		return frappe.get_doc(data)

	def _require_issue_fixtures(self):
		if not frappe.db.exists("Custom DocPerm", "cm-issue-perm-projects-user-0"):
			self.skipTest(
				"Requires `bench --site dev.localhost migrate` to install Issue Type and Issue Custom DocPerm fixtures."
			)

	def test_issue_creation_project_link_and_native_fields(self):
		project = self._create_project(frappe.generate_hash(length=6))
		issue = self._make_issue(
			project.name,
			priority=self._get_priority("High"),
			status="Open",
		)
		issue.insert()

		self.assertEqual(issue.project, project.name)
		self.assertEqual(issue.status, "Open")
		self.assertEqual(issue.priority, self._get_priority("High"))
		self.assertIn("Guardrail missing", issue.description)

		issue.status = "Resolved"
		issue.resolution_details = "<p>Guardrail reinstalled and inspected.</p>"
		issue.save()
		issue.reload()
		self.assertEqual(issue.status, "Resolved")

	def test_issue_type_fixture_values(self):
		self._require_issue_fixtures()
		project = self._create_project(frappe.generate_hash(length=6))
		for category in ("Safety", "Quality", "Material", "Equipment", "Design", "Delay", "Other"):
			self.assertTrue(frappe.db.exists("Issue Type", category), f"Missing Issue Type: {category}")

		issue = self._make_issue(project.name, issue_type="Safety")
		issue.insert()
		self.assertEqual(issue.issue_type, "Safety")

	def test_native_assignment_and_attachment(self):
		project = self._create_project(frappe.generate_hash(length=6))
		assignee = self._create_user_with_role("Projects User")
		issue = self._make_issue(project.name)
		issue.insert()

		assign_to_doc(
			{
				"assign_to": [assignee],
				"doctype": "Issue",
				"name": issue.name,
				"description": "Inspect scaffolding",
			}
		)

		list_res = get_issue_list(filters={"project": project.name})
		self.assertEqual(list_res["total"], 1)
		self.assertIn(assignee, list_res["records"][0]["assigned_to"])

		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "site_photo.txt",
				"content": b"site inspection photo placeholder",
				"attached_to_doctype": "Issue",
				"attached_to_name": issue.name,
				"is_private": 1,
			}
		)
		file_doc.insert(ignore_permissions=True)
		self.assertEqual(file_doc.attached_to_name, issue.name)

	def test_issue_list_filters_search_and_pagination(self):
		project = self._create_project(frappe.generate_hash(length=6))
		issue_1 = self._make_issue(
			project.name,
			subject="Tower Crane Hydraulic Leak",
			priority=self._get_priority("High"),
			status="Open",
		)
		issue_1.insert()

		issue_2 = self._make_issue(
			project.name,
			subject="Basement Sump Pump Check",
			priority=self._get_priority("Low"),
			status="On Hold",
		)
		issue_2.insert()

		filtered = get_issue_list(
			filters={"project": project.name, "status": "Open", "priority": self._get_priority("High")}
		)
		self.assertEqual(filtered["total"], 1)
		row = filtered["records"][0]
		self.assertEqual(row["name"], issue_1.name)
		for field in ("subject", "project", "issue_type", "priority", "status", "opening_date", "assigned_to"):
			self.assertIn(field, row)

		expected_total = 2
		if frappe.db.exists("Issue Type", "Safety"):
			issue_type_rec = self._make_issue(project.name, issue_type="Safety")
			issue_type_rec.insert()
			by_type = get_issue_list(filters={"project": project.name, "issue_type": "Safety"})
			self.assertEqual(by_type["total"], 1)
			self.assertEqual(by_type["records"][0]["name"], issue_type_rec.name)
			expected_total = 3

		searched = get_issue_list(search="Hydraulic Leak")
		self.assertEqual(searched["total"], 1)
		self.assertEqual(searched["records"][0]["name"], issue_1.name)

		page_1 = get_issue_list(filters={"project": project.name}, start=0, page_length=1)
		page_2 = get_issue_list(filters={"project": project.name}, start=1, page_length=1)
		self.assertEqual(page_1["total"], expected_total)
		self.assertEqual(len(page_1["records"]), 1)
		self.assertEqual(len(page_2["records"]), 1)
		self.assertNotEqual(page_1["records"][0]["name"], page_2["records"][0]["name"])

	def test_get_project_issues_mapped_and_unmapped(self):
		project = self._create_project(frappe.generate_hash(length=6))
		issue = self._make_issue(project.name)
		issue.insert()

		mapped = get_project_issues(project_name=project.project_name)
		self.assertEqual(mapped["mapped_project"], project.name)
		self.assertEqual(len(mapped["issues"]), 1)
		self.assertEqual(mapped["issues"][0]["name"], issue.name)

		unmapped = get_project_issues(
			project_name="Nonexistent Sample Project XYZ", project_code="PRJ-999"
		)
		self.assertIsNone(unmapped["mapped_project"])
		self.assertEqual(unmapped["issues"], [])

	def test_role_permissions_and_project_user_permission_scoping(self):
		self._require_issue_fixtures()

		project_a = self._create_project(f"A-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"B-{frappe.generate_hash(length=5)}")

		issue_a = self._make_issue(project_a.name, issue_type="Safety")
		issue_a.insert()
		issue_b = self._make_issue(project_b.name, issue_type="Quality")
		issue_b.insert()

		projects_user = self._create_user_with_role("Projects User")
		projects_manager = self._create_user_with_role("Projects Manager")
		unauthorized_user = self._create_user_with_role("Stock User")
		self.addCleanup(frappe.set_user, "Administrator")

		# Unauthorized user cannot read or create Issues
		frappe.set_user(unauthorized_user)
		self.assertFalse(frappe.has_permission("Issue", "read", user=unauthorized_user))
		self.assertFalse(frappe.has_permission("Issue", "create", user=unauthorized_user))

		# Projects User can read/create/write, but cannot delete
		frappe.set_user(projects_user)
		self.assertTrue(frappe.has_permission("Issue", "read", user=projects_user))
		self.assertTrue(frappe.has_permission("Issue", "create", user=projects_user))
		self.assertTrue(frappe.has_permission("Issue", "write", user=projects_user))
		self.assertFalse(frappe.has_permission("Issue", "delete", user=projects_user))

		user_issue = self._make_issue(project_a.name, issue_type="Material")
		user_issue.insert()
		self.assertEqual(user_issue.project, project_a.name)

		# User Permission on Project restricts get_issue_list and get_project_issues
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

		scoped = get_issue_list()
		scoped_names = {r["name"] for r in scoped["records"]}
		self.assertIn(issue_a.name, scoped_names)
		self.assertNotIn(issue_b.name, scoped_names)

		# Projects Manager can read/create/write, but cannot delete
		frappe.set_user(projects_manager)
		self.assertTrue(frappe.has_permission("Issue", "read", user=projects_manager))
		self.assertTrue(frappe.has_permission("Issue", "create", user=projects_manager))
		self.assertTrue(frappe.has_permission("Issue", "write", user=projects_manager))
		self.assertFalse(frappe.has_permission("Issue", "delete", user=projects_manager))

	def test_project_validation_and_create_permissions(self):
		self._require_issue_fixtures()

		project_a = self._create_project(f"VA-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"VB-{frappe.generate_hash(length=5)}")
		projects_user = self._create_user_with_role("Projects User")
		projects_manager = self._create_user_with_role("Projects Manager")
		unauthorized_user = self._create_user_with_role("Stock User")
		self.addCleanup(frappe.set_user, "Administrator")

		# Missing Project rejected for construction Issue
		frappe.set_user(projects_user)
		missing_proj_issue = self._make_issue(None, issue_type="Safety")
		self.assertRaises(frappe.ValidationError, missing_proj_issue.insert)

		# Invalid / nonexistent Project rejected
		invalid_proj_issue = self._make_issue("NONEXISTENT-PROJ-9999", issue_type="Safety")
		self.assertRaises(frappe.ValidationError, invalid_proj_issue.insert)

		# Unauthorized user (Stock User) cannot create Issue
		frappe.set_user(unauthorized_user)
		unauth_issue = self._make_issue(project_a.name, issue_type="Safety")
		self.assertRaises(frappe.PermissionError, unauth_issue.insert)

		# Projects User with User Permission on project_a cannot create Issue for project_b
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
		cross_proj_issue = self._make_issue(project_b.name, issue_type="Safety")
		self.assertRaises(frappe.PermissionError, cross_proj_issue.insert)

		# Authorized Projects User & Projects Manager can create Issue for accessible project_a
		ok_user_issue = self._make_issue(project_a.name, issue_type="Safety")
		ok_user_issue.insert()
		self.assertEqual(ok_user_issue.project, project_a.name)

		frappe.set_user(projects_manager)
		ok_mgr_issue = self._make_issue(project_a.name, issue_type="Quality")
		ok_mgr_issue.insert()
		self.assertEqual(ok_mgr_issue.project, project_a.name)

	def test_update_issue_unauthorized_project_and_get_project_issues_scoping(self):
		self._require_issue_fixtures()

		project_a = self._create_project(f"UA-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"UB-{frappe.generate_hash(length=5)}")
		projects_user = self._create_user_with_role("Projects User")
		self.addCleanup(frappe.set_user, "Administrator")

		issue_a = self._make_issue(project_a.name, issue_type="Safety")
		issue_a.insert()
		issue_b = self._make_issue(project_b.name, issue_type="Quality")
		issue_b.insert()

		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": projects_user,
				"allow": "Project",
				"for_value": project_a.name,
			}
		).insert(ignore_permissions=True)

		frappe.set_user(projects_user)

		# Updating an existing Issue to reference an unauthorized Project is rejected
		editable_issue = frappe.get_doc("Issue", issue_a.name)
		editable_issue.project = project_b.name
		self.assertRaises(frappe.PermissionError, editable_issue.save)

		# get_project_issues returns accessible Project's issues and hides restricted Project
		res_a = get_project_issues(project_name=project_a.project_name)
		self.assertEqual(res_a["mapped_project"], project_a.name)
		self.assertEqual([r["name"] for r in res_a["issues"]], [issue_a.name])

		res_b = get_project_issues(project_name=project_b.project_name)
		self.assertIsNone(res_b["mapped_project"])
		self.assertEqual(res_b["issues"], [])
