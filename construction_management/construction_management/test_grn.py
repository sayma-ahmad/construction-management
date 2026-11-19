# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days, flt, nowdate

from construction_management.grn import get_grns, get_purchase_order_items, make_grn


class TestGRN(FrappeTestCase):
	"""Tests for the GRN module: Purchase Receipts created against Purchase Orders."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		if not cls.company:
			raise unittest.SkipTest("Run the ERPNext setup wizard to create a Company first.")
		if not frappe.get_meta("Purchase Receipt Item").has_field("cm_ordered_qty"):
			raise unittest.SkipTest("Run bench migrate so the GRN custom fields exist.")

		cls.warehouse = cls.create_warehouse()
		cls.supplier = cls.create_supplier()

	def setUp(self):
		frappe.set_user("Administrator")
		self.item = self.create_item()

	def tearDown(self):
		frappe.set_user("Administrator")

	@classmethod
	def create_warehouse(cls):
		parent = frappe.db.get_value("Warehouse", {"company": cls.company, "is_group": 1}, "name")
		return (
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": f"GRN Test Store {frappe.generate_hash(length=5)}",
					"company": cls.company,
					"parent_warehouse": parent,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	@classmethod
	def create_supplier(cls):
		return (
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": f"GRN Test Supplier {frappe.generate_hash(length=5)}",
					"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
					"cm_specialization": "Cement & Concrete",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def create_item(self):
		return (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": f"CM-GRN-{frappe.generate_hash(length=6)}",
					"item_name": "GRN Test Cement",
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
					"cm_material_type": "Civil",
					"stock_uom": "Nos",
					"is_stock_item": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def create_purchase_order(self, qty=10, submit=True):
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": self.supplier,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"set_warehouse": self.warehouse,
				"items": [
					{
						"item_code": self.item,
						"qty": qty,
						"rate": 100,
						"warehouse": self.warehouse,
						"schedule_date": add_days(nowdate(), 7),
					}
				],
			}
		).insert(ignore_permissions=True)
		if submit:
			po.submit()
		return po

	def stock_qty(self):
		return flt(frappe.db.get_value("Bin", {"item_code": self.item, "warehouse": self.warehouse}, "actual_qty"))

	def receive(self, po, qty):
		row = po.items[0].name
		return make_grn(po.name, [{"purchase_order_item": row, "qty": qty}], warehouse=self.warehouse)

	def test_partial_and_full_receipt_update_stock_and_purchase_order(self):
		po = self.create_purchase_order(qty=10)
		po_items = get_purchase_order_items(po.name)["items"]
		self.assertEqual(po_items[0]["ordered_qty"], 10)
		self.assertEqual(po_items[0]["pending_qty"], 10)

		grn = frappe.get_doc("Purchase Receipt", self.receive(po, 4))
		self.assertEqual(grn.docstatus, 0)
		self.assertEqual(grn.supplier, self.supplier)
		self.assertEqual(grn.set_warehouse, self.warehouse)
		row = grn.items[0]
		self.assertEqual(row.purchase_order, po.name)
		self.assertEqual(row.purchase_order_item, po.items[0].name)
		self.assertEqual(row.warehouse, self.warehouse)
		self.assertEqual(flt(row.cm_ordered_qty), 10)
		self.assertEqual(flt(row.received_qty), 4)
		self.assertEqual(flt(row.qty), 4)
		self.assertEqual(self.stock_qty(), 0, "A draft GRN must not change stock")

		grn.submit()
		self.assertEqual(self.stock_qty(), 4)
		self.assertTrue(
			frappe.db.exists(
				"Stock Ledger Entry",
				{"voucher_no": grn.name, "item_code": self.item, "warehouse": self.warehouse, "actual_qty": 4},
			)
		)
		po.reload()
		self.assertEqual(flt(po.items[0].received_qty), 4)
		self.assertEqual(flt(po.per_received), 40)
		self.assertEqual(po.status, "To Receive and Bill")
		self.assertEqual(get_purchase_order_items(po.name)["items"][0]["pending_qty"], 6)

		second = frappe.get_doc("Purchase Receipt", self.receive(po, 6))
		second.submit()
		self.assertEqual(self.stock_qty(), 10)
		po.reload()
		self.assertEqual(flt(po.per_received), 100)
		self.assertEqual(po.status, "To Bill")

		listed = {row["name"]: row for row in get_grns()}
		self.assertIn(grn.name, listed)
		self.assertEqual(listed[grn.name]["purchase_orders"], [po.name])
		self.assertEqual(listed[grn.name]["warehouses"], [self.warehouse])
		self.assertEqual(listed[grn.name]["accepted_qty"], 4)
		self.assertEqual(listed[second.name]["status"], "To Bill")

		with self.assertRaises(frappe.ValidationError):
			self.receive(po, 1)

	def test_cancel_reverses_stock_and_received_qty(self):
		po = self.create_purchase_order(qty=5)
		grn = frappe.get_doc("Purchase Receipt", self.receive(po, 5))
		grn.submit()
		self.assertEqual(self.stock_qty(), 5)

		grn.cancel()
		self.assertEqual(self.stock_qty(), 0)
		po.reload()
		self.assertEqual(flt(po.items[0].received_qty), 0)
		self.assertEqual(po.status, "To Receive and Bill")
		grn.reload()
		self.assertEqual(grn.docstatus, 2)
		self.assertEqual(grn.status, "Cancelled")

	def test_received_quantity_validations(self):
		po = self.create_purchase_order(qty=5)

		for qty in (0, -1):
			with self.assertRaises(frappe.ValidationError):
				self.receive(po, qty)

		with self.assertRaises(frappe.ValidationError):
			make_grn(po.name, [{"purchase_order_item": "not-a-po-row", "qty": 1}])

		draft_po = self.create_purchase_order(qty=5, submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_grn(draft_po.name, [{"purchase_order_item": draft_po.items[0].name, "qty": 1}])
		with self.assertRaises(frappe.ValidationError):
			get_purchase_order_items(draft_po.name)

		with change_settings("Stock Settings", {"over_delivery_receipt_allowance": 0}):
			over_receipt = frappe.get_doc("Purchase Receipt", self.receive(po, 6))
			with self.assertRaises(frappe.ValidationError):
				over_receipt.submit()
		self.assertEqual(self.stock_qty(), 0)

	def test_permissions(self):
		po = self.create_purchase_order(qty=5)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"grn-viewer-{frappe.generate_hash(length=5)}@example.com",
				"first_name": "GRN Viewer",
				"send_welcome_email": 0,
				"roles": [{"role": "Accounts User"}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(user.name)
		self.assertFalse(frappe.has_permission("Purchase Receipt", "create"))
		with self.assertRaises(frappe.PermissionError):
			self.receive(po, 1)
		self.assertIsInstance(get_grns(), list)
