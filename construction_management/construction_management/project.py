# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import getdate, today

PROJECT_CUSTOM_FIELDS = {
	"Project": [
		{
			"fieldname": "cm_project_code",
			"fieldtype": "Data",
			"label": "Project Code",
			"insert_after": "project_name",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "cm_site_location",
			"fieldtype": "Data",
			"label": "Site Location",
			"insert_after": "cm_project_code",
			"in_standard_filter": 1,
		},
	]
}

PROJECT_FIELDS = [
	"name",
	"project_name",
	"cm_project_code",
	"cm_site_location",
	"customer",
	"status",
	"expected_start_date",
	"expected_end_date",
	"percent_complete",
	"notes",
]

STATUS_LABELS = {"On hold": "On Hold", "Completed": "Completed", "Cancelled": "Cancelled"}


def setup():
	"""Run after install and migrate: construction fields on the ERPNext Project form."""
	create_custom_fields(PROJECT_CUSTOM_FIELDS)


@frappe.whitelist()
def get_construction_projects():
	"""Return the ERPNext Projects of the user's default company for the Projects page."""
	filters = {}
	company = frappe.defaults.get_user_default("Company")
	if company:
		filters["company"] = company

	projects = frappe.get_list(
		"Project",
		filters=filters,
		fields=PROJECT_FIELDS,
		order_by="project_name asc",
		limit_page_length=0,
	)
	return [to_construction_project(p) for p in projects]


@frappe.whitelist()
def get_construction_project(key):
	"""Return one ERPNext Project, found by its Project Code or its name, with task counts."""
	matches = frappe.get_list(
		"Project",
		or_filters=[["Project", "cm_project_code", "=", key], ["Project", "name", "=", key]],
		fields=PROJECT_FIELDS,
		limit_page_length=1,
	)
	if not matches:
		return None

	project = to_construction_project(matches[0])
	tasks = frappe.get_all(
		"Task",
		filters={"project": project["id"], "is_group": 0, "status": ["not in", ["Template", "Cancelled"]]},
		pluck="status",
	)
	project["total_tasks"] = len(tasks)
	project["completed_tasks"] = tasks.count("Completed")
	return project


def to_construction_project(project):
	return {
		"id": project.name,
		"name": project.project_name,
		"code": project.cm_project_code or project.name,
		"client": project.customer or "",
		"location": project.cm_site_location or "",
		"status": get_status_label(project),
		"start": project.expected_start_date,
		"end": project.expected_end_date,
		"progress": project.percent_complete,
		"notes": project.notes or "",
	}


def get_status_label(project):
	"""Map the ERPNext Project status to the construction status shown on the pages.

	An Open project is Planning until its expected start date, then In Progress.
	"""
	if project.status in STATUS_LABELS:
		return STATUS_LABELS[project.status]
	if project.expected_start_date and getdate(project.expected_start_date) > getdate(today()):
		return "Planning"
	return "In Progress"
