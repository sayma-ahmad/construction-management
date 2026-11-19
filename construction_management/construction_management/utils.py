# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint

CUSTOMIZED_STANDARD_DOCTYPES = ("Material Request", "Item", "Issue", "Issue Type", "Issue Priority")
DOCPERM_FLAG_FIELDS = (
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"share",
	"print",
	"email",
	"select",
)


def ensure_standard_docperms_for_customized_doctypes():
	"""Ensure standard ERPNext DocPerm roles are preserved alongside Custom DocPerm entries.

	Frappe ignores tabDocPerm once any Custom DocPerm exists for a DocType, so keeping only
	Construction Management roles in custom_docperm.json requires copying missing base DocPerm
	rows into Custom DocPerm after fixtures sync.
	"""
	for parent in CUSTOMIZED_STANDARD_DOCTYPES:
		if not frappe.db.exists("Custom DocPerm", {"parent": parent}):
			continue

		for base_perm in frappe.get_all("DocPerm", fields="*", filters={"parent": parent}):
			exists = frappe.db.exists(
				"Custom DocPerm",
				{
					"parent": parent,
					"role": base_perm.role,
					"permlevel": cint(base_perm.permlevel),
					"if_owner": cint(base_perm.if_owner),
				},
			)
			if exists:
				continue

			custom_perm = {
				"doctype": "Custom DocPerm",
				"parent": parent,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": base_perm.role,
				"permlevel": cint(base_perm.permlevel),
				"if_owner": cint(base_perm.if_owner),
			}
			for field in DOCPERM_FLAG_FIELDS:
				custom_perm[field] = cint(base_perm.get(field))
			frappe.get_doc(custom_perm).insert(ignore_permissions=True)


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
