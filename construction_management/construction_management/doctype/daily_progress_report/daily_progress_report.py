# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime

REVIEWER_ROLES = {"System Manager", "Projects Manager"}


class DailyProgressReport(Document):
	"""Controller for Daily Progress Report."""

	def before_insert(self):
		self.review_status = "Draft"
		self.reviewed_by = None
		self.reviewed_on = None

	def validate(self):
		if self.docstatus == 0:
			self.review_status = "Draft"
			self.reviewed_by = None
			self.reviewed_on = None
		self.validate_overall_progress()
		self.validate_task_progress()
		self.validate_manpower()
		self.validate_machinery()

	def before_update_after_submit(self):
		for fieldname in ("review_status", "reviewed_by", "reviewed_on", "review_remarks"):
			if self.has_value_changed(fieldname):
				frappe.throw(
					_("Use the Approve or Request Revision actions to update {0}.").format(
						self.meta.get_label(fieldname)
					),
					frappe.PermissionError,
				)

	def on_submit(self):
		self.db_set("review_status", "Pending Review")

	def before_cancel(self):
		if self.review_status == "Approved" and "System Manager" not in frappe.get_roles(
			frappe.session.user
		):
			frappe.throw(
				_("Approved Daily Progress Reports can only be cancelled by a System Manager."),
				frappe.PermissionError,
			)

	def on_cancel(self):
		self.db_set("review_status", "Cancelled")

	def validate_overall_progress(self):
		"""Ensure manually entered overall progress is within 0-100%."""
		if self.overall_progress is not None and not (0 <= flt(self.overall_progress) <= 100):
			frappe.throw(_("Overall Progress must be between 0% and 100%."))

	def validate_task_progress(self):
		"""Validate task progress percentages and task-project relationships."""
		if self.task_progress and not self.project:
			frappe.throw(_("Please select a Project before adding Task Progress rows."))

		task_names = [row.task for row in self.task_progress if row.task]
		task_projects = {}
		if task_names and self.project:
			tasks = frappe.get_all(
				"Task",
				filters={"name": ["in", list(set(task_names))]},
				fields=["name", "project"],
			)
			task_projects = {t.name: t.project for t in tasks}

		for row in self.task_progress:
			if row.progress_percent is not None and not (0 <= flt(row.progress_percent) <= 100):
				frappe.throw(
					_("Row #{0}: Task Progress (%) must be between 0% and 100%.").format(row.idx)
				)

			if row.task and self.project:
				task_project = task_projects.get(row.task)
				if task_project != self.project:
					if task_project:
						frappe.throw(
							_("Row #{0}: Task {1} belongs to Project {2}, not {3}.").format(
								row.idx, row.task, task_project, self.project
							)
						)
					frappe.throw(
						_("Row #{0}: Task {1} is not linked to Project {2}.").format(
							row.idx, row.task, self.project
						)
					)

	def validate_manpower(self):
		"""Validate manpower worker counts and hours, and update total workers."""
		total_workers = 0
		for row in self.manpower:
			if cint(row.worker_count) <= 0:
				frappe.throw(_("Row #{0}: Worker Count must be greater than 0.").format(row.idx))
			if row.hours_worked is not None and flt(row.hours_worked) < 0:
				frappe.throw(_("Row #{0}: Hours Worked cannot be negative.").format(row.idx))
			total_workers += cint(row.worker_count)

		self.total_workers = total_workers

	def validate_machinery(self):
		"""Validate machinery quantities and hours, and update total machinery units."""
		total_machinery = 0
		for row in self.machinery:
			if cint(row.quantity) <= 0:
				frappe.throw(_("Row #{0}: Machinery Quantity must be greater than 0.").format(row.idx))
			if row.hours_used is not None and flt(row.hours_used) < 0:
				frappe.throw(_("Row #{0}: Hours Used cannot be negative.").format(row.idx))
			total_machinery += cint(row.quantity)

		self.total_machinery = total_machinery


def _validate_reviewer_and_doc(dpr_name):
	"""Verify reviewer role, document permission, and reviewable state."""
	if not (REVIEWER_ROLES & set(frappe.get_roles(frappe.session.user))):
		frappe.throw(
			_("Only System Manager or Projects Manager can review Daily Progress Reports."),
			frappe.PermissionError,
		)

	doc = frappe.get_doc("Daily Progress Report", dpr_name)
	doc.check_permission("read")

	if doc.docstatus != 1:
		frappe.throw(_("Only submitted Daily Progress Reports can be reviewed."))

	if doc.review_status != "Pending Review":
		frappe.throw(
			_("Daily Progress Report {0} cannot be reviewed because its status is {1}.").format(
				doc.name, doc.review_status
			)
		)

	return doc


@frappe.whitelist()
def approve_dpr(dpr_name, review_remarks=None):
	"""Approve a submitted Daily Progress Report in Pending Review status."""
	doc = _validate_reviewer_and_doc(dpr_name)
	reviewed_on = now_datetime()
	remarks = (review_remarks or "").strip() or None

	doc.db_set(
		{
			"review_status": "Approved",
			"reviewed_by": frappe.session.user,
			"reviewed_on": reviewed_on,
			"review_remarks": remarks,
		}
	)

	return {
		"name": doc.name,
		"review_status": "Approved",
		"reviewed_by": frappe.session.user,
		"reviewed_on": reviewed_on,
		"review_remarks": remarks,
	}


@frappe.whitelist()
def request_dpr_revision(dpr_name, review_remarks=None):
	"""Request revision on a submitted Daily Progress Report with mandatory remarks."""
	doc = _validate_reviewer_and_doc(dpr_name)
	remarks = (review_remarks or "").strip()
	if not remarks:
		frappe.throw(_("Review remarks are required when requesting a revision."))

	reviewed_on = now_datetime()
	doc.db_set(
		{
			"review_status": "Revision Requested",
			"reviewed_by": frappe.session.user,
			"reviewed_on": reviewed_on,
			"review_remarks": remarks,
		}
	)

	return {
		"name": doc.name,
		"review_status": "Revision Requested",
		"reviewed_by": frappe.session.user,
		"reviewed_on": reviewed_on,
		"review_remarks": remarks,
	}


@frappe.whitelist()
def get_dpr_list(filters=None, search=None, start=0, page_length=20):
	"""Return permission-filtered Daily Progress Reports for the Desk list page."""
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	filters = filters or {}

	query_filters = {}
	if filters.get("project"):
		query_filters["project"] = filters["project"]
	if filters.get("review_status"):
		query_filters["review_status"] = filters["review_status"]

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	if from_date and to_date:
		query_filters["report_date"] = ["between", [from_date, to_date]]
	elif from_date:
		query_filters["report_date"] = [">=", from_date]
	elif to_date:
		query_filters["report_date"] = ["<=", to_date]

	or_filters = None
	search_term = (search or "").strip()
	if search_term:
		like = f"%{search_term}%"
		or_filters = [
			["Daily Progress Report", "name", "like", like],
			["Daily Progress Report", "project", "like", like],
			["Daily Progress Report", "project_name", "like", like],
			["Daily Progress Report", "site_engineer", "like", like],
		]

	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 20, 1), 100)

	records = frappe.get_list(
		"Daily Progress Report",
		fields=[
			"name",
			"project",
			"project_name",
			"report_date",
			"site_engineer",
			"overall_progress",
			"review_status",
			"docstatus",
		],
		filters=query_filters,
		or_filters=or_filters,
		order_by="report_date desc, modified desc",
		start=start,
		page_length=page_length,
	)

	count_rows = frappe.get_list(
		"Daily Progress Report",
		fields=["count(name) as total"],
		filters=query_filters,
		or_filters=or_filters,
	)
	total = cint(count_rows[0].total) if count_rows else 0

	return {
		"records": records,
		"total": total,
		"start": start,
		"page_length": page_length,
	}


@frappe.whitelist()
def get_project_dprs(project_name=None, project_code=None):
	"""Find a matching ERPNext Project (if any) and return its permission-filtered DPRs."""
	matched_project = None

	if project_name:
		matches = frappe.get_list(
			"Project",
			fields=["name"],
			or_filters=[
				["Project", "name", "=", project_name],
				["Project", "project_name", "=", project_name],
			],
			limit_page_length=1,
		)
		if matches:
			matched_project = matches[0].name

	if not matched_project and project_code:
		matches = frappe.get_list(
			"Project",
			fields=["name"],
			filters={"name": project_code},
			limit_page_length=1,
		)
		if matches:
			matched_project = matches[0].name

	if not matched_project:
		return {"mapped_project": None, "dprs": []}

	dprs = frappe.get_list(
		"Daily Progress Report",
		fields=[
			"name",
			"report_date",
			"overall_progress",
			"review_status",
			"site_engineer",
			"docstatus",
		],
		filters={"project": matched_project},
		order_by="report_date desc, modified desc",
		limit_page_length=50,
	)

	return {
		"mapped_project": matched_project,
		"dprs": dprs,
	}
