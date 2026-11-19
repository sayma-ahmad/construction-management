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
		# Ensure required test UOM dependencies exist on clean or fresh databases
		for uom in ["Bag", "Kg", "Nos", "Meter", "Cubic Meter", "Unit"]:
			if not frappe.db.exists("UOM", uom):
				frappe.get_doc(
					{
						"doctype": "UOM",
						"uom_name": uom,
						"name": uom,
					}
				).insert(ignore_permissions=True)
		# Ensure materials, vendors, and PO custom fields are configured
		materials.setup()
		vendors.setup()
		purchase_orders.setup()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _ensure_uom(self, uom_name="Bag"):
		if not frappe.db.exists("UOM", uom_name):
			frappe.get_doc(
				{
					"doctype": "UOM",
					"uom_name": uom_name,
					"name": uom_name,
				}
			).insert(ignore_permissions=True)

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

	def _get_or_create_warehouse(self, company):
		warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
		if warehouse:
			return warehouse
		abbr = frappe.db.get_value("Company", company, "abbr") or "TC"
		doc = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"Stores {frappe.generate_hash(length=4)}",
				"company": company,
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
		self._ensure_uom("Bag")
		company = self._get_or_create_company()
		warehouse = self._get_or_create_warehouse(company)
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
				"item_defaults": [
					{
						"company": company,
						"default_warehouse": warehouse,
					}
				],
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
		warehouse = self._get_or_create_warehouse(company)
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
						"warehouse": warehouse,
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

		res = purchase_orders.get_purchase_orders(project=project_name)
		orders = res["orders"] if isinstance(res, dict) else res
		self.assertTrue(len(orders) >= 1)
		found = [o for o in orders if o["name"] == po["name"]]
		self.assertEqual(len(found), 1)
		self.assertEqual(found[0]["project"], project_name)
		self.assertEqual(found[0]["supplier"], supplier_name)
		self.assertEqual(found[0]["item_count"], 1)
		if isinstance(res, dict):
			self.assertTrue(res["total"] >= 1)

	def test_05_get_material_requests_api(self):
		"""Verify get_material_requests_for_project returns open purchase requisitions."""
		company = self._get_or_create_company()
		project_name = self._create_project("MR-API-Proj")
		item_code = self._get_or_create_item()

		warehouse = self._get_or_create_warehouse(company)
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
						"warehouse": warehouse,
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
		warehouse = self._get_or_create_warehouse(company)
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
						"warehouse": warehouse,
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
		res = purchase_orders.get_purchase_orders(page_length=50)
		orders = res["orders"] if isinstance(res, dict) else res
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

	def test_10_quantity_validation(self):
		"""Verify that zero, negative, or empty item quantities fail validation."""
		project_name = self._create_project("Qty-Val-Proj")
		supplier_name = self._get_or_create_supplier()
		item_code = self._get_or_create_item()

		# 1. Zero quantity should raise ValidationError
		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project_name,
				supplier=supplier_name,
				required_date=add_days(nowdate(), 7),
				items=[{"item_code": item_code, "qty": 0, "rate": 100}],
			)

		# 2. Negative quantity should raise ValidationError
		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project_name,
				supplier=supplier_name,
				required_date=add_days(nowdate(), 7),
				items=[{"item_code": item_code, "qty": -5, "rate": 100}],
			)

		# 3. Empty item list should raise ValidationError
		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project_name,
				supplier=supplier_name,
				required_date=add_days(nowdate(), 7),
				items=[],
			)

		# 4. Quantity exceeding remaining requested quantity on linked MR raises ValidationError
		company = self._get_or_create_company()
		warehouse = self._get_or_create_warehouse(company)
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
						"qty": 50,
						"schedule_date": add_days(nowdate(), 10),
						"project": project_name,
						"warehouse": warehouse,
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)
		mr.submit()

		# Attempting to order 60 when only 50 was requested must raise ValidationError
		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project_name,
				supplier=supplier_name,
				required_date=add_days(nowdate(), 7),
				material_request=mr.name,
				items=[
					{
						"item_code": item_code,
						"qty": 60,
						"rate": 100,
						"material_request": mr.name,
						"material_request_item": mr.items[0].name,
					}
				],
			)

	def test_11_material_request_query_filtering(self):
		"""Verify material_request_query returns only open MRs for the requested project."""
		company = self._get_or_create_company()
		project_a = self._create_project("Query-A")
		project_b = self._create_project("Query-B")
		item_code = self._get_or_create_item()
		warehouse = self._get_or_create_warehouse(company)

		mr_a = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project_a,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 10),
				"items": [
					{
						"item_code": item_code,
						"qty": 20,
						"schedule_date": add_days(nowdate(), 10),
						"project": project_a,
						"warehouse": warehouse,
					}
				],
			}
		)
		mr_a.insert(ignore_permissions=True)
		mr_a.submit()

		results_a = purchase_orders.material_request_query(
			"Material Request", "", "name", 0, 20, {"project": project_a}
		)
		names_a = [r[0] for r in results_a]
		self.assertIn(mr_a.name, names_a)

		results_b = purchase_orders.material_request_query(
			"Material Request", "", "name", 0, 20, {"project": project_b}
		)
		names_b = [r[0] for r in results_b]
		self.assertNotIn(mr_a.name, names_b)

	def test_12_user_permission_project_isolation(self):
		"""Verify that User Permissions isolate Purchase Orders and Material Requests across projects."""
		project_a = self._create_project("UserPerm-A")
		project_b = self._create_project("UserPerm-B")
		supplier_name = self._get_or_create_supplier()
		item_code = self._get_or_create_item()

		po_a = purchase_orders.create_construction_purchase_order(
			project=project_a,
			supplier=supplier_name,
			required_date=add_days(nowdate(), 7),
			items=[{"item_code": item_code, "qty": 10, "rate": 200}],
		)
		po_b = purchase_orders.create_construction_purchase_order(
			project=project_b,
			supplier=supplier_name,
			required_date=add_days(nowdate(), 7),
			items=[{"item_code": item_code, "qty": 15, "rate": 250}],
		)

		user_email = f"restricted_buyer_{frappe.generate_hash(length=6)}@example.com"
		if not frappe.db.exists("User", user_email):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": user_email,
					"first_name": "Restricted",
					"last_name": "Buyer",
					"roles": [{"role": "Stock User"}, {"role": "Projects User"}],
				}
			)
			user.insert(ignore_permissions=True)

		user_perm = frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user_email,
				"allow": "Project",
				"for_value": project_a,
			}
		)
		user_perm.insert(ignore_permissions=True)

		try:
			frappe.set_user(user_email)

			# Listing all POs should return PO for project_a and omit project_b
			res = purchase_orders.get_purchase_orders()
			orders = res["orders"] if isinstance(res, dict) else res
			returned_names = [o["name"] for o in orders]
			self.assertIn(po_a["name"], returned_names)
			self.assertNotIn(po_b["name"], returned_names)

			# Explicitly requesting project_b must raise PermissionError
			with self.assertRaises(frappe.PermissionError):
				purchase_orders.get_purchase_orders(project=project_b)

			# Requesting Material Requests for project_b must raise PermissionError
			with self.assertRaises(frappe.PermissionError):
				purchase_orders.get_material_requests_for_project(project=project_b)

		finally:
			frappe.set_user("Administrator")
			user_perm.delete(ignore_permissions=True)

	def test_13_material_request_type_and_status_validation(self):
		"""Verify rejection of unsubmitted, non-Purchase, or stopped Material Requests."""
		company = self._get_or_create_company()
		project = self._create_project("MR-Type-Status")
		supplier = self._get_or_create_supplier()
		item_code = self._get_or_create_item()
		warehouse = self._get_or_create_warehouse(company)

		# 1. Draft Material Request (docstatus = 0)
		draft_mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"items": [
					{
						"item_code": item_code,
						"qty": 20,
						"schedule_date": add_days(nowdate(), 7),
						"project": project,
						"warehouse": warehouse,
					}
				],
			}
		)
		draft_mr.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project,
				supplier=supplier,
				required_date=add_days(nowdate(), 7),
				material_request=draft_mr.name,
				items=[{"item_code": item_code, "qty": 10, "material_request": draft_mr.name, "material_request_item": draft_mr.items[0].name}],
			)

		# 2. Material Request of type "Material Transfer"
		transfer_mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Material Transfer",
				"company": company,
				"cm_project": project,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"items": [
					{
						"item_code": item_code,
						"qty": 20,
						"schedule_date": add_days(nowdate(), 7),
						"project": project,
						"warehouse": warehouse,
					}
				],
			}
		)
		transfer_mr.insert(ignore_permissions=True)
		transfer_mr.submit()

		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project,
				supplier=supplier,
				required_date=add_days(nowdate(), 7),
				material_request=transfer_mr.name,
				items=[{"item_code": item_code, "qty": 10, "material_request": transfer_mr.name, "material_request_item": transfer_mr.items[0].name}],
			)

		# 3. Stopped Material Request
		valid_mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"items": [
					{
						"item_code": item_code,
						"qty": 20,
						"schedule_date": add_days(nowdate(), 7),
						"project": project,
						"warehouse": warehouse,
					}
				],
			}
		)
		valid_mr.insert(ignore_permissions=True)
		valid_mr.submit()
		valid_mr.db_set("status", "Stopped")

		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project,
				supplier=supplier,
				required_date=add_days(nowdate(), 7),
				material_request=valid_mr.name,
				items=[{"item_code": item_code, "qty": 10, "material_request": valid_mr.name, "material_request_item": valid_mr.items[0].name}],
			)

	def test_14_project_mismatch_validation(self):
		"""Verify that linking MR or item with mismatched project raises ValidationError."""
		company = self._get_or_create_company()
		project_a = self._create_project("Mismatch-A")
		project_b = self._create_project("Mismatch-B")
		supplier = self._get_or_create_supplier()
		item_code = self._get_or_create_item()
		warehouse = self._get_or_create_warehouse(company)

		mr_a = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project_a,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"items": [
					{
						"item_code": item_code,
						"qty": 50,
						"schedule_date": add_days(nowdate(), 7),
						"project": project_a,
						"warehouse": warehouse,
					}
				],
			}
		)
		mr_a.insert(ignore_permissions=True)
		mr_a.submit()

		# Case 1: PO header project is B, but linked MR is for Project A
		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project_b,
				supplier=supplier,
				required_date=add_days(nowdate(), 7),
				material_request=mr_a.name,
				items=[{"item_code": item_code, "qty": 10, "material_request": mr_a.name, "material_request_item": mr_a.items[0].name}],
			)

		# Case 2: PO header is Project A, but item row has project=Project B
		with self.assertRaises(frappe.ValidationError):
			po = frappe.get_doc(
				{
					"doctype": "Purchase Order",
					"company": company,
					"supplier": supplier,
					"project": project_a,
					"transaction_date": nowdate(),
					"schedule_date": add_days(nowdate(), 7),
					"items": [
						{
							"item_code": item_code,
							"qty": 10,
							"rate": 100,
							"project": project_b,
							"schedule_date": add_days(nowdate(), 7),
						}
					],
				}
			)
			po.insert()

	def test_15_over_ordering_across_draft_and_submitted_pos(self):
		"""Verify that draft POs consume remaining quantity and prevent excess ordering across multiple POs."""
		company = self._get_or_create_company()
		project = self._create_project("Draft-Sub-Qty")
		supplier = self._get_or_create_supplier()
		item_code = self._get_or_create_item()
		warehouse = self._get_or_create_warehouse(company)

		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 10),
				"items": [
					{
						"item_code": item_code,
						"qty": 100,
						"schedule_date": add_days(nowdate(), 10),
						"project": project,
						"warehouse": warehouse,
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)
		mr.submit()
		mr_item_name = mr.items[0].name

		# Draft PO 1: 50 units
		po1 = purchase_orders.create_construction_purchase_order(
			project=project,
			supplier=supplier,
			required_date=add_days(nowdate(), 7),
			material_request=mr.name,
			items=[{"item_code": item_code, "qty": 50, "rate": 200, "material_request": mr.name, "material_request_item": mr_item_name}],
			submit=0,
		)
		self.assertEqual(po1.get("docstatus"), 0)

		# Remaining quantity should now be 50 (even though PO 1 is only Draft!)
		rem_qty = purchase_orders.get_remaining_qty_for_mr_item(mr_item_name)
		self.assertEqual(rem_qty, 50.0)

		# Attempting to order 60 more should fail because 50 + 60 = 110 > 100
		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project,
				supplier=supplier,
				required_date=add_days(nowdate(), 7),
				material_request=mr.name,
				items=[{"item_code": item_code, "qty": 60, "rate": 200, "material_request": mr.name, "material_request_item": mr_item_name}],
				submit=0,
			)

		# Submitted PO 2: 30 units
		po2 = purchase_orders.create_construction_purchase_order(
			project=project,
			supplier=supplier,
			required_date=add_days(nowdate(), 7),
			material_request=mr.name,
			items=[{"item_code": item_code, "qty": 30, "rate": 200, "material_request": mr.name, "material_request_item": mr_item_name}],
			submit=1,
		)
		self.assertEqual(po2.get("docstatus"), 1)

		# Remaining quantity is now 20
		rem_qty = purchase_orders.get_remaining_qty_for_mr_item(mr_item_name)
		self.assertEqual(rem_qty, 20.0)

		# Order the remaining 20 units
		po3 = purchase_orders.create_construction_purchase_order(
			project=project,
			supplier=supplier,
			required_date=add_days(nowdate(), 7),
			material_request=mr.name,
			items=[{"item_code": item_code, "qty": 20, "rate": 200, "material_request": mr.name, "material_request_item": mr_item_name}],
			submit=0,
		)
		self.assertEqual(purchase_orders.get_remaining_qty_for_mr_item(mr_item_name), 0.0)

	def test_16_duplicate_item_rows_over_ordering(self):
		"""Verify that duplicate/split item rows cannot bypass quantity validation and over-ordering is prevented."""
		company = self._get_or_create_company()
		project = self._create_project("Split-Row-Qty")
		supplier = self._get_or_create_supplier()
		item_code_1 = self._get_or_create_item()
		item_code_2 = self._get_or_create_item(name="Test TMT Steel 12mm")
		warehouse = self._get_or_create_warehouse(company)

		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 10),
				"items": [
					{
						"item_code": item_code_1,
						"qty": 50,
						"schedule_date": add_days(nowdate(), 10),
						"project": project,
						"warehouse": warehouse,
					},
					{
						"item_code": item_code_2,
						"qty": 40,
						"schedule_date": add_days(nowdate(), 10),
						"project": project,
						"warehouse": warehouse,
					},
				],
			}
		)
		mr.insert(ignore_permissions=True)
		mr.submit()
		mr_item_1 = mr.items[0].name
		mr_item_2 = mr.items[1].name

		# 1. Attempting to bypass limit by splitting same MR item across duplicate rows (30 + 30 = 60 > 50) fails validation
		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project,
				supplier=supplier,
				required_date=add_days(nowdate(), 7),
				material_request=mr.name,
				items=[
					{"item_code": item_code_1, "qty": 30, "rate": 200, "material_request": mr.name, "material_request_item": mr_item_1},
					{"item_code": item_code_1, "qty": 30, "rate": 200, "material_request": mr.name, "material_request_item": mr_item_1},
				],
			)

		# 2. Over-ordering on any MR item row raises ValidationError
		with self.assertRaises(frappe.ValidationError):
			purchase_orders.create_construction_purchase_order(
				project=project,
				supplier=supplier,
				required_date=add_days(nowdate(), 7),
				material_request=mr.name,
				items=[
					{"item_code": item_code_1, "qty": 20, "rate": 200, "material_request": mr.name, "material_request_item": mr_item_1},
					{"item_code": item_code_2, "qty": 45, "rate": 300, "material_request": mr.name, "material_request_item": mr_item_2},
				],
			)

		# 3. Valid multi-row PO within limits succeeds
		po = purchase_orders.create_construction_purchase_order(
			project=project,
			supplier=supplier,
			required_date=add_days(nowdate(), 7),
			material_request=mr.name,
			items=[
				{"item_code": item_code_1, "qty": 20, "rate": 200, "material_request": mr.name, "material_request_item": mr_item_1},
				{"item_code": item_code_2, "qty": 35, "rate": 300, "material_request": mr.name, "material_request_item": mr_item_2},
			],
		)
		self.assertTrue(bool(po.get("name")))

	def test_17_standard_form_save_and_update_revalidation(self):
		"""Verify that standard ERPNext form creation and updates trigger quantity validations without self-blocking."""
		company = self._get_or_create_company()
		project = self._create_project("Std-Form-Hook")
		supplier = self._get_or_create_supplier()
		item_code = self._get_or_create_item()
		warehouse = self._get_or_create_warehouse(company)

		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 10),
				"items": [
					{
						"item_code": item_code,
						"qty": 60,
						"schedule_date": add_days(nowdate(), 10),
						"project": project,
						"warehouse": warehouse,
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)
		mr.submit()
		mr_item_name = mr.items[0].name

		# 1. Standard form insert: excess quantity (70 > 60) fails
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"company": company,
				"supplier": supplier,
				"project": project,
				"cm_material_request": mr.name,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"items": [
					{
						"item_code": item_code,
						"qty": 70,
						"rate": 300,
						"project": project,
						"schedule_date": add_days(nowdate(), 7),
						"material_request": mr.name,
						"material_request_item": mr_item_name,
					}
				],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			po.insert()

		# 2. Standard form insert: valid quantity (40 <= 60) succeeds
		po.items[0].qty = 40
		po.insert()
		self.assertTrue(bool(po.name))

		# 3. Update existing PO: update to 50 (still <= 60 requested) succeeds without counting old 40 against itself
		po.reload()
		po.items[0].qty = 50
		po.save()
		self.assertEqual(po.items[0].qty, 50)

		# 4. Update existing PO: update to 75 (> 60 requested) fails on save
		po.items[0].qty = 75
		with self.assertRaises(frappe.ValidationError):
			po.save()

