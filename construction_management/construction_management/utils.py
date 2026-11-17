# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import frappe


def resolve_erpnext_project(project_name=None, project_code=None):
	"""Resolve a project name or code to an actual permission-accessible ERPNext Project."""
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
			return matches[0].name

	if project_code:
		matches = frappe.get_list(
			"Project",
			fields=["name"],
			filters={"name": project_code},
			limit_page_length=1,
		)
		if matches:
			return matches[0].name

	return None
