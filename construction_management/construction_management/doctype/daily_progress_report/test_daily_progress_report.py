# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from construction_management.construction_management.doctype.daily_progress_report.daily_progress_report import (
	approve_dpr,
	get_dpr_list,
	get_project_dprs,
	request_dpr_revision,
)


class TestDailyProgressReport(FrappeTestCase):
	"""Tests for Daily Progress Report validations, totals, and lifecycle."""

	def _create_project(self, suffix):
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
				"project_name": f"Test Construction Project {suffix}",
				"company": company or self._get_or_create_company(),
			}
		)
		project.insert(ignore_permissions=True)
		return project

	def _create_task(self, subject, project=None, progress=0):
		task = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project,
				"progress": progress,
			}
		)
		task.insert(ignore_permissions=True)
		return task

	def _make_dpr(self, project, **kwargs):
		data = {
			"doctype": "Daily Progress Report",
			"project": project,
			"report_date": nowdate(),
			"overall_progress": 45,
			"work_completed": "Completed foundation excavation and blinding concrete.",
			"remarks": "Site inspection completed.",
		}
		data.update(kwargs)
		return frappe.get_doc(data)

	def test_valid_draft_creation_and_naming_series(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(project.name)
		dpr.insert()

		current_year = nowdate()[:4]
		self.assertEqual(dpr.docstatus, 0)
		self.assertEqual(dpr.review_status, "Draft")
		self.assertRegex(dpr.name, rf"^DPR-{current_year}-\d{{5}}$")

	def test_submit_and_cancel_review_status(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(project.name)
		dpr.insert()

		dpr.submit()
		dpr.reload()
		self.assertEqual(dpr.docstatus, 1)
		self.assertEqual(dpr.review_status, "Pending Review")

		dpr.cancel()
		dpr.reload()
		self.assertEqual(dpr.docstatus, 2)
		self.assertEqual(dpr.review_status, "Cancelled")

	def test_multiple_dprs_allowed_for_same_project_and_date(self):
		project = self._create_project(frappe.generate_hash(length=6))
		report_date = nowdate()

		dpr_1 = self._make_dpr(project.name, report_date=report_date, shift="Day")
		dpr_1.insert()
		dpr_1.submit()

		dpr_2 = self._make_dpr(project.name, report_date=report_date, shift="Night")
		dpr_2.insert()
		dpr_2.submit()

		self.assertNotEqual(dpr_1.name, dpr_2.name)
		self.assertEqual(dpr_1.docstatus, 1)
		self.assertEqual(dpr_2.docstatus, 1)

	def test_invalid_overall_progress_bounds(self):
		project = self._create_project(frappe.generate_hash(length=6))

		dpr_negative = self._make_dpr(project.name, overall_progress=-1)
		self.assertRaises(frappe.ValidationError, dpr_negative.insert)

		dpr_over_100 = self._make_dpr(project.name, overall_progress=101)
		self.assertRaises(frappe.ValidationError, dpr_over_100.insert)

	def test_invalid_task_progress_bounds(self):
		project = self._create_project(frappe.generate_hash(length=6))
		task = self._create_task("Excavation", project=project.name)

		dpr_negative = self._make_dpr(
			project.name,
			task_progress=[
				{"task": task.name, "progress_percent": -5, "work_done": "Excavation"}
			],
		)
		self.assertRaises(frappe.ValidationError, dpr_negative.insert)

		dpr_over_100 = self._make_dpr(
			project.name,
			task_progress=[
				{"task": task.name, "progress_percent": 105, "work_done": "Excavation"}
			],
		)
		self.assertRaises(frappe.ValidationError, dpr_over_100.insert)

	def test_invalid_manpower_worker_count_and_hours(self):
		project = self._create_project(frappe.generate_hash(length=6))

		dpr_zero_workers = self._make_dpr(
			project.name,
			manpower=[{"trade_or_role": "Mason", "worker_count": 0, "hours_worked": 8}],
		)
		self.assertRaises(frappe.ValidationError, dpr_zero_workers.insert)

		dpr_negative_workers = self._make_dpr(
			project.name,
			manpower=[{"trade_or_role": "Mason", "worker_count": -3, "hours_worked": 8}],
		)
		self.assertRaises(frappe.ValidationError, dpr_negative_workers.insert)

		dpr_negative_hours = self._make_dpr(
			project.name,
			manpower=[{"trade_or_role": "Mason", "worker_count": 4, "hours_worked": -2}],
		)
		self.assertRaises(frappe.ValidationError, dpr_negative_hours.insert)

	def test_invalid_machinery_quantity_and_hours(self):
		project = self._create_project(frappe.generate_hash(length=6))

		dpr_zero_qty = self._make_dpr(
			project.name,
			machinery=[{"equipment_name": "Excavator", "quantity": 0, "hours_used": 6}],
		)
		self.assertRaises(frappe.ValidationError, dpr_zero_qty.insert)

		dpr_negative_qty = self._make_dpr(
			project.name,
			machinery=[{"equipment_name": "Excavator", "quantity": -1, "hours_used": 6}],
		)
		self.assertRaises(frappe.ValidationError, dpr_negative_qty.insert)

		dpr_negative_hours = self._make_dpr(
			project.name,
			machinery=[{"equipment_name": "Excavator", "quantity": 1, "hours_used": -1}],
		)
		self.assertRaises(frappe.ValidationError, dpr_negative_hours.insert)

	def test_task_project_mismatch(self):
		project_a = self._create_project(f"A-{frappe.generate_hash(length=5)}")
		project_b = self._create_project(f"B-{frappe.generate_hash(length=5)}")
		task_b = self._create_task("Project B Task", project=project_b.name)
		task_unlinked = self._create_task("Unlinked Task", project=None)

		dpr_wrong_project = self._make_dpr(
			project_a.name,
			task_progress=[
				{"task": task_b.name, "progress_percent": 50, "work_done": "Footing work"}
			],
		)
		self.assertRaises(frappe.ValidationError, dpr_wrong_project.insert)

		dpr_unlinked_task = self._make_dpr(
			project_a.name,
			task_progress=[
				{"task": task_unlinked.name, "progress_percent": 50, "work_done": "Footing work"}
			],
		)
		self.assertRaises(frappe.ValidationError, dpr_unlinked_task.insert)

	def test_total_workers_and_total_machinery_calculation(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(
			project.name,
			manpower=[
				{"trade_or_role": "Mason", "worker_count": 6, "hours_worked": 8},
				{"trade_or_role": "Helper", "worker_count": 10, "hours_worked": 8},
			],
			machinery=[
				{"equipment_name": "Excavator", "quantity": 2, "hours_used": 7.5},
				{"equipment_name": "Concrete Mixer", "quantity": 3, "hours_used": 6.0},
			],
		)
		dpr.insert()

		self.assertEqual(dpr.total_workers, 16)
		self.assertEqual(dpr.total_machinery, 5)

	def test_erpnext_task_progress_unchanged_after_submit(self):
		project = self._create_project(frappe.generate_hash(length=6))
		task = self._create_task("Column Casting", project=project.name, progress=25)

		dpr = self._make_dpr(
			project.name,
			task_progress=[
				{"task": task.name, "progress_percent": 80, "work_done": "Cast 8 columns"}
			],
		)
		dpr.insert()
		dpr.submit()

		task.reload()
		self.assertEqual(task.progress, 25)

	def _create_user_with_role(self, role):
		email = f"dpr_{role.lower().replace(' ', '_')}_{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "DPR",
				"last_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		)
		user.insert(ignore_permissions=True)
		return user.name

	def test_approve_dpr_as_projects_manager(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(project.name)
		dpr.insert()
		dpr.submit()

		manager = self._create_user_with_role("Projects Manager")
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(manager)

		result = approve_dpr(dpr.name, review_remarks="Verified site progress.")
		dpr.reload()

		self.assertEqual(result["review_status"], "Approved")
		self.assertEqual(dpr.docstatus, 1)
		self.assertEqual(dpr.review_status, "Approved")
		self.assertEqual(dpr.reviewed_by, manager)
		self.assertIsNotNone(dpr.reviewed_on)
		self.assertEqual(dpr.review_remarks, "Verified site progress.")

	def test_request_revision_requires_remarks_and_updates_status(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(project.name)
		dpr.insert()
		dpr.submit()

		manager = self._create_user_with_role("Projects Manager")
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(manager)

		self.assertRaises(frappe.ValidationError, request_dpr_revision, dpr.name, "   ")

		result = request_dpr_revision(dpr.name, "Please attach concrete cube test details.")
		dpr.reload()

		self.assertEqual(result["review_status"], "Revision Requested")
		self.assertEqual(dpr.docstatus, 1)
		self.assertEqual(dpr.review_status, "Revision Requested")
		self.assertEqual(dpr.reviewed_by, manager)
		self.assertIsNotNone(dpr.reviewed_on)
		self.assertEqual(dpr.review_remarks, "Please attach concrete cube test details.")

	def test_unauthorized_user_cannot_review_dpr(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(project.name)
		dpr.insert()
		dpr.submit()

		site_user = self._create_user_with_role("Projects User")
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(site_user)

		self.assertRaises(frappe.PermissionError, approve_dpr, dpr.name, "Looks good")
		self.assertRaises(frappe.PermissionError, request_dpr_revision, dpr.name, "Needs changes")

		dpr.reload()
		self.assertEqual(dpr.review_status, "Pending Review")
		self.assertIsNone(dpr.reviewed_by)

	def test_cannot_review_draft_or_already_reviewed_dpr(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(project.name)
		dpr.insert()

		self.assertRaises(frappe.ValidationError, approve_dpr, dpr.name)

		dpr.submit()
		approve_dpr(dpr.name, "Approved once")

		self.assertRaises(frappe.ValidationError, approve_dpr, dpr.name)
		self.assertRaises(frappe.ValidationError, request_dpr_revision, dpr.name, "Too late")

	def test_cannot_tamper_review_status_after_submit(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(project.name)
		dpr.insert()
		dpr.submit()

		dpr.review_status = "Approved"
		self.assertRaises(frappe.PermissionError, dpr.save)

		dpr.reload()
		dpr.review_remarks = "Tampered remark"
		self.assertRaises(frappe.PermissionError, dpr.save)

	def test_get_dpr_list_filters_search_and_pagination(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		dpr_1 = self._make_dpr(project.name, report_date="2026-11-10")
		dpr_1.insert()
		dpr_1.submit()

		dpr_2 = self._make_dpr(project.name, report_date="2026-11-12")
		dpr_2.insert()

		# Date range filter
		date_res = get_dpr_list(
			filters={"project": project.name, "from_date": "2026-11-11", "to_date": "2026-11-15"}
		)
		self.assertEqual(date_res["total"], 1)
		self.assertEqual(date_res["records"][0]["name"], dpr_2.name)

		# Search filter
		search_res = get_dpr_list(search=dpr_1.name)
		self.assertEqual(search_res["total"], 1)
		self.assertEqual(search_res["records"][0]["name"], dpr_1.name)

		# Pagination
		page_1 = get_dpr_list(filters={"project": project.name}, start=0, page_length=1)
		page_2 = get_dpr_list(filters={"project": project.name}, start=1, page_length=1)
		self.assertEqual(page_1["total"], 2)
		self.assertEqual(len(page_1["records"]), 1)
		self.assertEqual(len(page_2["records"]), 1)
		self.assertNotEqual(page_1["records"][0]["name"], page_2["records"][0]["name"])

	def test_cancellation_permissions_by_role_and_review_status(self):
		project = self._create_project(frappe.generate_hash(length=6))
		dpr = self._make_dpr(project.name)
		dpr.insert()
		dpr.submit()

		projects_user = self._create_user_with_role("Projects User")
		projects_manager = self._create_user_with_role("Projects Manager")
		sys_manager = self._create_user_with_role("System Manager")
		self.addCleanup(frappe.set_user, "Administrator")

		# Projects User cannot cancel any submitted DPR
		frappe.set_user(projects_user)
		self.assertFalse(frappe.has_permission("Daily Progress Report", "cancel", user=projects_user))
		dpr_user_view = frappe.get_doc("Daily Progress Report", dpr.name)
		self.assertRaises(frappe.PermissionError, dpr_user_view.cancel)

		# Projects Manager can cancel a Pending Review DPR
		frappe.set_user(projects_manager)
		self.assertTrue(frappe.has_permission("Daily Progress Report", "cancel", user=projects_manager))
		dpr_mgr_view = frappe.get_doc("Daily Progress Report", dpr.name)
		dpr_mgr_view.cancel()
		dpr_mgr_view.reload()
		self.assertEqual(dpr_mgr_view.docstatus, 2)
		self.assertEqual(dpr_mgr_view.review_status, "Cancelled")

		# Projects Manager cannot cancel an Approved DPR, while System Manager can
		frappe.set_user("Administrator")
		approved_dpr = self._make_dpr(project.name)
		approved_dpr.insert()
		approved_dpr.submit()
		approve_dpr(approved_dpr.name, "Approved for record")

		frappe.set_user(projects_manager)
		approved_mgr_view = frappe.get_doc("Daily Progress Report", approved_dpr.name)
		self.assertRaises(frappe.PermissionError, approved_mgr_view.cancel)

		frappe.set_user(sys_manager)
		approved_sys_view = frappe.get_doc("Daily Progress Report", approved_dpr.name)
		approved_sys_view.cancel()
		approved_sys_view.reload()
		self.assertEqual(approved_sys_view.docstatus, 2)
		self.assertEqual(approved_sys_view.review_status, "Cancelled")

	def test_get_dpr_list_and_get_project_dprs(self):
		suffix = frappe.generate_hash(length=6)
		project = self._create_project(suffix)
		dpr = self._make_dpr(project.name)
		dpr.insert()
		dpr.submit()

		list_res = get_dpr_list(filters={"project": project.name, "review_status": "Pending Review"})
		self.assertEqual(list_res["total"], 1)
		self.assertEqual(list_res["records"][0]["name"], dpr.name)

		mapped_res = get_project_dprs(project_name=project.project_name)
		self.assertEqual(mapped_res["mapped_project"], project.name)
		self.assertEqual(len(mapped_res["dprs"]), 1)
		self.assertEqual(mapped_res["dprs"][0]["name"], dpr.name)

		unmapped_res = get_project_dprs(project_name="Nonexistent Sample Project XYZ", project_code="PRJ-999")
		self.assertIsNone(unmapped_res["mapped_project"])
		self.assertEqual(unmapped_res["dprs"], [])
