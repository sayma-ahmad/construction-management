# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import json

import frappe

from construction_management.construction_management.utils import resolve_erpnext_project

TASK_FIELDS = [
	"name",
	"subject",
	"project",
	"status",
	"priority",
	"exp_start_date",
	"exp_end_date",
	"progress",
	"parent_task",
	"_assign",
]


@frappe.whitelist()
def get_construction_tasks(project_name=None, project_code=None):
	"""Return ERPNext Tasks (excluding phase groups and templates) for the Tasks page.

	When a project name or code is given, only the matching ERPNext Project's tasks are returned.
	"""
	filters = {"is_group": 0, "status": ["not in", ["Template", "Cancelled"]]}
	mapped_project = None
	if project_name or project_code:
		mapped_project = resolve_erpnext_project(project_name, project_code)
		if not mapped_project:
			return {"mapped_project": None, "tasks": []}
		filters["project"] = mapped_project

	tasks = frappe.get_list(
		"Task",
		filters=filters,
		fields=TASK_FIELDS,
		order_by="exp_end_date asc, modified desc",
		limit_page_length=0,
	)

	project_names = _names("Project", "project_name", {t.project for t in tasks})
	project_codes = _names("Project", "cm_project_code", {t.project for t in tasks})
	phase_names = _names("Task", "subject", {t.parent_task for t in tasks})
	users = {user for t in tasks for user in json.loads(t._assign or "[]")}
	user_names = _names("User", "full_name", users)

	for task in tasks:
		task.project_name = project_names.get(task.project, task.project)
		task.project_code = project_codes.get(task.project) or task.project
		task.phase = phase_names.get(task.parent_task, "")
		task.assigned_to = ", ".join(user_names.get(u, u) for u in json.loads(task.pop("_assign") or "[]"))

	return {"mapped_project": mapped_project, "tasks": tasks}


def _names(doctype, field, names):
	names = [n for n in names if n]
	if not names:
		return {}
	return dict(frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", field], as_list=True))
