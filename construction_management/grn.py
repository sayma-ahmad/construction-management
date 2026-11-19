import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt

# A GRN (Goods Receipt Note) is a standard ERPNext Purchase Receipt.
RECEIVABLE_PO_STATUSES = ["To Receive and Bill", "To Receive"]

GRN_CUSTOM_FIELDS = {
	"Purchase Receipt Item": [
		{
			"fieldname": "cm_ordered_qty",
			"fieldtype": "Float",
			"label": "Ordered Qty",
			"insert_after": "received_qty",
			"read_only": 1,
			"no_copy": 1,
			"in_list_view": 1,
			"columns": 1,
		},
	]
}


def setup():
	"""Run after install and migrate: Purchase Receipt custom fields."""
	create_custom_fields(GRN_CUSTOM_FIELDS)


def validate_purchase_receipt(doc, method=None):
	"""Purchase Receipt validate hook: show the Purchase Order quantity on each received row."""
	po_items = [row.purchase_order_item for row in doc.items if row.get("purchase_order_item")]
	ordered_qty = {}
	if po_items:
		ordered_qty = dict(
			frappe.get_all(
				"Purchase Order Item",
				filters={"name": ["in", po_items]},
				fields=["name", "qty"],
				as_list=True,
			)
		)

	for row in doc.items:
		row.cm_ordered_qty = flt(ordered_qty.get(row.get("purchase_order_item")))


@frappe.whitelist()
def get_grns():
	"""Return Purchase Receipts with their Purchase Orders, warehouses and quantities."""
	receipts = frappe.get_list(
		"Purchase Receipt",
		fields=[
			"name",
			"supplier",
			"supplier_name",
			"posting_date",
			"status",
			"docstatus",
			"is_return",
			"project",
			"set_warehouse",
			"supplier_delivery_note",
		],
		order_by="posting_date desc, creation desc",
		limit_page_length=500,
	)
	if not receipts:
		return []

	items = frappe.get_all(
		"Purchase Receipt Item",
		filters={"parenttype": "Purchase Receipt", "parent": ["in", [r.name for r in receipts]]},
		fields=["parent", "purchase_order", "warehouse", "received_qty", "qty", "rejected_qty"],
	)

	summary = {}
	for item in items:
		row = summary.setdefault(
			item.parent,
			{"purchase_orders": [], "warehouses": [], "item_count": 0, "received_qty": 0, "accepted_qty": 0},
		)
		if item.purchase_order and item.purchase_order not in row["purchase_orders"]:
			row["purchase_orders"].append(item.purchase_order)
		if item.warehouse and item.warehouse not in row["warehouses"]:
			row["warehouses"].append(item.warehouse)
		row["item_count"] += 1
		row["received_qty"] += flt(item.received_qty)
		row["accepted_qty"] += flt(item.qty)

	empty = {"purchase_orders": [], "warehouses": [], "item_count": 0, "received_qty": 0, "accepted_qty": 0}
	return [{**receipt, **summary.get(receipt.name, empty)} for receipt in receipts]


@frappe.whitelist()
def get_purchase_order_items(purchase_order):
	"""Return a submitted Purchase Order's rows with ordered, received and pending quantities."""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")
	if po.docstatus != 1:
		frappe.throw(_("Purchase Order {0} is not submitted.").format(po.name))

	return {
		"supplier": po.supplier,
		"supplier_name": po.supplier_name,
		"project": po.project,
		"set_warehouse": po.set_warehouse,
		"company": po.company,
		"status": po.status,
		"items": [
			{
				"purchase_order_item": row.name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"uom": row.uom,
				"warehouse": row.warehouse,
				"ordered_qty": flt(row.qty),
				"received_qty": flt(row.received_qty),
				"pending_qty": max(flt(row.qty) - flt(row.received_qty), 0),
			}
			for row in po.items
			if not row.delivered_by_supplier
		],
	}


@frappe.whitelist()
def make_grn(purchase_order, items, warehouse=None, posting_date=None, supplier_delivery_note=None):
	"""Create a draft Purchase Receipt against a Purchase Order for the given row quantities.

	`items` is a list of {"purchase_order_item": <PO row name>, "qty": <received qty>}.
	"""
	frappe.has_permission("Purchase Receipt", "create", throw=True)

	qty_by_row = {}
	for row in frappe.parse_json(items) or []:
		qty = flt(row.get("qty"))
		if qty < 0:
			frappe.throw(_("Received quantity cannot be negative."))
		if qty:
			qty_by_row[row.get("purchase_order_item")] = qty

	if not qty_by_row:
		frappe.throw(_("Enter a received quantity for at least one item."))

	if frappe.db.get_value("Purchase Order", purchase_order, "status") not in RECEIVABLE_PO_STATUSES:
		frappe.throw(_("Purchase Order {0} has no items left to receive.").format(purchase_order))

	doc = make_purchase_receipt(purchase_order)
	doc.items = [row for row in doc.items if row.purchase_order_item in qty_by_row]
	if len(doc.items) != len(qty_by_row):
		frappe.throw(_("Some items do not belong to Purchase Order {0} or are already fully received.").format(purchase_order))

	if warehouse:
		doc.set_warehouse = warehouse

	for idx, row in enumerate(doc.items, start=1):
		row.idx = idx
		row.qty = qty_by_row[row.purchase_order_item]
		row.received_qty = row.qty
		row.rejected_qty = 0
		if warehouse:
			row.warehouse = warehouse

	if posting_date:
		doc.posting_date = posting_date
		doc.set_posting_time = 1
	if supplier_delivery_note:
		doc.supplier_delivery_note = supplier_delivery_note

	doc.insert()
	return doc.name
