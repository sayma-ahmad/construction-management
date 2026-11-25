# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowdate
from frappe.utils.nestedset import get_descendants_of

from construction_management.construction_management.utils import resolve_erpnext_project
from construction_management.vendors import VENDORS_SUPPLIER_GROUP, is_vendor_type

ALLOWED_STATUSES = ("Open", "In Progress", "On Hold", "Completed", "Cancelled")
ALLOWED_PRIORITIES = ("Low", "Medium", "High", "Urgent")
ALLOWED_STATUS_TRANSITIONS = {
	"Open": {"In Progress", "Cancelled"},
	"In Progress": {"On Hold", "Completed", "Cancelled"},
	"On Hold": {"In Progress", "Cancelled"},
	"Completed": set(),
	"Cancelled": set(),
}
ALLOWED_LIST_FILTERS = ("project", "contractor", "status", "priority")


class ConstructionWorkOrder(Document):
	"""Controller for Construction Work Order."""

	def validate(self):
		self.validate_title()
		self.validate_project()
		self.validate_contractor()
		self.validate_task()
		self.validate_priority()
		self.validate_status_transition()
		self.apply_completion_defaults()
		self.validate_dates()
		self.validate_estimated_cost()

	def validate_title(self):
		"""Ensure Work Order Title is present and non-whitespace."""
		if not (self.title or "").strip():
			frappe.throw(_("Work Order Title is required."))
		self.title = self.title.strip()

	def validate_project(self):
		"""Verify referenced Project exists and keep project_name synced."""
		if not self.project:
			frappe.throw(_("Project is required."))

		project_name = frappe.db.get_value("Project", self.project, "project_name")
		if project_name is None:
			frappe.throw(_("Project {0} does not exist.").format(self.project))
		self.project_name = project_name

	def validate_contractor(self):
		"""Verify referenced Supplier exists, is enabled, and belongs to Construction Vendors."""
		if not self.contractor:
			frappe.throw(_("Assigned Contractor is required."))

		supplier = frappe.db.get_value(
			"Supplier",
			self.contractor,
			["name", "supplier_name", "supplier_group", "disabled", "cm_specialization"],
			as_dict=True,
		)
		if not supplier:
			frappe.throw(_("Contractor {0} does not exist.").format(self.contractor))

		if cint(supplier.disabled):
			frappe.throw(
				_("Contractor {0} is disabled and cannot be assigned to a Work Order.").format(
					self.contractor
				)
			)

		if frappe.db.exists("Supplier Group", VENDORS_SUPPLIER_GROUP) and not (
			supplier.supplier_group == VENDORS_SUPPLIER_GROUP
			or is_vendor_type(supplier.supplier_group)
		):
			frappe.throw(
				_("Contractor {0} must belong to a Construction Vendors Supplier Group.").format(
					self.contractor
				)
			)

		self.contractor_name = supplier.supplier_name
		if not self.specialization and supplier.cm_specialization:
			self.specialization = supplier.cm_specialization

	def validate_task(self):
		"""Verify related Task belongs to the selected Project."""
		if not self.task:
			return

		task_doc = frappe.db.get_value("Task", self.task, ["name", "project"], as_dict=True)
		if not task_doc:
			frappe.throw(_("Related Task {0} does not exist.").format(self.task))

		if task_doc.project != self.project:
			if task_doc.project:
				frappe.throw(
					_("Task {0} belongs to Project {1}, not {2}.").format(
						self.task, task_doc.project, self.project
					)
				)
			frappe.throw(
				_("Task {0} is not linked to Project {1}.").format(self.task, self.project)
			)

	def validate_priority(self):
		"""Ensure Priority is one of the allowed options."""
		if not self.priority:
			self.priority = "Medium"
		elif self.priority not in ALLOWED_PRIORITIES:
			frappe.throw(_("Invalid Priority: {0}.").format(self.priority))

	def validate_status_transition(self):
		"""Enforce valid work order statuses and state transitions server-side."""
		if not self.status:
			self.status = "Open"

		if self.status not in ALLOWED_STATUSES:
			frappe.throw(_("Invalid Status: {0}.").format(self.status))

		if self.is_new():
			return

		previous_doc = self.get_doc_before_save()
		previous_status = (
			previous_doc.status
			if previous_doc
			else frappe.db.get_value(self.doctype, self.name, "status")
		)
		if not previous_status or previous_status == self.status:
			return

		allowed_next = ALLOWED_STATUS_TRANSITIONS.get(previous_status, set())
		if self.status not in allowed_next:
			frappe.throw(
				_("Cannot change Work Order status from {0} to {1}.").format(
					previous_status, self.status
				)
			)

	def apply_completion_defaults(self):
		"""Populate Actual Completion Date with today's date when marked Completed."""
		if self.status == "Completed" and not self.actual_completion_date:
			self.actual_completion_date = nowdate()

	def validate_dates(self):
		"""Ensure planned and actual date ranges are chronological."""
		if (
			self.planned_start_date
			and self.planned_end_date
			and getdate(self.planned_end_date) < getdate(self.planned_start_date)
		):
			frappe.throw(_("Planned End Date cannot be earlier than Planned Start Date."))

		if (
			self.actual_start_date
			and self.actual_completion_date
			and getdate(self.actual_completion_date) < getdate(self.actual_start_date)
		):
			frappe.throw(_("Actual Completion Date cannot be earlier than Actual Start Date."))

	def validate_estimated_cost(self):
		"""Ensure Estimated Cost is non-negative when provided."""
		if self.estimated_cost is not None and flt(self.estimated_cost) < 0:
			frappe.throw(_("Estimated Cost cannot be negative."))


def _ensure_contractor_lookup_permission():
	"""Allow contractor lookup only for authorized project or supplier-reading roles."""
	if not (
		frappe.has_permission("Construction Work Order", "read")
		or frappe.has_permission("Construction Work Order", "create")
		or frappe.has_permission("Construction Work Order", "write")
		or frappe.has_permission("Supplier", "read")
	):
		frappe.throw(
			_("You are not permitted to access contractor options."),
			frappe.PermissionError,
		)


def _get_construction_vendor_group_names():
	"""Return Construction Vendors root and descendant Supplier Group names, or empty list."""
	if not frappe.db.exists("Supplier Group", VENDORS_SUPPLIER_GROUP):
		return []
	child_groups = get_descendants_of(
		"Supplier Group", VENDORS_SUPPLIER_GROUP, ignore_permissions=True
	)
	return [VENDORS_SUPPLIER_GROUP, *(child_groups or [])]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_contractor_options(doctype, txt, searchfield, start, page_len, filters):
	"""Return enabled Suppliers strictly within the Construction Vendors hierarchy."""
	_ensure_contractor_lookup_permission()

	vendor_groups = _get_construction_vendor_group_names()
	if not vendor_groups:
		return []

	query_filters = {
		"disabled": 0,
		"supplier_group": ["in", vendor_groups],
	}

	or_filters = None
	search_term = (txt or "").strip()
	if search_term:
		like = f"%{search_term}%"
		or_filters = [
			["Supplier", "name", "like", like],
			["Supplier", "supplier_name", "like", like],
			["Supplier", "supplier_group", "like", like],
			["Supplier", "cm_specialization", "like", like],
		]

	query_fn = frappe.get_list if frappe.has_permission("Supplier", "read") else frappe.get_all
	return query_fn(
		"Supplier",
		fields=["name", "supplier_name", "supplier_group", "cm_specialization"],
		filters=query_filters,
		or_filters=or_filters,
		order_by="supplier_name asc",
		start=max(cint(start), 0),
		page_length=min(max(cint(page_len) or 20, 1), 100),
		as_list=True,
	)


@frappe.whitelist()
def get_contractor_details(contractor=None):
	"""Return minimal display fields for an eligible enabled Construction Vendor."""
	_ensure_contractor_lookup_permission()

	contractor_name = (contractor or "").strip() if isinstance(contractor, str) else ""
	if not contractor_name:
		return {"valid": False}

	vendor_groups = _get_construction_vendor_group_names()
	if not vendor_groups:
		return {"valid": False}

	query_fn = frappe.get_list if frappe.has_permission("Supplier", "read") else frappe.get_all
	rows = query_fn(
		"Supplier",
		fields=["name", "supplier_name", "cm_specialization"],
		filters={
			"name": contractor_name,
			"disabled": 0,
			"supplier_group": ["in", vendor_groups],
		},
		limit_page_length=1,
	)
	if not rows:
		return {"valid": False}

	row = rows[0]
	return {
		"valid": True,
		"contractor": row.name,
		"contractor_name": row.supplier_name or "",
		"specialization": row.cm_specialization or "",
	}


@frappe.whitelist()
def get_work_order_list(filters=None, search=None, start=0, page_length=20):
	"""Return permission-filtered, paginated Construction Work Orders."""
	if isinstance(filters, str):
		filters = json.loads(filters) if filters.strip() else {}
	if not isinstance(filters, dict):
		filters = {}

	query_filters = {}
	for key in ALLOWED_LIST_FILTERS:
		value = filters.get(key)
		if value:
			query_filters[key] = value

	or_filters = None
	search_term = (search or "").strip()
	if search_term:
		like = f"%{search_term}%"
		or_filters = [
			["Construction Work Order", "name", "like", like],
			["Construction Work Order", "title", "like", like],
			["Construction Work Order", "project", "like", like],
			["Construction Work Order", "project_name", "like", like],
			["Construction Work Order", "contractor", "like", like],
			["Construction Work Order", "contractor_name", "like", like],
		]

	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 20, 1), 100)

	records = frappe.get_list(
		"Construction Work Order",
		fields=[
			"name",
			"title",
			"project",
			"project_name",
			"contractor",
			"contractor_name",
			"status",
			"priority",
			"planned_start_date",
			"planned_end_date",
			"estimated_cost",
		],
		filters=query_filters,
		or_filters=or_filters,
		order_by="modified desc",
		start=start,
		page_length=page_length,
	)

	count_rows = frappe.get_list(
		"Construction Work Order",
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
def get_project_work_orders(project_name=None, project_code=None):
	"""Resolve a Project reference safely and return its permission-filtered Work Orders."""
	matched_project = resolve_erpnext_project(project_name, project_code)
	if not matched_project:
		return {"mapped_project": None, "work_orders": []}

	work_orders = frappe.get_list(
		"Construction Work Order",
		fields=[
			"name",
			"title",
			"contractor",
			"contractor_name",
			"status",
			"priority",
			"planned_end_date",
		],
		filters={"project": matched_project},
		order_by="modified desc",
		limit_page_length=50,
	)

	return {
		"mapped_project": matched_project,
		"work_orders": work_orders,
	}
