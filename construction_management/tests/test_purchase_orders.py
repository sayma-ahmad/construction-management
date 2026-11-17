# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from construction_management import materials, purchase_orders, vendors


class TestPurchaseOrders(FrappeTestCase):
	"""Tests for Construction Management Purchase Order features (US-13)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Ensure materials, vendors, and PO custom fields are configured
		materials.setup()
		vendors.setup()
		purchase_orders.setup()

	def _get_or_create_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if company:
			return company
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Test Construction Co {frappe.generate_hash(length=4)}",
				"abbr": f"TC{frappe.generate_hash(length=3).upper()}",
				"default_currency": "INR",
				"country": "India",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _get_or_create_supplier(self):
		supplier = frappe.db.get_value("Supplier", {}, "name")
		if supplier:
			return supplier
		doc = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"Test Construction Supplier {frappe.generate_hash(length=4)}",
				"supplier_group": "Material Supplier",
				"supplier_type": "Company",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _get_or_create_item(self):
		item = frappe.db.get_value("Item", {"is_stock_item": 1}, "name")
		if item:
			return item
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"TEST-MAT-{frappe.generate_hash(length=4)}",
				"item_name": "Test Cement 53 Grade",
				"item_group": "Cement & Concrete",
				"stock_uom": "Bag",
				"is_stock_item": 1,
				"cm_material_type": "Civil",
				"cm_material_grade": "OPC 53",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _create_project(self, suffix):
		company = self._get_or_create_company()
		doc = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Test Construction Project {suffix}",
				"company": company,
				"status": "Open",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_01_custom_fields_exist(self):
		"""Verify that construction custom fields exist on Purchase Order, Purchase Order Item, and Material Request."""
		po_meta = frappe.get_meta("Purchase Order")
		self.assertTrue(po_meta.has_field("cm_project"))
		self.assertTrue(po_meta.has_field("cm_material_request"))
		self.assertTrue(po_meta.has_field("cm_delivery_site"))
		self.assertTrue(po_meta.has_field("cm_delivery_contact"))

		item_meta = frappe.get_meta("Purchase Order Item")
		self.assertTrue(item_meta.has_field("cm_material_type"))
		self.assertTrue(item_meta.has_field("cm_material_grade"))

		mr_meta = frappe.get_meta("Material Request")
		self.assertTrue(mr_meta.has_field("cm_project"))

	def test_02_create_purchase_order_with_project(self):
		"""Verify that creating a PO sets project on header and item lines."""
		project_name = self._create_project("PO-Proj")
		supplier_name = self._get_or_create_supplier()
		item_code = self._get_or_create_item()

		po = purchase_orders.create_construction_purchase_order(
			project=project_name,
			supplier=supplier_name,
			required_date=add_days(nowdate(), 7),
			delivery_site="Site North Block",
			delivery_contact="Test Supervisor",
			items=[{"item_code": item_code, "qty": 50, "rate": 350}],
			submit=0,
		)

		self.assertEqual(po.get("project"), project_name)
		self.assertEqual(po.get("cm_project"), project_name)
		self.assertEqual(po.get("cm_delivery_site"), "Site North Block")
		self.assertEqual(po.get("cm_delivery_contact"), "Test Supervisor")

		# Verify item line inherited project
		po_doc = frappe.get_doc("Purchase Order", po["name"])
		self.assertEqual(len(po_doc.items), 1)
		self.assertEqual(po_doc.items[0].project, project_name)
		self.assertEqual(po_doc.items[0].qty, 50)
		self.assertEqual(po_doc.items[0].rate, 350)

	def test_03_link_purchase_order_with_material_request(self):
		"""Verify that a PO can be linked to a Material Request with item-level traceability."""
		company = self._get_or_create_company()
		project_name = self._create_project("MR-Link-Proj")
		supplier_name = self._get_or_create_supplier()
		item_code = self._get_or_create_item()

		# 1. Create a Material Request
		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project_name,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 10),
				"items": [
					{
						"item_code": item_code,
						"qty": 100,
						"schedule_date": add_days(nowdate(), 10),
						"project": project_name,
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)
		mr.submit()

		# 2. Get Material Request details via API
		mr_details = purchase_orders.get_material_request_details(mr.name)
		self.assertEqual(mr_details["name"], mr.name)
		self.assertEqual(mr_details["project"], project_name)
		self.assertEqual(len(mr_details["items"]), 1)
		self.assertEqual(mr_details["items"][0]["item_code"], item_code)

		# 3. Create PO linked to Material Request
		po = purchase_orders.create_construction_purchase_order(
			project=project_name,
			supplier=supplier_name,
			required_date=add_days(nowdate(), 7),
			material_request=mr.name,
			items=[
				{
					"item_code": item_code,
					"qty": 75,
					"rate": 360,
					"material_request": mr.name,
					"material_request_item": mr.items[0].name,
				}
			],
			submit=0,
		)

		self.assertEqual(po.get("cm_material_request"), mr.name)
		po_doc = frappe.get_doc("Purchase Order", po["name"])
		self.assertEqual(po_doc.items[0].material_request, mr.name)
		self.assertEqual(po_doc.items[0].material_request_item, mr.items[0].name)

	def test_04_get_purchase_orders_api(self):
		"""Verify get_purchase_orders endpoint with filtering by project."""
		project_name = self._create_project("API-Proj")
		supplier_name = self._get_or_create_supplier()
		item_code = self._get_or_create_item()

		po = purchase_orders.create_construction_purchase_order(
			project=project_name,
			supplier=supplier_name,
			required_date=add_days(nowdate(), 5),
			items=[{"item_code": item_code, "qty": 20, "rate": 400}],
		)

		orders = purchase_orders.get_purchase_orders(project=project_name)
		self.assertTrue(len(orders) >= 1)
		found = [o for o in orders if o["name"] == po["name"]]
		self.assertEqual(len(found), 1)
		self.assertEqual(found[0]["project"], project_name)
		self.assertEqual(found[0]["supplier"], supplier_name)
		self.assertEqual(found[0]["item_count"], 1)

	def test_05_get_material_requests_api(self):
		"""Verify get_material_requests_for_project returns open purchase requisitions."""
		company = self._get_or_create_company()
		project_name = self._create_project("MR-API-Proj")
		item_code = self._get_or_create_item()

		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project_name,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 10),
				"items": [
					{
						"item_code": item_code,
						"qty": 30,
						"schedule_date": add_days(nowdate(), 10),
						"project": project_name,
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)
		mr.submit()

		mrs = purchase_orders.get_material_requests_for_project(project=project_name)
		self.assertTrue(len(mrs) >= 1)
		found = [m for m in mrs if m["name"] == mr.name]
		self.assertEqual(len(found), 1)
		self.assertEqual(found[0]["project"], project_name)
