# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import frappe

from construction_management.construction_management.utils import resolve_erpnext_project

PHASE_FIELDS = ["name", "phase_name", "project", "sequence", "start_date", "end_date", "status", "progress"]


@frappe.whitelist()
def get_project_phases(project_name=None, project_code=None):
	"""Return Project Phase records for the Phases page, optionally for one project.

	A phase that is In Progress is shown as On Hold while its project is on hold.
	"""
	filters = {}
	mapped_project = None
	if project_name or project_code:
		mapped_project = resolve_erpnext_project(project_name, project_code)
		if not mapped_project:
			return {"mapped_project": None, "phases": []}
		filters["project"] = mapped_project

	phases = frappe.get_list(
		"Project Phase",
		filters=filters,
		fields=PHASE_FIELDS,
		order_by="project asc, sequence asc, start_date asc",
		limit_page_length=0,
	)

	projects = {
		p.name: p
		for p in frappe.get_all(
			"Project",
			filters={"name": ["in", list({ph.project for ph in phases}) or [""]]},
			fields=["name", "project_name", "status"],
		)
	}
	for phase in phases:
		project = projects.get(phase.project, {})
		phase.project_name = project.get("project_name") or phase.project
		phase.display_status = phase.status
		if phase.status == "In Progress" and project.get("status") == "On hold":
			phase.display_status = "On Hold"

	return {"mapped_project": mapped_project, "phases": phases}
