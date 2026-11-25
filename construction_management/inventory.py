# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import json
import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt, nowdate, nowtime

from construction_management import materials
from construction_management.demo_data import ITEM_RATES

SAMPLE_RECEIPT_MARKER = "[CM-INV:SAMPLE-RECEIPT]"
SAMPLE_TRANSFER_MARKER = "[CM-INV:SAMPLE-TRANSFER]"
MAX_TRANSFER_ROWS = 100

# Standard Construction Warehouse configurations
STANDARD_WAREHOUSES = [
	{
		"warehouse_name": "Central Store",
		"description": "Central Construction Materials Store",
		"is_site_warehouse": 0,
		"warehouse_type": "Stores",
	},
	{
		"warehouse_name": "Site Store",
		"description": "Main Construction Site Store",
		"is_site_warehouse": 1,
		"warehouse_type": "Stores",
	},
	{
		"warehouse_name": "Transit Store",
		"description": "In-Transit Construction Materials Store",
		"is_site_warehouse": 0,
		"warehouse_type": "Transit",
	},
	{
		"warehouse_name": "Scrap Store",
		"description": "Construction Scrap & Salvage Store",
		"is_site_warehouse": 0,
		"warehouse_type": "Scrap",
	},
]

WAREHOUSE_CUSTOM_FIELDS = {
	"Warehouse": [
		{
			"fieldname": "cm_section",
			"fieldtype": "Section Break",
			"label": "Construction Details",
			"insert_after": "is_group",
		},
		{
			"fieldname": "cm_is_site_warehouse",
			"fieldtype": "Check",
			"label": "Is Site Warehouse",
			"insert_after": "cm_section",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "cm_project",
			"fieldtype": "Link",
			"options": "Project",
			"label": "Associated Project",
			"insert_after": "cm_is_site_warehouse",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "cm_site_location",
			"fieldtype": "Data",
			"label": "Site Location / Address",
			"insert_after": "cm_project",
		},
	]
}


def setup(company=None):
	"""Run after install and migrate: configure custom fields and default construction warehouses."""
	create_custom_fields(WAREHOUSE_CUSTOM_FIELDS)
	setup_warehouses(company)


def setup_warehouses(company=None):
	"""Configure standard ERPNext construction warehouses for the company."""
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_default("company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	if not company:
		return []

	abbr = frappe.get_cached_value("Company", company, "abbr")
	parent_warehouse = f"All Warehouses - {abbr}"

	# Ensure parent group warehouse exists
	if not frappe.db.exists("Warehouse", parent_warehouse):
		# Look for any group warehouse for the company
		parent_warehouse = frappe.db.get_value(
			"Warehouse", {"company": company, "is_group": 1}, "name"
		)
		if not parent_warehouse:
			return []

	created = []
	for wh_def in STANDARD_WAREHOUSES:
		wh_name = f"{wh_def['warehouse_name']} - {abbr}"
		if not frappe.db.exists("Warehouse", wh_name):
			doc = frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": wh_def["warehouse_name"],
					"company": company,
					"parent_warehouse": parent_warehouse,
					"is_group": 0,
					"cm_is_site_warehouse": wh_def.get("is_site_warehouse", 0),
				}
			)
			# Only set warehouse_type if the type exists in ERPNext
			if wh_def.get("warehouse_type") and frappe.db.exists(
				"Warehouse Type", wh_def["warehouse_type"]
			):
				doc.warehouse_type = wh_def["warehouse_type"]

			doc.insert(ignore_permissions=True)
			created.append(doc.name)
		else:
			# Update custom fields if not set
			if wh_def.get("is_site_warehouse"):
				frappe.db.set_value(
					"Warehouse", wh_name, "cm_is_site_warehouse", 1, update_modified=False
				)

	return created


def _check_stock_read():
	"""Stock balances (Bin) and materials (Item) must both be readable by the user."""
	if frappe.session.user == "Guest" or not (
		frappe.has_permission("Bin", "read") and frappe.has_permission("Item", "read")
	):
		frappe.throw(_("Not permitted to view stock balances"), frappe.PermissionError)


def _resolve_company(company=None):
	return (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_default("company")
		or frappe.db.get_value("Company", {}, "name")
	)


def _permitted_warehouses(company=None, warehouse=None):
	"""Non-group warehouses of the company that the user may read (User Permissions apply)."""
	filters = {"is_group": 0}
	if company:
		filters["company"] = company
	names = frappe.get_list("Warehouse", filters=filters, pluck="name", limit_page_length=0)
	if warehouse:
		if warehouse not in names:
			frappe.throw(_("Not permitted to view Warehouse {0}").format(warehouse), frappe.PermissionError)
		return [warehouse]
	return names


@frappe.whitelist()
def get_inventory_summary(company=None, warehouse=None, item_group=None, material_type=None, search=None, status=None):
	"""Subtasks 2 & 3: Fetch inventory list, stock summary, material quantities, and availability."""
	_check_stock_read()
	company = _resolve_company(company)
	currency = frappe.get_cached_value("Company", company, "default_currency") or "INR"

	# Build base item filters for active construction materials
	item_filters = {"is_stock_item": 1, "disabled": 0}
	if item_group:
		item_filters["item_group"] = item_group
	if material_type and frappe.db.has_column("Item", "cm_material_type"):
		item_filters["cm_material_type"] = material_type

	# Scope construction materials
	has_cm_category = frappe.db.exists("Item Group", materials.MATERIALS_ITEM_GROUP)
	if has_cm_category and not item_group:
		child_groups = frappe.get_all(
			"Item Group",
			filters={"parent_item_group": materials.MATERIALS_ITEM_GROUP},
			pluck="name",
		)
		if child_groups:
			item_filters["item_group"] = ["in", child_groups + [materials.MATERIALS_ITEM_GROUP]]

	fields = ["name", "item_name", "item_group", "stock_uom"]
	if frappe.db.has_column("Item", "cm_material_type"):
		fields.append("cm_material_type")
	if frappe.db.has_column("Item", "cm_material_grade"):
		fields.append("cm_material_grade")

	items = frappe.get_list("Item", filters=item_filters, fields=fields, limit_page_length=0)
	if not items:
		return {
			"kpis": {
				"total_items": 0,
				"in_stock_items": 0,
				"low_stock_items": 0,
				"out_of_stock_items": 0,
				"total_valuation": 0.0,
				"currency": currency,
				"warehouse_count": 0,
			},
			"items": [],
		}

	item_codes = [it.name for it in items]
	warehouses = _permitted_warehouses(company, warehouse) or [""]

	bins = frappe.get_all(
		"Bin",
		filters={"item_code": ["in", item_codes], "warehouse": ["in", warehouses]},
		fields=[
			"item_code",
			"warehouse",
			"actual_qty",
			"reserved_qty",
			"ordered_qty",
			"indented_qty",
			"projected_qty",
			"valuation_rate",
			"stock_value",
		],
		limit_page_length=0,
	)

	# Aggregate stock by item_code
	stock_by_item = {}
	for b in bins:
		code = b.item_code
		if code not in stock_by_item:
			stock_by_item[code] = {
				"actual_qty": 0.0,
				"reserved_qty": 0.0,
				"ordered_qty": 0.0,
				"indented_qty": 0.0,
				"projected_qty": 0.0,
				"stock_value": 0.0,
				"valuation_rate": 0.0,
				"warehouses": set(),
			}
		entry = stock_by_item[code]
		entry["actual_qty"] += flt(b.actual_qty)
		entry["reserved_qty"] += flt(b.reserved_qty)
		entry["ordered_qty"] += flt(b.ordered_qty)
		entry["indented_qty"] += flt(b.indented_qty)
		entry["projected_qty"] += flt(b.projected_qty)
		entry["stock_value"] += flt(b.stock_value)
		if b.warehouse:
			entry["warehouses"].add(b.warehouse)

	for entry in stock_by_item.values():
		if entry["actual_qty"] > 0:
			entry["valuation_rate"] = entry["stock_value"] / entry["actual_qty"]

	# Reorder levels only for the same warehouses as the stock figures
	reorder_levels = {}
	reorders = frappe.get_all(
		"Item Reorder",
		filters={"parent": ["in", item_codes], "warehouse": ["in", warehouses]},
		fields=["parent", "warehouse_reorder_level"],
		limit_page_length=0,
	)
	for r in reorders:
		reorder_levels[r.parent] = reorder_levels.get(r.parent, 0.0) + flt(r.warehouse_reorder_level)

	result_items = []
	total_valuation = 0.0
	in_stock_count = 0
	low_stock_count = 0
	out_of_stock_count = 0

	search_query = (search or "").lower().strip()

	for it in items:
		code = it.name
		name = it.item_name or code

		stock = stock_by_item.get(
			code,
			{
				"actual_qty": 0.0,
				"reserved_qty": 0.0,
				"ordered_qty": 0.0,
				"indented_qty": 0.0,
				"projected_qty": 0.0,
				"stock_value": 0.0,
				"valuation_rate": 0.0,
				"warehouses": set(),
			},
		)

		actual_qty = flt(stock["actual_qty"])
		reserved_qty = flt(stock["reserved_qty"])
		available_qty = max(actual_qty - reserved_qty, 0.0)
		projected_qty = flt(stock["projected_qty"])
		stock_val = flt(stock["stock_value"])
		reorder_lvl = flt(reorder_levels.get(code, 0.0))

		total_valuation += stock_val

		# Determine stock status
		if actual_qty <= 0:
			item_status = "Out of Stock"
			out_of_stock_count += 1
		elif reorder_lvl > 0 and actual_qty < reorder_lvl:
			item_status = "Low Stock"
			low_stock_count += 1
			in_stock_count += 1
		else:
			item_status = "In Stock"
			in_stock_count += 1

		if search_query and search_query not in code.lower() and search_query not in name.lower():
			continue
		if status and status != "All" and item_status.lower() != status.lower():
			continue

		result_items.append(
			{
				"item_code": code,
				"item_name": name,
				"item_group": it.item_group,
				"material_type": it.get("cm_material_type") or "",
				"material_grade": it.get("cm_material_grade") or "",
				"stock_uom": it.stock_uom,
				"actual_qty": actual_qty,
				"reserved_qty": reserved_qty,
				"available_qty": available_qty,
				"projected_qty": projected_qty,
				"ordered_qty": flt(stock["ordered_qty"]),
				"reorder_level": reorder_lvl,
				"valuation_rate": flt(stock["valuation_rate"]),
				"stock_value": stock_val,
				"status": item_status,
				"warehouse_count": len(stock["warehouses"]),
			}
		)

	active_warehouses_count = len(
		frappe.get_list(
			"Warehouse",
			filters={"company": company, "is_group": 0, "disabled": 0},
			pluck="name",
			limit_page_length=0,
		)
	)

	return {
		"kpis": {
			"total_items": len(items),
			"in_stock_items": in_stock_count,
			"low_stock_items": low_stock_count,
			"out_of_stock_items": out_of_stock_count,
			"total_valuation": round(total_valuation, 2),
			"currency": currency,
			"warehouse_count": active_warehouses_count,
		},
		"items": result_items,
	}


@frappe.whitelist()
def get_warehouse_stock_breakdown(company=None, warehouse=None, item_code=None):
	"""Subtasks 2 & 3: Detailed per-warehouse material availability breakdown."""
	_check_stock_read()
	company = _resolve_company(company)

	wh_filters = {"is_group": 0}
	if company:
		wh_filters["company"] = company
	if warehouse:
		wh_filters["name"] = warehouse

	wh_fields = ["name", "warehouse_name", "company"]
	if frappe.db.has_column("Warehouse", "cm_is_site_warehouse"):
		wh_fields.append("cm_is_site_warehouse")
	if frappe.db.has_column("Warehouse", "cm_project"):
		wh_fields.append("cm_project")
	if frappe.db.has_column("Warehouse", "cm_site_location"):
		wh_fields.append("cm_site_location")

	warehouses = frappe.get_list("Warehouse", filters=wh_filters, fields=wh_fields, limit_page_length=0)
	if not warehouses:
		return []

	wh_names = [w.name for w in warehouses]
	wh_map = {w.name: w for w in warehouses}

	bin_filters = {"warehouse": ["in", wh_names]}
	if item_code:
		bin_filters["item_code"] = item_code

	bins = frappe.get_all(
		"Bin",
		filters=bin_filters,
		fields=[
			"item_code",
			"warehouse",
			"actual_qty",
			"reserved_qty",
			"projected_qty",
			"valuation_rate",
			"stock_value",
		],
		limit_page_length=0,
	)

	# Fetch item details
	item_codes = list(set([b.item_code for b in bins]))
	item_meta = {}
	if item_codes:
		item_rows = frappe.get_all(
			"Item",
			filters={"name": ["in", item_codes]},
			fields=["name", "item_name", "stock_uom", "item_group"],
		)
		item_meta = {i.name: i for i in item_rows}

	breakdown = []
	for b in bins:
		meta = item_meta.get(b.item_code, {})
		wh_info = wh_map.get(b.warehouse, {})

		actual = flt(b.actual_qty)
		reserved = flt(b.reserved_qty)
		available = max(actual - reserved, 0.0)

		breakdown.append(
			{
				"warehouse": b.warehouse,
				"warehouse_name": wh_info.get("warehouse_name", b.warehouse),
				"is_site_warehouse": wh_info.get("cm_is_site_warehouse", 0),
				"project": wh_info.get("cm_project") or "",
				"site_location": wh_info.get("cm_site_location") or "",
				"item_code": b.item_code,
				"item_name": meta.get("item_name") or b.item_code,
				"item_group": meta.get("item_group") or "",
				"stock_uom": meta.get("stock_uom") or "",
				"actual_qty": actual,
				"reserved_qty": reserved,
				"available_qty": available,
				"projected_qty": flt(b.projected_qty),
				"valuation_rate": flt(b.valuation_rate),
				"stock_value": flt(b.stock_value),
			}
		)

	return breakdown


@frappe.whitelist()
def get_item_availability(item_code, warehouse=None, company=None):
	"""Return real-time available stock for an item in a specific or all permitted warehouses."""
	_check_stock_read()
	if not item_code:
		return {"actual_qty": 0.0, "available_qty": 0.0, "stock_uom": ""}

	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or ""
	warehouses = _permitted_warehouses(company, warehouse) or [""]
	bins = frappe.get_all(
		"Bin",
		filters={"item_code": item_code, "warehouse": ["in", warehouses]},
		fields=["actual_qty", "reserved_qty"],
	)
	actual = sum(flt(b.actual_qty) for b in bins)
	reserved = sum(flt(b.reserved_qty) for b in bins)

	return {
		"item_code": item_code,
		"stock_uom": stock_uom,
		"actual_qty": actual,
		"reserved_qty": reserved,
		"available_qty": max(actual - reserved, 0.0),
	}


@frappe.whitelist()
def get_warehouses(company=None):
	"""Return non-group construction warehouses for the company."""
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_default("company")

	filters = {"is_group": 0}
	if company:
		filters["company"] = company

	fields = ["name", "warehouse_name", "company"]
	if frappe.db.has_column("Warehouse", "cm_is_site_warehouse"):
		fields.append("cm_is_site_warehouse")
	if frappe.db.has_column("Warehouse", "cm_project"):
		fields.append("cm_project")

	return frappe.get_list("Warehouse", filters=filters, fields=fields, order_by="warehouse_name asc", limit_page_length=0)


@frappe.whitelist()
def create_stock_transfer(from_warehouse, to_warehouse, items, project=None, company=None, remarks=None, submit=1):
	"""Subtask 4: Transfer materials between warehouses / project sites via ERPNext Stock Entry."""
	if not frappe.has_permission("Stock Entry", "create"):
		frappe.throw(_("Permission denied to create Stock Entry"), frappe.PermissionError)

	if not from_warehouse or not to_warehouse:
		frappe.throw(_("Both Source Warehouse and Target Warehouse are required."))

	if from_warehouse == to_warehouse:
		frappe.throw(_("Source Warehouse and Target Warehouse cannot be identical."))

	if not frappe.db.exists("Warehouse", from_warehouse):
		frappe.throw(_("Source Warehouse {0} does not exist.").format(from_warehouse))

	if not frappe.db.exists("Warehouse", to_warehouse):
		frappe.throw(_("Target Warehouse {0} does not exist.").format(to_warehouse))

	# Non-group warehouse validation
	if frappe.db.get_value("Warehouse", from_warehouse, "is_group"):
		frappe.throw(
			_("Source Warehouse {0} is a group warehouse. Material transfers must use specific non-group stores.").format(from_warehouse)
		)

	if frappe.db.get_value("Warehouse", to_warehouse, "is_group"):
		frappe.throw(
			_("Target Warehouse {0} is a group warehouse. Material transfers must use specific non-group stores.").format(to_warehouse)
		)

	# Inter-company validation
	wh_from_company = frappe.db.get_value("Warehouse", from_warehouse, "company")
	wh_to_company = frappe.db.get_value("Warehouse", to_warehouse, "company")
	if wh_from_company and wh_to_company and wh_from_company != wh_to_company:
		frappe.throw(_("Source and Target warehouses must belong to the same company."))

	if not company:
		company = wh_from_company
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_default("company")

	if isinstance(items, str):
		try:
			items = json.loads(items)
		except Exception:
			frappe.throw(_("Invalid items payload format."))

	if not items or not isinstance(items, list):
		frappe.throw(_("At least one material item row is required for stock transfer."))
	if len(items) > MAX_TRANSFER_ROWS:
		frappe.throw(_("A stock transfer can have at most {0} rows.").format(MAX_TRANSFER_ROWS))

	if project and not frappe.db.exists("Project", project):
		frappe.throw(_("Project {0} does not exist.").format(project))

	# Multi-row quantity aggregation to prevent split-row bypass
	item_requested_totals = {}
	for idx, it in enumerate(items, 1):
		if not isinstance(it, dict):
			frappe.throw(_("Row #{0}: Invalid item row.").format(idx))
		item_code = it.get("item_code")
		if not item_code or not frappe.db.exists("Item", item_code):
			frappe.throw(_("Row #{0}: Valid Item Code is required.").format(idx))

		qty = flt(it.get("qty"))
		if qty <= 0:
			frappe.throw(_("Row #{0}: Quantity must be greater than zero.").format(idx))

		item_requested_totals[item_code] = item_requested_totals.get(item_code, 0.0) + qty

	# Validate total requested quantity against stock in the source warehouse
	for item_code, total_qty in item_requested_totals.items():
		actual_qty = flt(
			frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": from_warehouse}, "actual_qty")
		)
		if actual_qty < total_qty:
			frappe.throw(
				_("Cannot transfer total {0} {1} of {2}. Available stock in {3} is only {4}.").format(
					total_qty,
					frappe.db.get_value("Item", item_code, "stock_uom"),
					item_code,
					from_warehouse,
					actual_qty,
				)
			)

	# Quantities are always in the material's stock UOM
	entry_items = []
	for it in items:
		item_code = it["item_code"]
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
		entry_items.append(
			{
				"item_code": item_code,
				"qty": flt(it["qty"]),
				"uom": stock_uom,
				"stock_uom": stock_uom,
				"conversion_factor": 1,
				"s_warehouse": from_warehouse,
				"t_warehouse": to_warehouse,
				"project": project or None,
			}
		)

	# Prepare Stock Entry
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": company,
			"from_warehouse": from_warehouse,
			"to_warehouse": to_warehouse,
			"posting_date": nowdate(),
			"posting_time": nowtime(),
			"project": project or None,
			"remarks": remarks or _("Construction Material Transfer from {0} to {1}").format(from_warehouse, to_warehouse),
			"items": entry_items,
		}
	)

	# Auto-resolve Cost Center if required by company setup
	cost_center = frappe.db.get_value("Company", company, "cost_center")
	if cost_center:
		for row in se.items:
			if not row.cost_center:
				row.cost_center = cost_center

	se.insert()

	if cint(submit):
		se.submit()

	return {
		"name": se.name,
		"docstatus": se.docstatus,
		"status": se.get("status") or ("Submitted" if se.docstatus == 1 else "Draft"),
		"from_warehouse": se.from_warehouse,
		"to_warehouse": se.to_warehouse,
		"items_count": len(se.items),
	}


@frappe.whitelist()
def get_stock_transfers(company=None, project=None, limit=25):
	"""Return list of recent stock transfers with their items and statuses."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.PermissionError)

	if not frappe.has_permission("Stock Entry", "read"):
		frappe.throw(_("Permission denied to view stock transfers"), frappe.PermissionError)

	filters = {"purpose": "Material Transfer"}
	if company:
		filters["company"] = company
	if project:
		filters["project"] = project

	entries = frappe.get_list(
		"Stock Entry",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"posting_time",
			"from_warehouse",
			"to_warehouse",
			"project",
			"total_outgoing_value",
			"docstatus",
		],
		order_by="posting_date desc, creation desc",
		limit_page_length=min(cint(limit) or 25, 100),
	)

	if not entries:
		return []

	# Fetch item count per entry
	entry_names = [e.name for e in entries]
	counts = frappe.db.sql(
		"""
		SELECT parent, count(name) as item_count, sum(qty) as total_qty
		FROM `tabStock Entry Detail`
		WHERE parent IN ({0})
		GROUP BY parent
	""".format(", ".join(["%s"] * len(entry_names))),
		tuple(entry_names),
		as_dict=True,
	)
	count_map = {c.parent: c for c in counts}

	for e in entries:
		cm = count_map.get(e.name, {})
		e["item_count"] = cm.get("item_count", 0)
		e["total_qty"] = flt(cm.get("total_qty", 0.0))
		e["status"] = "Submitted" if e.docstatus == 1 else ("Draft" if e.docstatus == 0 else "Cancelled")

	return entries


def create_sample_stock_data(company=None):
	"""Subtask 5: Insert sample construction stock data via ERPNext Material Receipt and initial transfers."""
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_default("company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	if not company:
		frappe.throw(_("No company found to create sample stock data."))

	# 1. Setup custom fields & warehouses
	setup(company)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	central_wh = f"Central Store - {abbr}"
	site_wh = f"Site Store - {abbr}"

	# 2. Ensure sample materials exist
	materials.create_sample_materials()

	# Opening quantities; rates are shared with the US-18 sample data
	sample_stock = [
		("CM-CEM-001", 500),
		("CM-STL-001", 2000),
		("CM-AGG-001", 60),
		("CM-AGG-002", 80),
		("CM-MAS-001", 5000),
		("CM-MAS-002", 1000),
		("CM-PLB-001", 120),
		("CM-ELE-001", 300),
	]
	cost_center = frappe.db.get_value("Company", company, "cost_center")

	receipt_name = _get_sample_entry(company, SAMPLE_RECEIPT_MARKER)
	if not receipt_name:
		items_to_receive = []
		for item_code, qty in sample_stock:
			uom = frappe.db.get_value("Item", item_code, "stock_uom")
			items_to_receive.append(
				{
					"item_code": item_code,
					"qty": qty,
					"uom": uom,
					"stock_uom": uom,
					"conversion_factor": 1,
					"t_warehouse": central_wh,
					"basic_rate": ITEM_RATES[item_code],
					"cost_center": cost_center,
				}
			)
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": company,
				"to_warehouse": central_wh,
				"remarks": f"{SAMPLE_RECEIPT_MARKER} Initial sample stock for construction materials",
				"items": items_to_receive,
			}
		)
		receipt.insert(ignore_permissions=True)
		receipt.submit()
		receipt_name = receipt.name

	transfer_name = _get_sample_entry(company, SAMPLE_TRANSFER_MARKER)
	if not transfer_name:
		result = create_stock_transfer(
			from_warehouse=central_wh,
			to_warehouse=site_wh,
			items=[
				{"item_code": "CM-CEM-001", "qty": 50},
				{"item_code": "CM-STL-001", "qty": 250},
				{"item_code": "CM-MAS-001", "qty": 500},
			],
			project=frappe.db.get_value("Project", {"company": company, "status": "Open"}, "name"),
			company=company,
			remarks=f"{SAMPLE_TRANSFER_MARKER} Sample transfer from Central Store to Site Store",
			submit=1,
		)
		transfer_name = result["name"]

	return {
		"company": company,
		"central_warehouse": central_wh,
		"site_warehouse": site_wh,
		"material_receipt": receipt_name,
		"stock_transfer": transfer_name,
	}


def _get_sample_entry(company, marker):
	"""Return the submitted or draft sample Stock Entry carrying `marker`, so re-runs create nothing."""
	return frappe.db.get_value(
		"Stock Entry",
		{"company": company, "remarks": ["like", f"{marker}%"], "docstatus": ["!=", 2]},
		"name",
	)
