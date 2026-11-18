# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import cint

from construction_management.construction_management.utils import resolve_erpnext_project

CONSTRUCTION_ISSUE_TYPES = {"Safety", "Quality", "Material", "Equipment", "Design", "Delay", "Other"}


def validate_construction_issue(doc, method=None):
	"""Validate project reference and project access permissions for construction Issues."""
	is_construction_issue = doc.get("issue_type") in CONSTRUCTION_ISSUE_TYPES

	if not doc.project:
		if is_construction_issue:
			frappe.throw(_("Project is required for Construction Issues."))
		return

	if not frappe.db.exists("Project", doc.project):
		frappe.throw(_("Project {0} does not exist.").format(doc.project))

	if not frappe.flags.in_import and not doc.flags.ignore_permissions:
		if not frappe.has_permission("Project", "read", doc=doc.project):
			frappe.throw(
				_("You do not have permission to access Project {0}.").format(doc.project),
				frappe.PermissionError,
			)


def _parse_assignees(raw_assign):
	"""Parse Frappe's native _assign JSON list into a list of user IDs."""
	if not raw_assign:
		return []
	if isinstance(raw_assign, list):
		return raw_assign
	try:
		parsed = json.loads(raw_assign)
		return parsed if isinstance(parsed, list) else []
	except (TypeError, ValueError):
		return []


@frappe.whitelist()
def get_issue_list(filters=None, search=None, start=0, page_length=20):
	"""Return permission-filtered ERPNext Issues for the construction issues page."""
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	filters = filters or {}

	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 20, 1), 100)

	query_filters = {}
	if filters.get("project"):
		query_filters["project"] = filters["project"]
	if filters.get("status"):
		query_filters["status"] = filters["status"]
	if filters.get("priority"):
		query_filters["priority"] = filters["priority"]
	if filters.get("issue_type"):
		query_filters["issue_type"] = filters["issue_type"]

	or_filters = None
	search_term = (search or "").strip()
	if search_term:
		like = f"%{search_term}%"
		or_filters = [
			["Issue", "name", "like", like],
			["Issue", "subject", "like", like],
			["Issue", "project", "like", like],
		]

	records = frappe.get_list(
		"Issue",
		fields=[
			"name",
			"subject",
			"project",
			"issue_type",
			"priority",
			"status",
			"opening_date",
			"modified",
			"owner",
			"_assign",
		],
		filters=query_filters,
		or_filters=or_filters,
		order_by="opening_date desc, modified desc",
		start=start,
		page_length=page_length,
	)

	for row in records:
		row["assigned_to"] = _parse_assignees(row.get("_assign"))

	count_rows = frappe.get_list(
		"Issue",
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
def get_project_issues(project_name=None, project_code=None):
	"""Find a matching ERPNext Project (if any) and return its permission-filtered Issues."""
	matched_project = resolve_erpnext_project(project_name=project_name, project_code=project_code)
	if not matched_project:
		return {"mapped_project": None, "issues": []}

	issues = frappe.get_list(
		"Issue",
		fields=[
			"name",
			"subject",
			"issue_type",
			"priority",
			"status",
			"opening_date",
			"_assign",
		],
		filters={"project": matched_project},
		order_by="opening_date desc, modified desc",
		limit_page_length=50,
	)

	for row in issues:
		row["assigned_to"] = _parse_assignees(row.get("_assign"))

	return {
		"mapped_project": matched_project,
		"issues": issues,
	}
