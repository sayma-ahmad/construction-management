# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

from construction_management.construction_management.utils import count_permitted, resolve_erpnext_project


def setup():
	"""Run after install and migrate: preserve legacy custom_project values into cm_project."""
	migrate_legacy_custom_project_to_cm_project()


def migrate_legacy_custom_project_to_cm_project():
	"""Idempotently copy legacy custom_project values into cm_project and remove duplicate field."""
	if frappe.db.has_column("Material Request", "custom_project") and frappe.db.has_column(
		"Material Request", "cm_project"
	):
		frappe.db.sql(
			"""
			UPDATE `tabMaterial Request`
			SET `cm_project` = `custom_project`
			WHERE COALESCE(`cm_project`, '') = ''
			  AND COALESCE(`custom_project`, '') != ''
			"""
		)
		frappe.db.sql(
			"""
			UPDATE `tabMaterial Request Item` AS mri
			INNER JOIN `tabMaterial Request` AS mr ON mr.`name` = mri.`parent`
			SET mri.`project` = mr.`cm_project`
			WHERE COALESCE(mri.`project`, '') = ''
			  AND COALESCE(mr.`cm_project`, '') != ''
			"""
		)

	if frappe.db.exists("Custom Field", "Material Request-custom_project"):
		frappe.delete_doc("Custom Field", "Material Request-custom_project", ignore_permissions=True)


def validate_construction_material_request(doc, method=None):
	"""Validate construction-specific fields, quantities, and project consistency on Material Request."""
	_set_and_validate_requested_by(doc)

	for row in doc.get("items") or []:
		if flt(row.get("qty")) <= 0:
			frappe.throw(_("Row #{0}: Quantity must be greater than 0.").format(row.idx))

	cm_project = doc.get("cm_project")
	custom_task = doc.get("custom_task")
	custom_dpr = doc.get("custom_dpr")

	if custom_task and not cm_project:
		frappe.throw(_("Please select a Project when a Task is specified."))

	if custom_task and cm_project:
		task_project = frappe.db.get_value("Task", custom_task, "project")
		if task_project != cm_project:
			if task_project:
				frappe.throw(
					_("Task {0} belongs to Project {1}, not {2}.").format(
						custom_task, task_project, cm_project
					)
				)
			frappe.throw(
				_("Task {0} is not linked to Project {1}.").format(custom_task, cm_project)
			)

	if custom_dpr:
		if not cm_project:
			frappe.throw(_("Please select a Project when a Daily Progress Report is linked."))
		dpr_project = frappe.db.get_value("Daily Progress Report", custom_dpr, "project")
		if dpr_project != cm_project:
			frappe.throw(
				_("Daily Progress Report {0} belongs to Project {1}, not {2}.").format(
					custom_dpr, dpr_project, cm_project
				)
			)

	if cm_project:
		for row in doc.get("items") or []:
			row_project = row.get("project")
			if row_project and row_project != cm_project:
				frappe.throw(
					_("Row #{0}: Item Project {1} does not match Material Request Project {2}.").format(
						row.idx, row_project, cm_project
					)
				)
			if not row_project:
				row.project = cm_project


def _set_and_validate_requested_by(doc):
	"""Always set custom_requested_by from session user on creation and prevent tampering."""
	if doc.is_new():
		doc.set("custom_requested_by", frappe.session.user)
		return

	previous = doc.get_doc_before_save()
	if previous and doc.get("custom_requested_by") != previous.get("custom_requested_by"):
		frappe.throw(
			_("Requested By cannot be changed after creation."),
			frappe.PermissionError,
		)


def _get_project_matched_mr_names(project):
	"""Return permitted Material Request names matching parent cm_project or child item project."""
	parent_matches = set(
		frappe.get_list(
			"Material Request",
			filters={"cm_project": project},
			pluck="name",
			limit_page_length=0,
		)
	)

	child_matches = set(
		frappe.get_list(
			"Material Request",
			filters=[["Material Request Item", "project", "=", project]],
			pluck="name",
			distinct=True,
			limit_page_length=0,
		)
	)

	return list(parent_matches | child_matches)


def _attach_resolved_projects(records):
	"""Populate display `project` from parent cm_project or permitted child item projects."""
	missing_parent_names = [row["name"] for row in records if not row.get("cm_project")]
	child_project_map = {}
	if missing_parent_names:
		item_rows = frappe.get_all(
			"Material Request Item",
			filters={"parent": ["in", missing_parent_names], "project": ["is", "set"]},
			fields=["parent", "project"],
			order_by="idx asc",
		)
		for item in item_rows:
			child_project_map.setdefault(item.parent, [])
			if item.project not in child_project_map[item.parent]:
				child_project_map[item.parent].append(item.project)

	for row in records:
		if row.get("cm_project"):
			row["project"] = row["cm_project"]
		else:
			row["project"] = ", ".join(child_project_map.get(row["name"], []))


@frappe.whitelist()
def get_material_requisition_list(filters=None, search=None, start=0, page_length=20):
	"""Return permission-filtered Material Requests for the construction listing page."""
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	filters = filters or {}

	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 20, 1), 100)

	query_filters = {}
	if filters.get("project"):
		matched_names = _get_project_matched_mr_names(filters["project"])
		if not matched_names:
			return {
				"records": [],
				"total": 0,
				"start": start,
				"page_length": page_length,
			}
		query_filters["name"] = ["in", matched_names]

	if filters.get("material_request_type"):
		query_filters["material_request_type"] = filters["material_request_type"]
	if filters.get("status"):
		query_filters["status"] = filters["status"]
	if filters.get("priority"):
		query_filters["custom_priority"] = filters["priority"]

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	if from_date and to_date:
		query_filters["transaction_date"] = ["between", [from_date, to_date]]
	elif from_date:
		query_filters["transaction_date"] = [">=", from_date]
	elif to_date:
		query_filters["transaction_date"] = ["<=", to_date]

	or_filters = None
	search_term = (search or "").strip()
	if search_term:
		like = f"%{search_term}%"
		or_filters = [
			["Material Request", "name", "like", like],
			["Material Request", "title", "like", like],
			["Material Request", "cm_project", "like", like],
			["Material Request", "custom_site_location", "like", like],
		]

	records = frappe.get_list(
		"Material Request",
		fields=[
			"name",
			"title",
			"material_request_type",
			"transaction_date",
			"schedule_date",
			"status",
			"per_ordered",
			"per_received",
			"cm_project",
			"custom_task",
			"custom_site_location",
			"custom_priority",
			"custom_requested_by",
			"docstatus",
		],
		filters=query_filters,
		or_filters=or_filters,
		order_by="transaction_date desc, modified desc",
		start=start,
		page_length=page_length,
	)

	_attach_resolved_projects(records)

	total = count_permitted("Material Request", query_filters, or_filters)

	return {
		"records": records,
		"total": total,
		"start": start,
		"page_length": page_length,
	}


@frappe.whitelist()
def get_project_material_requests(project_name=None, project_code=None):
	"""Find a matching ERPNext Project (if any) and return its permission-filtered Material Requests."""
	matched_project = resolve_erpnext_project(project_name=project_name, project_code=project_code)
	if not matched_project:
		return {"mapped_project": None, "material_requests": []}

	matched_names = _get_project_matched_mr_names(matched_project)
	if not matched_names:
		return {"mapped_project": matched_project, "material_requests": []}

	material_requests = frappe.get_list(
		"Material Request",
		fields=[
			"name",
			"material_request_type",
			"transaction_date",
			"schedule_date",
			"status",
			"custom_priority",
			"custom_site_location",
			"per_ordered",
			"per_received",
			"docstatus",
		],
		filters={"name": ["in", matched_names]},
		order_by="transaction_date desc, modified desc",
		limit_page_length=50,
	)

	return {
		"mapped_project": matched_project,
		"material_requests": material_requests,
	}
