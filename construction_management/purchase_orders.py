import json
import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import add_days, flt, getdate, nowdate

from construction_management import materials, vendors

PO_CUSTOM_FIELDS = {
	"Purchase Order": [
		{
			"fieldname": "cm_construction_section",
			"fieldtype": "Section Break",
			"label": "Construction Details",
			"insert_after": "supplier",
		},
		{
			"fieldname": "cm_project",
			"fieldtype": "Link",
			"options": "Project",
			"label": "Construction Project",
			"insert_after": "cm_construction_section",
			"in_standard_filter": 1,
			"in_list_view": 1,
		},
		{
			"fieldname": "cm_material_request",
			"fieldtype": "Link",
			"options": "Material Request",
			"label": "Material Request Reference",
			"insert_after": "cm_project",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "cm_col_break",
			"fieldtype": "Column Break",
			"insert_after": "cm_material_request",
		},
		{
			"fieldname": "cm_delivery_site",
			"fieldtype": "Data",
			"label": "Delivery Site / Location",
			"insert_after": "cm_col_break",
		},
		{
			"fieldname": "cm_delivery_contact",
			"fieldtype": "Data",
			"label": "Site Contact Person",
			"insert_after": "cm_delivery_site",
		},
	],
	"Purchase Order Item": [
		{
			"fieldname": "cm_material_type",
			"fieldtype": "Select",
			"options": "\nCivil\nStructural\nMEP\nFinishing\nConsumable",
			"label": "Material Type",
			"insert_after": "item_name",
		},
		{
			"fieldname": "cm_material_grade",
			"fieldtype": "Data",
			"label": "Material Grade",
			"insert_after": "cm_material_type",
		},
	],
	"Material Request": [
		{
			"fieldname": "cm_project",
			"fieldtype": "Link",
			"options": "Project",
			"label": "Construction Project",
			"insert_after": "customer",
			"in_standard_filter": 1,
			"in_list_view": 1,
		},
	],
}


def setup():
	"""Run after install and migrate: Purchase Order custom fields."""
	create_custom_fields(PO_CUSTOM_FIELDS)


def validate_purchase_order(doc, method=None):
	"""Purchase Order validate hook: sync construction project reference to items and header."""
	# Sync cm_project with standard project field
	if doc.get("cm_project") and not doc.get("project"):
		doc.project = doc.cm_project
	elif doc.get("project") and not doc.get("cm_project"):
		doc.cm_project = doc.project

	project = doc.get("project") or doc.get("cm_project")

	for item in doc.get("items", []):
		# Sync project down to item lines for ERPNext accounting & cost tracking
		if project and not item.get("project"):
			item.project = project

		# Auto-populate construction material type and grade from Item master if not set
		if item.get("item_code") and (not item.get("cm_material_type") or not item.get("cm_material_grade")):
			mat_type, mat_grade = frappe.db.get_value(
				"Item", item.item_code, ["cm_material_type", "cm_material_grade"]
			) or (None, None)
			if mat_type and not item.get("cm_material_type"):
				item.cm_material_type = mat_type
			if mat_grade and not item.get("cm_material_grade"):
				item.cm_material_grade = mat_grade


@frappe.whitelist()
def get_purchase_orders(project=None, status=None, supplier=None, search=None):
	"""Return purchase orders formatted for the Construction Management procurement screen."""
	filters = {}
	if project:
		filters["project"] = project
	if status:
		filters["status"] = status
	if supplier:
		filters["supplier"] = supplier

	fields = [
		"name",
		"supplier",
		"supplier_name",
		"project",
		"cm_project",
		"cm_material_request",
		"cm_delivery_site",
		"transaction_date",
		"schedule_date",
		"grand_total",
		"currency",
		"status",
		"docstatus",
		"modified",
	]

	orders = frappe.get_all(
		"Purchase Order",
		filters=filters,
		fields=fields,
		order_by="modified desc",
		limit=200,
	)

	if not orders:
		return []

	po_names = [po.name for po in orders]
	items = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": ["in", po_names]},
		fields=["parent", "item_code", "item_name", "qty", "stock_uom", "rate", "amount"],
		order_by="idx asc",
	)

	items_by_po = {}
	for item in items:
		items_by_po.setdefault(item.parent, []).append(item)

	result = []
	for po in orders:
		po_items = items_by_po.get(po.name, [])
		item_count = len(po_items)
		item_names = [it.item_name or it.item_code for it in po_items[:3]]
		items_summary = ", ".join(item_names)
		if item_count > 3:
			items_summary += f" +{item_count - 3} more"

		proj_ref = po.cm_project or po.project or ""
		proj_name = frappe.db.get_value("Project", proj_ref, "project_name") if proj_ref else ""

		if search:
			q = search.lower()
			searchable = f"{po.name} {po.supplier_name or ''} {proj_ref} {proj_name} {items_summary}".lower()
			if q not in searchable:
				continue

		result.append(
			{
				"name": po.name,
				"supplier": po.supplier,
				"supplier_name": po.supplier_name or po.supplier,
				"project": proj_ref,
				"project_name": proj_name or proj_ref,
				"material_request": po.cm_material_request or "",
				"delivery_site": po.cm_delivery_site or "",
				"transaction_date": str(po.transaction_date or ""),
				"schedule_date": str(po.schedule_date or ""),
				"grand_total": flt(po.grand_total, 2),
				"currency": po.currency or "INR",
				"status": po.status,
				"docstatus": po.docstatus,
				"item_count": item_count,
				"items_summary": items_summary,
			}
		)

	return result


@frappe.whitelist()
def get_material_requests_for_project(project=None):
	"""Return submitted/open Material Requests of type Purchase for a project."""
	filters = {"material_request_type": "Purchase", "docstatus": ["<", 2]}
	if project:
		# Material Request may link to project via item-level project or header cm_project
		mr_from_items = frappe.db.sql_list(
			"""SELECT DISTINCT parent FROM `tabMaterial Request Item` WHERE project = %s""",
			(project,),
		)
		mr_from_header = []
		if frappe.db.has_column("Material Request", "cm_project"):
			mr_from_header = frappe.db.sql_list(
				"""SELECT name FROM `tabMaterial Request` WHERE cm_project = %s""",
				(project,),
			)
		matching_names = list(set(mr_from_items + mr_from_header))
		if not matching_names:
			return []
		filters["name"] = ["in", matching_names]

	fields = ["name", "transaction_date", "schedule_date", "status"]
	if frappe.db.has_column("Material Request", "cm_project"):
		fields.append("cm_project")

	requests = frappe.get_all(
		"Material Request",
		filters=filters,
		fields=fields,
		order_by="modified desc",
		limit=100,
	)

	for mr in requests:
		items = frappe.get_all(
			"Material Request Item",
			filters={"parent": mr.name},
			fields=["item_code", "item_name", "qty", "stock_uom", "project"],
		)
		mr["items"] = items
		mr["items_count"] = len(items)
		# Ensure project reference is set on mr dictionary for UI
		first_item_proj = items[0].get("project") if items else ""
		mr["project"] = mr.get("cm_project") or first_item_proj or project or ""

	return requests


@frappe.whitelist()
def get_material_request_details(material_request):
	"""Return material request header and items for populating a new Purchase Order."""
	if not frappe.db.exists("Material Request", material_request):
		frappe.throw(_("Material Request {0} not found").format(material_request))

	mr = frappe.get_doc("Material Request", material_request)
	items = []
	project = mr.get("cm_project") or ""
	for it in mr.items:
		if not project and it.get("project"):
			project = it.project
		items.append(
			{
				"item_code": it.item_code,
				"item_name": it.item_name,
				"qty": flt(it.qty) - flt(it.ordered_qty) if flt(it.qty) > flt(it.ordered_qty) else flt(it.qty),
				"stock_uom": it.stock_uom,
				"rate": flt(it.rate),
				"description": it.description,
				"material_request": mr.name,
				"material_request_item": it.name,
				"project": it.get("project") or project,
			}
		)

	return {
		"name": mr.name,
		"project": project,
		"schedule_date": str(mr.schedule_date or ""),
		"items": items,
	}


@frappe.whitelist()
def create_construction_purchase_order(
	project,
	supplier,
	required_date,
	items,
	material_request=None,
	delivery_site=None,
	delivery_contact=None,
	submit=0,
):
	"""Create and optionally submit an ERPNext Purchase Order with construction project references."""
	if isinstance(items, str):
		items = json.loads(items)

	if not items:
		frappe.throw(_("At least one item is required to create a Purchase Order."))

	company = frappe.db.get_value("Project", project, "company") or frappe.db.get_value(
		"Company", {}, "name"
	)
	if not company:
		frappe.throw(_("No company found. Please ensure a Company is set up in ERPNext."))

	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"company": company,
			"supplier": supplier,
			"transaction_date": nowdate(),
			"schedule_date": required_date or add_days(nowdate(), 7),
			"project": project,
			"cm_project": project,
			"cm_material_request": material_request or "",
			"cm_delivery_site": delivery_site or "",
			"cm_delivery_contact": delivery_contact or "",
			"items": [],
		}
	)

	for it in items:
		qty = flt(it.get("qty", 1))
		rate = flt(it.get("rate", 0))
		if qty <= 0:
			frappe.throw(_("Quantity must be greater than zero for item {0}").format(it.get("item_code")))

		row = {
			"item_code": it.get("item_code"),
			"qty": qty,
			"rate": rate,
			"schedule_date": required_date or add_days(nowdate(), 7),
			"project": project,
		}
		if it.get("stock_uom"):
			row["uom"] = it.get("stock_uom")
			row["stock_uom"] = it.get("stock_uom")
		if it.get("material_request"):
			row["material_request"] = it.get("material_request")
		if it.get("material_request_item"):
			row["material_request_item"] = it.get("material_request_item")

		po.append("items", row)

	po.insert(ignore_permissions=True)

	if frappe.utils.cint(submit):
		po.submit()

	return po.as_dict()


def _get_or_create_default_company():
	company = frappe.db.get_value("Company", {}, "name")
	if company:
		return company
	doc = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "TechnoTribes Construction",
			"abbr": "TTC",
			"default_currency": "INR",
			"country": "India",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_sample_projects(company):
	"""Ensure standard sample projects exist in ERPNext Project DocType."""
	sample_projects = [
		{"project_name": "Riverside Apartments", "code": "PRJ-001", "location": "Pune"},
		{"project_name": "Metro Office Tower", "code": "PRJ-002", "location": "Mumbai"},
		{"project_name": "Green Valley Villas", "code": "PRJ-003", "location": "Bengaluru"},
	]
	projects = {}
	for sp in sample_projects:
		p_name = frappe.db.get_value("Project", {"project_name": sp["project_name"]}, "name")
		if not p_name:
			doc = frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": sp["project_name"],
					"company": company,
					"status": "Open",
				}
			)
			doc.insert(ignore_permissions=True)
			p_name = doc.name
		projects[sp["code"]] = p_name
	return projects


def create_sample_purchase_orders():
	"""Insert sample construction Material Requests and Purchase Orders.
	Run manually: bench --site <site> execute construction_management.purchase_orders.create_sample_purchase_orders
	"""
	setup()
	materials.create_sample_materials()
	vendors.create_sample_vendors()

	company = _get_or_create_default_company()
	projects = _ensure_sample_projects(company)
	today = nowdate()

	# Create Sample Material Requests if they don't exist
	mr_riverside_name = None
	riverside_mrs = frappe.db.sql_list(
		"""SELECT DISTINCT parent FROM `tabMaterial Request Item` WHERE project = %s""",
		(projects["PRJ-001"],),
	)
	if riverside_mrs:
		mr_riverside_name = riverside_mrs[0]

	if not mr_riverside_name:
		mr_data = {
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": company,
			"transaction_date": add_days(today, -5),
			"schedule_date": add_days(today, 10),
			"items": [
				{
					"item_code": "CM-CEM-001",
					"qty": 500,
					"schedule_date": add_days(today, 10),
					"project": projects["PRJ-001"],
				},
				{
					"item_code": "CM-STL-001",
					"qty": 15000,
					"schedule_date": add_days(today, 10),
					"project": projects["PRJ-001"],
				},
			],
		}
		if frappe.db.has_column("Material Request", "cm_project"):
			mr_data["cm_project"] = projects["PRJ-001"]

		mr = frappe.get_doc(mr_data)
		mr.insert(ignore_permissions=True)
		mr.submit()
		mr_riverside_name = mr.name

	mr_metro_name = None
	metro_mrs = frappe.db.sql_list(
		"""SELECT DISTINCT parent FROM `tabMaterial Request Item` WHERE project = %s""",
		(projects["PRJ-002"],),
	)
	if metro_mrs:
		mr_metro_name = metro_mrs[0]

	if not mr_metro_name:
		mr2_data = {
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": company,
			"transaction_date": add_days(today, -3),
			"schedule_date": add_days(today, 14),
			"items": [
				{
					"item_code": "CM-ELE-001",
					"qty": 500,
					"schedule_date": add_days(today, 14),
					"project": projects["PRJ-002"],
				},
				{
					"item_code": "CM-PLB-001",
					"qty": 200,
					"schedule_date": add_days(today, 14),
					"project": projects["PRJ-002"],
				},
			],
		}
		if frappe.db.has_column("Material Request", "cm_project"):
			mr2_data["cm_project"] = projects["PRJ-002"]

		mr2 = frappe.get_doc(mr2_data)
		mr2.insert(ignore_permissions=True)
		mr2.submit()
		mr_metro_name = mr2.name

	# Sample Purchase Orders
	sample_pos = [
		{
			"supplier": "Apex Cement Traders",
			"project": projects["PRJ-001"],
			"cm_material_request": mr_riverside_name,
			"cm_delivery_site": "Block A, North Site, Pune",
			"cm_delivery_contact": "Anil Mehta (+91 98220 11001)",
			"schedule_date": add_days(today, 7),
			"submit": 1,
			"items": [
				{
					"item_code": "CM-CEM-001",
					"qty": 300,
					"rate": 380,
					"material_request": mr_riverside_name,
				}
			],
		},
		{
			"supplier": "Ironclad Steel Suppliers",
			"project": projects["PRJ-001"],
			"cm_material_request": mr_riverside_name,
			"cm_delivery_site": "Block B, North Site, Pune",
			"cm_delivery_contact": "Anil Mehta (+91 98220 11002)",
			"schedule_date": add_days(today, 10),
			"submit": 1,
			"items": [
				{
					"item_code": "CM-STL-001",
					"qty": 8000,
					"rate": 65,
					"material_request": mr_riverside_name,
				}
			],
		},
		{
			"supplier": "Brightline Electricals",
			"project": projects["PRJ-002"],
			"cm_material_request": mr_metro_name,
			"cm_delivery_site": "Plot 7, Downtown Commercial, Mumbai",
			"cm_delivery_contact": "Priya Nair (+91 98220 11004)",
			"schedule_date": add_days(today, 12),
			"submit": 0,  # Draft
			"items": [
				{
					"item_code": "CM-ELE-001",
					"qty": 250,
					"rate": 85,
					"material_request": mr_metro_name,
				}
			],
		},
		{
			"supplier": "Riverstone Sand & Aggregates",
			"project": projects["PRJ-003"],
			"cm_material_request": "",
			"cm_delivery_site": "Phase 2, Green Valley, Bengaluru",
			"cm_delivery_contact": "Suresh Patil (+91 98220 11003)",
			"schedule_date": add_days(today, 5),
			"submit": 1,
			"items": [
				{
					"item_code": "CM-AGG-001",
					"qty": 40,
					"rate": 1800,
				},
				{
					"item_code": "CM-AGG-002",
					"qty": 60,
					"rate": 1400,
				},
			],
		},
	]

	for po_data in sample_pos:
		# Check if already exists for this supplier and project
		existing = frappe.db.get_value(
			"Purchase Order",
			{"supplier": po_data["supplier"], "project": po_data["project"]},
			"name",
		)
		if not existing:
			create_construction_purchase_order(
				project=po_data["project"],
				supplier=po_data["supplier"],
				required_date=po_data["schedule_date"],
				items=po_data["items"],
				material_request=po_data.get("cm_material_request"),
				delivery_site=po_data.get("cm_delivery_site"),
				delivery_contact=po_data.get("cm_delivery_contact"),
				submit=po_data.get("submit", 0),
			)
