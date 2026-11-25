import json
import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import add_days, flt, getdate, nowdate


PO_CUSTOM_FIELDS = {
	"Purchase Order": [
		{
			"fieldname": "cm_construction_section",
			"fieldtype": "Section Break",
			"label": "Construction Details",
			"insert_after": "supplier",
		},
		{
			"fieldname": "cm_material_request",
			"fieldtype": "Link",
			"options": "Material Request",
			"label": "Material Request Reference",
			"insert_after": "cm_construction_section",
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
}


def setup():
	"""Run after install and migrate: Purchase Order custom fields and property setters."""
	# Remove duplicate cm_project field on Purchase Order if previously created
	if frappe.db.exists("Custom Field", "Purchase Order-cm_project"):
		frappe.delete_doc("Custom Field", "Purchase Order-cm_project", ignore_permissions=True)

	create_custom_fields(PO_CUSTOM_FIELDS)

	# Ensure standard ERPNext 'project' field on Purchase Order is visible in list view and filters
	if not frappe.db.exists("Property Setter", "Purchase Order-project-in_list_view"):
		frappe.make_property_setter({
			"doctype": "Purchase Order",
			"fieldname": "project",
			"property": "in_list_view",
			"value": "1",
			"property_type": "Check",
		})
	if not frappe.db.exists("Property Setter", "Purchase Order-project-in_standard_filter"):
		frappe.make_property_setter({
			"doctype": "Purchase Order",
			"fieldname": "project",
			"property": "in_standard_filter",
			"value": "1",
			"property_type": "Check",
		})


def get_remaining_qty_for_mr_item(mr_item_name, exclude_po_name=None):
	"""Calculate remaining available quantity for a Material Request item across draft and submitted POs."""
	mr_item = frappe.db.get_value(
		"Material Request Item",
		mr_item_name,
		["qty", "parent", "item_code"],
		as_dict=True,
	)
	if not mr_item:
		return 0.0

	conditions = ["poi.material_request_item = %s", "po.docstatus IN (0, 1)"]
	args = [mr_item_name]

	if exclude_po_name:
		conditions.append("po.name != %s")
		args.append(exclude_po_name)

	allocated = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(poi.qty), 0)
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE {' AND '.join(conditions)}
		""",
		args,
	)[0][0]

	return max(0.0, flt(mr_item.qty) - flt(allocated))


def validate_purchase_order(doc, method=None):
	"""Purchase Order validate hook: enforce project sync, MR status, and quantity limits."""
	# Ensure project is synchronized between custom cm_project and standard project
	if doc.get("cm_project") and not doc.get("project"):
		doc.project = doc.cm_project
	elif doc.get("project") and doc.meta.has_field("cm_project"):
		doc.cm_project = doc.project

	project = doc.get("project") or doc.get("cm_project")

	# Validate linked Material Requests (header or items)
	linked_mrs = set()
	if doc.get("cm_material_request"):
		linked_mrs.add(doc.get("cm_material_request"))
	for item in doc.get("items", []):
		if item.get("material_request"):
			linked_mrs.add(item.get("material_request"))

	for mr_name in linked_mrs:
		if not frappe.db.exists("Material Request", mr_name):
			frappe.throw(_("Material Request {0} not found.").format(mr_name))

		mr = frappe.db.get_value(
			"Material Request",
			mr_name,
			["docstatus", "material_request_type", "status"]
			+ (["cm_project"] if frappe.db.has_column("Material Request", "cm_project") else []),
			as_dict=True,
		)
		if mr.docstatus != 1:
			frappe.throw(
				_("Material Request {0} is not submitted. Only submitted Material Requests can be linked to Purchase Orders.").format(mr_name)
			)
		if mr.material_request_type != "Purchase":
			frappe.throw(
				_("Material Request {0} is of type {1}. Only 'Purchase' type Material Requests can be linked to Purchase Orders.").format(
					mr_name, mr.material_request_type
				)
			)
		if mr.status in ("Stopped", "Cancelled"):
			frappe.throw(
				_("Material Request {0} is {1} and cannot be processed.").format(mr_name, mr.status)
			)

		mr_project = mr.get("cm_project")
		if not mr_project:
			# Look up project from child items
			mr_project = frappe.db.get_value(
				"Material Request Item",
				{"parent": mr_name, "project": ["is", "set"]},
				"project",
			)
		if mr_project and project and mr_project != project:
			frappe.throw(
				_("Material Request {0} belongs to Project {1}, which does not match Purchase Order Project {2}.").format(
					mr_name, mr_project, project
				)
			)

	# Aggregate quantities in current PO by material_request_item to handle split rows
	current_po_item_qtys = {}
	for idx, item in enumerate(doc.get("items", []), start=1):
		# Validate positive quantity
		if flt(item.get("qty", 0)) <= 0:
			frappe.throw(
				_("Row #{0}: Quantity must be greater than zero for item {1}").format(
					item.idx or idx, frappe.bold(item.get("item_code") or "")
				)
			)

		# Sync project down to item lines for ERPNext accounting & cost tracking
		if project and not item.get("project"):
			item.project = project
		elif item.get("project") and project and item.get("project") != project:
			frappe.throw(
				_("Row #{0}: Item Project {1} does not match Purchase Order Project {2}.").format(
					item.idx or idx, item.get("project"), project
				)
			)

		# Auto-populate construction material type and grade from Item master if not set
		if item.get("item_code") and (not item.get("cm_material_type") or not item.get("cm_material_grade")):
			mat_type, mat_grade = frappe.db.get_value(
				"Item", item.item_code, ["cm_material_type", "cm_material_grade"]
			) or (None, None)
			if mat_type and not item.get("cm_material_type"):
				item.cm_material_type = mat_type
			if mat_grade and not item.get("cm_material_grade"):
				item.cm_material_grade = mat_grade

		# Auto-link material_request_item if material_request is present but item row is not set
		if item.get("material_request") and not item.get("material_request_item"):
			item.material_request_item = frappe.db.get_value(
				"Material Request Item",
				{"parent": item.material_request, "item_code": item.item_code},
				"name",
			)

		mri = item.get("material_request_item")
		if mri:
			current_po_item_qtys[mri] = current_po_item_qtys.get(mri, 0.0) + flt(item.get("qty", 0))

	# Validate remaining quantities against Material Request items across other draft & submitted POs
	for mri, total_qty in current_po_item_qtys.items():
		mr_item_data = frappe.db.get_value(
			"Material Request Item",
			mri,
			["qty", "parent", "item_code"],
			as_dict=True,
		)
		if not mr_item_data:
			continue

		rem_allowed = get_remaining_qty_for_mr_item(mri, exclude_po_name=doc.name)
		if rem_allowed <= 0.0:
			frappe.throw(
				_("Item {0} on Material Request {1} has already been fully ordered in other Purchase Orders.").format(
					mr_item_data.item_code, mr_item_data.parent
				),
				frappe.ValidationError,
			)
		if total_qty > rem_allowed:
			frappe.throw(
				_("Total quantity {0} for item {1} exceeds remaining allowed quantity ({2}) on Material Request {3}.").format(
					total_qty, mr_item_data.item_code, rem_allowed, mr_item_data.parent
				),
				frappe.ValidationError,
			)


@frappe.whitelist()
def get_purchase_orders(project=None, status=None, supplier=None, search=None, start=0, page_length=20):
	"""Return purchase orders formatted for the Construction Management procurement screen with permissions and pagination."""
	if not frappe.has_permission("Purchase Order", "read"):
		frappe.throw(_("Not permitted to view Purchase Orders"), frappe.PermissionError)

	start = max(0, frappe.utils.cint(start))
	page_length = min(max(1, frappe.utils.cint(page_length) or 20), 100)

	filters = {}
	if project:
		if not frappe.has_permission("Project", "read", project):
			frappe.throw(_("Not permitted to access Project {0}").format(project), frappe.PermissionError)
		filters["project"] = project
	if status:
		filters["status"] = status
	if supplier:
		filters["supplier"] = supplier

	fields = [
		"name",
		"title",
		"supplier",
		"supplier_name",
		"project",
		"cm_material_request",
		"cm_delivery_site",
		"cm_delivery_contact",
		"transaction_date",
		"schedule_date",
		"grand_total",
		"currency",
		"status",
		"docstatus",
		"modified",
	]
	if frappe.db.has_column("Purchase Order", "cm_project"):
		fields.append("cm_project")

	or_filters = None
	if search:
		term = search.strip()
		like = f"%{term}%"
		or_filters = [
			["Purchase Order", "name", "like", like],
			["Purchase Order", "title", "like", like],
			["Purchase Order", "supplier", "like", like],
			["Purchase Order", "supplier_name", "like", like],
			["Purchase Order", "project", "like", like],
		]

	# Use frappe.get_list to enforce role and User Permissions
	orders = frappe.get_list(
		"Purchase Order",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="modified desc",
		start=start,
		page_length=page_length,
	)

	count_rows = frappe.get_list(
		"Purchase Order",
		filters=filters,
		or_filters=or_filters,
		fields=["count(name) as total"],
	)
	total = count_rows[0].total if count_rows else len(orders)

	if not orders:
		return {
			"orders": [],
			"total": 0,
			"start": start,
			"page_length": page_length,
		}

	po_names = [po.name for po in orders]
	items = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": ["in", po_names]},
		fields=["parent", "item_code", "item_name", "qty", "stock_uom", "rate", "amount", "material_request", "material_request_item"],
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

		proj_ref = po.get("project") or po.get("cm_project") or ""
		proj_name = frappe.db.get_value("Project", proj_ref, "project_name") if proj_ref else ""

		# Material request link from header or first item line
		mr_ref = po.get("cm_material_request") or ""
		if not mr_ref and po_items and po_items[0].get("material_request"):
			mr_ref = po_items[0]["material_request"]

		result.append(
			{
				"name": po.name,
				"title": po.title if po.title and po.title != po.supplier_name else "",
				"supplier": po.supplier,
				"supplier_name": po.supplier_name or po.supplier,
				"project": proj_ref,
				"project_name": proj_name or proj_ref,
				"material_request": mr_ref,
				"delivery_site": po.get("cm_delivery_site") or "",
				"delivery_contact": po.get("cm_delivery_contact") or "",
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

	return {
		"orders": result,
		"total": total,
		"start": start,
		"page_length": page_length,
	}


@frappe.whitelist()
def get_material_requests_for_project(project=None):
	"""Return submitted/open Material Requests of type Purchase with unfulfilled balance for a project."""
	if not frappe.has_permission("Material Request", "read"):
		frappe.throw(_("Not permitted to view Material Requests"), frappe.PermissionError)

	if project and not frappe.has_permission("Project", "read", project):
		frappe.throw(_("Not permitted to access Project {0}").format(project), frappe.PermissionError)

	filters = [
		["Material Request", "material_request_type", "=", "Purchase"],
		["Material Request", "docstatus", "=", 1],
		["Material Request", "status", "not in", ["Stopped", "Cancelled", "Ordered"]],
	]

	if project:
		matching_names = set()
		if frappe.db.has_column("Material Request", "cm_project"):
			matching_names.update(
				frappe.get_list("Material Request", filters={"cm_project": project}, pluck="name", limit_page_length=0)
			)
		matching_names.update(
			frappe.get_list(
				"Material Request",
				filters=[["Material Request Item", "project", "=", project]],
				pluck="name",
				distinct=True,
				limit_page_length=0,
			)
		)
		if not matching_names:
			return []
		filters.append(["Material Request", "name", "in", list(matching_names)])

	fields = ["name", "transaction_date", "schedule_date", "status", "per_ordered"]
	if frappe.db.has_column("Material Request", "cm_project"):
		fields.append("cm_project")

	requests = frappe.get_list(
		"Material Request",
		filters=filters,
		fields=fields,
		order_by="modified desc",
		limit_page_length=100,
	)

	valid_requests = []
	for mr in requests:
		items = frappe.get_all(
			"Material Request Item",
			filters={"parent": mr.name},
			fields=["name", "item_code", "item_name", "qty", "ordered_qty", "stock_uom", "project"],
		)
		# Calculate remaining quantities taking both draft and submitted POs into account
		unfulfilled_items = []
		for it in items:
			rem_qty = get_remaining_qty_for_mr_item(it.name)
			if rem_qty > 0:
				it["remaining_qty"] = rem_qty
				unfulfilled_items.append(it)

		if not unfulfilled_items:
			continue

		mr["items"] = unfulfilled_items
		mr["items_count"] = len(unfulfilled_items)
		first_item_proj = items[0].get("project") if items else ""
		mr["project"] = mr.get("cm_project") or first_item_proj or project or ""
		valid_requests.append(mr)

	return valid_requests


@frappe.whitelist()
def get_material_request_details(material_request):
	"""Return material request header and unfulfilled items for populating a new Purchase Order."""
	if not frappe.has_permission("Material Request", "read"):
		frappe.throw(_("Not permitted to view Material Requests"), frappe.PermissionError)

	if not frappe.has_permission("Material Request", "read", material_request):
		frappe.throw(
			_("Not permitted to view Material Request {0}").format(material_request),
			frappe.PermissionError,
		)

	if not frappe.db.exists("Material Request", material_request):
		frappe.throw(_("Material Request {0} not found").format(material_request))

	mr = frappe.get_doc("Material Request", material_request)
	if mr.docstatus != 1:
		frappe.throw(_("Material Request {0} is not submitted").format(material_request))
	if mr.material_request_type != "Purchase":
		frappe.throw(_("Material Request {0} is not of type Purchase").format(material_request))
	if mr.status in ("Stopped", "Cancelled"):
		frappe.throw(_("Material Request {0} is {1} and cannot be processed").format(material_request, mr.status))

	project = mr.get("cm_project") or ""
	if not project:
		for it in mr.items:
			if it.get("project"):
				project = it.project
				break

	if project and not frappe.has_permission("Project", "read", project):
		frappe.throw(_("Not permitted to access Project {0}").format(project), frappe.PermissionError)

	items = []
	for it in mr.items:
		remaining_qty = get_remaining_qty_for_mr_item(it.name)

		# Only return items that still have remaining quantity to order
		if remaining_qty > 0:
			items.append(
				{
					"item_code": it.item_code,
					"item_name": it.item_name,
					"qty": remaining_qty,
					"requested_qty": flt(it.qty),
					"ordered_qty": flt(it.ordered_qty),
					"remaining_qty": remaining_qty,
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
def material_request_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query for Material Request filtered by project and open unfulfilled balance."""
	if not frappe.has_permission("Material Request", "read"):
		return []

	project = filters.get("project") if isinstance(filters, dict) else None

	valid_mrs = get_material_requests_for_project(project=project)
	if not valid_mrs:
		return []

	valid_names = [mr["name"] for mr in valid_mrs]
	if txt:
		txt_lower = txt.lower()
		valid_names = [name for name in valid_names if txt_lower in name.lower()]

	start_idx = int(start or 0)
	page_length = int(page_len or 20)
	return [[name, name] for name in valid_names[start_idx : start_idx + page_length]]


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
	if not frappe.has_permission("Purchase Order", "create"):
		frappe.throw(_("Not permitted to create Purchase Orders"), frappe.PermissionError)

	if frappe.utils.cint(submit) and not frappe.has_permission("Purchase Order", "submit"):
		frappe.throw(_("Not permitted to submit Purchase Orders"), frappe.PermissionError)

	if project and not frappe.has_permission("Project", "read", project):
		frappe.throw(_("Not permitted to access Project {0}").format(project), frappe.PermissionError)

	if material_request and not frappe.has_permission("Material Request", "read", material_request):
		frappe.throw(_("Not permitted to access Material Request {0}").format(material_request), frappe.PermissionError)

	if isinstance(items, str):
		items = json.loads(items)

	if not items:
		frappe.throw(_("At least one item is required to create a Purchase Order."))

	company = frappe.db.get_value("Project", project, "company") or frappe.db.get_value(
		"Company", {}, "name"
	)
	if not company:
		frappe.throw(_("No company found. Please ensure a Company is set up in ERPNext."))

	po_dict = {
		"doctype": "Purchase Order",
		"company": company,
		"supplier": supplier,
		"transaction_date": nowdate(),
		"schedule_date": required_date or add_days(nowdate(), 7),
		"project": project,
		"cm_material_request": material_request or "",
		"cm_delivery_site": delivery_site or "",
		"cm_delivery_contact": delivery_contact or "",
		"items": [],
	}
	if frappe.db.has_column("Purchase Order", "cm_project"):
		po_dict["cm_project"] = project

	po = frappe.get_doc(po_dict)

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

		# Auto-resolve warehouse if item is a stock item
		warehouse = it.get("warehouse")
		if not warehouse:
			warehouse = frappe.db.get_value(
				"Item Default",
				{"parent": it.get("item_code"), "company": company},
				"default_warehouse",
			)
		if not warehouse:
			warehouse = frappe.db.get_value(
				"Warehouse",
				{"company": company, "is_group": 0},
				"name",
			)
		if not warehouse:
			warehouse = frappe.db.get_value(
				"Warehouse",
				{"is_group": 0},
				"name",
			)
		if warehouse:
			row["warehouse"] = warehouse

		# Item-level Material Request linkage
		mr_ref = it.get("material_request") or material_request
		mr_item_ref = it.get("material_request_item")

		if mr_ref and not mr_item_ref:
			# Auto-lookup material_request_item from parent MR if not explicitly provided
			mr_item_ref = frappe.db.get_value(
				"Material Request Item",
				{"parent": mr_ref, "item_code": it.get("item_code")},
				"name",
			)

		if mr_ref:
			row["material_request"] = mr_ref
		if mr_item_ref:
			row["material_request_item"] = mr_item_ref

		po.append("items", row)

	po.insert()

	if frappe.utils.cint(submit):
		po.submit()

	return po.as_dict()


def create_sample_purchase_orders():
	"""Insert the sample construction procurement records (Material Requests, Purchase Orders,
	Purchase Receipts) through the shared US-18 sample data generator. Run manually:
	bench --site <site> execute construction_management.purchase_orders.create_sample_purchase_orders
	"""
	from construction_management.demo_data import create_sample_data

	setup()
	return create_sample_data()
