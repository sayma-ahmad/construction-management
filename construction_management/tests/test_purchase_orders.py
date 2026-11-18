# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

from construction_management import materials, purchase_orders, vendors


class TestPurchaseOrders(FrappeTestCase):
	"""Comprehensive tests for Construction Management Purchase Order features (US-13)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Ensure materials, vendors, and PO custom fields are configured
		materials.setup()
		vendors.setup()
		purchase_orders.setup()

	def tearDown(self):
		frappe.set_user("Administrator")

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

	def _get_or_create_item(self, code=None, name="Test Cement 53 Grade"):
		item_code = code or f"TEST-MAT-{frappe.generate_hash(length=4)}"
		if frappe.db.exists("Item", item_code):
			return item_code
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": name,
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
				"project_name": f"Test Construction Project {suffix} {frappe.generate_hash(length=4)}",
				"company": company,
				"status": "Open",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_01_custom_fields_exist(self):
		"""Verify that construction custom fields exist on Purchase Order, Item, and Material Request."""
		po_meta = frappe.get_meta("Purchase Order")
		self.assertTrue(po_meta.has_field("project"), "Standard project field must exist on Purchase Order")
		self.assertTrue(po_meta.has_field("cm_material_request"), "cm_material_request field must exist")
		self.assertTrue(po_meta.has_field("cm_delivery_site"), "cm_delivery_site field must exist")
		self.assertTrue(po_meta.has_field("cm_delivery_contact"), "cm_delivery_contact field must exist")

		item_meta = frappe.get_meta("Purchase Order Item")
		self.assertTrue(item_meta.has_field("cm_material_type"), "cm_material_type field must exist")
		self.assertTrue(item_meta.has_field("cm_material_grade"), "cm_material_grade field must exist")

		mr_meta = frappe.get_meta("Material Request")
		self.assertTrue(mr_meta.has_field("cm_project"), "cm_project field must exist on Material Request")

	def test_02_create_purchase_order_with_project(self):
		"""Verify that creating a PO sets project on header and propagates down to item lines."""
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
		self.assertEqual(po.get("cm_delivery_site"), "Site North Block")
		self.assertEqual(po.get("cm_delivery_contact"), "Test Supervisor")

		# Verify item line inherited project
		po_doc = frappe.get_doc("Purchase Order", po["name"])
		self.assertEqual(len(po_doc.items), 1)
		self.assertEqual(po_doc.items[0].project, project_name)
		self.assertEqual(po_doc.items[0].qty, 50)
		self.assertEqual(po_doc.items[0].rate, 350)

	def test_03_link_purchase_order_with_material_request(self):
		"""Verify that a PO links to a Material Request with item-level traceability."""
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
		self.assertEqual(mr_details["items"][0]["remaining_qty"], 100)

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

	def test_06_permission_checks(self):
		"""Verify that unpermitted users (Guest) are blocked by API permission checks."""
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				purchase_orders.get_purchase_orders()

			with self.assertRaises(frappe.PermissionError):
				purchase_orders.get_material_requests_for_project("NonExistent")

			with self.assertRaises(frappe.PermissionError):
				purchase_orders.get_material_request_details("NonExistent")

			with self.assertRaises(frappe.PermissionError):
				purchase_orders.create_construction_purchase_order(
					project="Proj",
					supplier="Supp",
					required_date=nowdate(),
					items=[{"item_code": "CM-CEM-001", "qty": 1}],
				)
		finally:
			frappe.set_user("Administrator")

	def test_07_purchase_order_submission(self):
		"""Verify Purchase Order creation with submit=1 sets docstatus=1."""
		project_name = self._create_project("Submit-Proj")
		supplier_name = self._get_or_create_supplier()
		item_code = self._get_or_create_item()

		po = purchase_orders.create_construction_purchase_order(
			project=project_name,
			supplier=supplier_name,
			required_date=add_days(nowdate(), 7),
			items=[{"item_code": item_code, "qty": 15, "rate": 500}],
			submit=1,
		)

		self.assertEqual(po.get("docstatus"), 1)
		db_status = frappe.db.get_value("Purchase Order", po["name"], "docstatus")
		self.assertEqual(db_status, 1)

	def test_08_remaining_quantity_calculations(self):
		"""Verify accurate calculation of remaining quantities and exclusion of fully ordered MRs."""
		company = self._get_or_create_company()
		project_name = self._create_project("Qty-Calc-Proj")
		supplier_name = self._get_or_create_supplier()
		item_code = self._get_or_create_item()

		# Create MR for 100 units
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

		# Initially, remaining qty should be 100
		details_1 = purchase_orders.get_material_request_details(mr.name)
		self.assertEqual(len(details_1["items"]), 1)
		self.assertEqual(details_1["items"][0]["remaining_qty"], 100)

		# Create and submit a partial PO for 40 units
		purchase_orders.create_construction_purchase_order(
			project=project_name,
			supplier=supplier_name,
			required_date=add_days(nowdate(), 5),
			material_request=mr.name,
			items=[
				{
					"item_code": item_code,
					"qty": 40,
					"rate": 300,
					"material_request": mr.name,
					"material_request_item": mr.items[0].name,
				}
			],
			submit=1,
		)

		# Remaining quantity should now be 60
		details_2 = purchase_orders.get_material_request_details(mr.name)
		self.assertEqual(len(details_2["items"]), 1)
		self.assertEqual(details_2["items"][0]["remaining_qty"], 60)
		self.assertEqual(details_2["items"][0]["ordered_qty"], 40)

		# Order the remaining 60 units and submit
		purchase_orders.create_construction_purchase_order(
			project=project_name,
			supplier=supplier_name,
			required_date=add_days(nowdate(), 5),
			material_request=mr.name,
			items=[
				{
					"item_code": item_code,
					"qty": 60,
					"rate": 300,
					"material_request": mr.name,
					"material_request_item": mr.items[0].name,
				}
			],
			submit=1,
		)

		# The MR is now fully ordered, so it should be excluded from open MRs
		open_mrs = purchase_orders.get_material_requests_for_project(project=project_name)
		matching = [m for m in open_mrs if m["name"] == mr.name]
		self.assertEqual(len(matching), 0, "Fully ordered Material Request must be excluded from open requisitions")

	def test_09_sample_purchase_orders_integrity(self):
		"""Verify that sample POs are correctly linked to Material Requests with item traceability."""
		purchase_orders.create_sample_purchase_orders()

		# Query sample POs
		orders = purchase_orders.get_purchase_orders()
		self.assertTrue(len(orders) >= 4)

		# Check PO linked to Riverside Apartments
		riverside_pos = [o for o in orders if o["project_name"] == "Riverside Apartments" and o["material_request"]]
		self.assertTrue(len(riverside_pos) >= 1)

		for po in riverside_pos:
			po_doc = frappe.get_doc("Purchase Order", po["name"])
			# Every item linked to an MR must have material_request_item populated
			for it in po_doc.items:
				if it.material_request:
					self.assertTrue(bool(it.material_request_item), f"Item {it.item_code} in PO {po['name']} missing material_request_item")
					mr_item_exists = frappe.db.exists("Material Request Item", it.material_request_item)
					self.assertTrue(bool(mr_item_exists), f"Referenced MR Item {it.material_request_item} does not exist")
