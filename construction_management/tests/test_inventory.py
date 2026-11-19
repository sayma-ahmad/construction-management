# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import json
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from construction_management import inventory, materials


class TestInventory(FrappeTestCase):
	"""Comprehensive unit tests for Construction Inventory Module (US-15)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		materials.setup()
		materials.create_sample_materials()

	def setUp(self):
		self.company = self._get_or_create_company()
		inventory.setup(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _get_or_create_company(self):
		company = (
			frappe.defaults.get_user_default("Company")
			or frappe.db.get_default("company")
			or frappe.db.get_value("Company", {}, "name")
		)
		if company:
			return company

		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Test Inv Co {frappe.generate_hash(length=4)}",
				"abbr": f"TI{frappe.generate_hash(length=3).upper()}",
				"default_currency": "INR",
				"country": "India",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _get_abbr(self):
		return frappe.get_cached_value("Company", self.company, "abbr")

	def _ensure_stock_in_warehouse(self, item_code, warehouse, qty, rate=100.0):
		"""Helper to ensure a warehouse has at least `qty` of `item_code`."""
		avail = inventory.get_item_availability(item_code, warehouse=warehouse)
		if avail["actual_qty"] < qty:
			deficit = qty - avail["actual_qty"]
			cost_center = frappe.db.get_value("Company", self.company, "cost_center")
			uom = frappe.db.get_value("Item", item_code, "stock_uom")
			se = frappe.get_doc(
				{
					"doctype": "Stock Entry",
					"stock_entry_type": "Material Receipt",
					"purpose": "Material Receipt",
					"company": self.company,
					"to_warehouse": warehouse,
					"items": [
						{
							"item_code": item_code,
							"qty": deficit,
							"uom": uom,
							"stock_uom": uom,
							"t_warehouse": warehouse,
							"basic_rate": rate,
							"cost_center": cost_center,
						}
					],
				}
			)
			se.insert(ignore_permissions=True)
			se.submit()

	def test_01_warehouse_setup_and_hierarchy(self):
		"""Subtask 1: Verify standard construction warehouses and custom fields are properly configured."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		transit_wh = f"Transit Store - {abbr}"
		scrap_wh = f"Scrap Store - {abbr}"

		for wh in [central_wh, site_wh, transit_wh, scrap_wh]:
			self.assertTrue(frappe.db.exists("Warehouse", wh), f"Warehouse {wh} should exist")

		# Check custom field cm_is_site_warehouse
		is_site = frappe.db.get_value("Warehouse", site_wh, "cm_is_site_warehouse")
		self.assertEqual(is_site, 1)

		# Verify non-group warehouses
		for wh in [central_wh, site_wh]:
			self.assertEqual(frappe.db.get_value("Warehouse", wh, "is_group"), 0)

	def test_02_inventory_summary_metrics_and_availability(self):
		"""Subtasks 2 & 3: Verify inventory summary KPIs and material availability calculations."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		item_code = "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		# Ensure stock exists
		self._ensure_stock_in_warehouse(item_code, central_wh, 50, rate=350.0)

		data = inventory.get_inventory_summary(company=self.company)
		kpis = data["kpis"]
		items = data["items"]

		self.assertTrue(kpis["total_items"] > 0)
		self.assertTrue(kpis["in_stock_items"] > 0)
		self.assertTrue(kpis["total_valuation"] > 0)
		self.assertTrue(kpis["warehouse_count"] > 0)

		# Check item availability details
		cem_item = next((i for i in items if i["item_code"] == item_code), None)
		self.assertIsNotNone(cem_item)
		self.assertTrue(cem_item["actual_qty"] >= 50)
		self.assertEqual(cem_item["available_qty"], max(cem_item["actual_qty"] - cem_item["reserved_qty"], 0.0))
		self.assertEqual(cem_item["status"], "In Stock")
		self.assertTrue(cem_item["stock_value"] > 0)

	def test_03_stock_transfer_updates_balances(self):
		"""Subtask 4: Verify that Stock Transfer moves stock between warehouses and updates Bin balances."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = "CM-STL-001" if frappe.db.exists("Item", "CM-STL-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		# Ensure 100 kg in source warehouse
		self._ensure_stock_in_warehouse(item_code, central_wh, 100, rate=65.0)

		# Record initial balances
		source_before = inventory.get_item_availability(item_code, warehouse=central_wh)["actual_qty"]
		target_before = inventory.get_item_availability(item_code, warehouse=site_wh)["actual_qty"]

		transfer_qty = 20.0
		result = inventory.create_stock_transfer(
			from_warehouse=central_wh,
			to_warehouse=site_wh,
			items=[{"item_code": item_code, "qty": transfer_qty}],
			company=self.company,
			remarks="Test transfer for US-15",
			submit=1,
		)

		self.assertEqual(result["docstatus"], 1)
		self.assertEqual(result["status"], "Submitted")

		# Verify balances after transfer
		source_after = inventory.get_item_availability(item_code, warehouse=central_wh)["actual_qty"]
		target_after = inventory.get_item_availability(item_code, warehouse=site_wh)["actual_qty"]

		self.assertEqual(source_after, source_before - transfer_qty)
		self.assertEqual(target_after, target_before + transfer_qty)

	def test_04_stock_transfer_validation_prevents_excess_transfer(self):
		"""Subtask 4: Verify that transfer fails when requested quantity exceeds available stock."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		avail = inventory.get_item_availability(item_code, warehouse=central_wh)["actual_qty"]
		excess_qty = avail + 999999.0

		with self.assertRaises(frappe.ValidationError):
			inventory.create_stock_transfer(
				from_warehouse=central_wh,
				to_warehouse=site_wh,
				items=[{"item_code": item_code, "qty": excess_qty}],
				company=self.company,
			)

	def test_05_stock_transfer_validation_requires_different_warehouses(self):
		"""Subtask 4: Verify that transfer rejects identical source and target warehouses."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		item_code = "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		with self.assertRaises(frappe.ValidationError):
			inventory.create_stock_transfer(
				from_warehouse=central_wh,
				to_warehouse=central_wh,
				items=[{"item_code": item_code, "qty": 5}],
				company=self.company,
			)

	def test_06_stock_transfer_with_project_association(self):
		"""Subtask 4: Verify that stock transfer records project linkage correctly."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		# Create a test project
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Test Inv Proj {frappe.generate_hash(length=4)}",
				"company": self.company,
				"status": "Open",
			}
		).insert(ignore_permissions=True)

		self._ensure_stock_in_warehouse(item_code, central_wh, 25, rate=350.0)

		res = inventory.create_stock_transfer(
			from_warehouse=central_wh,
			to_warehouse=site_wh,
			items=[{"item_code": item_code, "qty": 5}],
			project=project.name,
			company=self.company,
			submit=1,
		)

		se_doc = frappe.get_doc("Stock Entry", res["name"])
		self.assertEqual(se_doc.project, project.name)

	def test_07_warehouse_stock_breakdown_view(self):
		"""Subtask 2: Verify per-warehouse breakdown view returns accurate item positions."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		item_code = "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		self._ensure_stock_in_warehouse(item_code, central_wh, 15, rate=350.0)

		breakdown = inventory.get_warehouse_stock_breakdown(
			company=self.company, warehouse=central_wh, item_code=item_code
		)
		self.assertTrue(len(breakdown) >= 1)
		row = breakdown[0]
		self.assertEqual(row["warehouse"], central_wh)
		self.assertEqual(row["item_code"], item_code)
		self.assertTrue(row["actual_qty"] >= 15)
		self.assertTrue(row["available_qty"] >= 15)

	def test_08_permission_checks(self):
		"""Verify that unauthenticated / guest users cannot access inventory data."""
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				inventory.get_inventory_summary(company=self.company)
		finally:
			frappe.set_user("Administrator")

	def test_09_sample_stock_data_generation(self):
		"""Subtask 5: Verify sample stock data creation function executes and populates stores."""
		res = inventory.create_sample_stock_data(company=self.company)
		self.assertIn("central_warehouse", res)
		self.assertIn("site_warehouse", res)

		# Central Store must have stock
		central_bins = frappe.db.count("Bin", {"warehouse": res["central_warehouse"], "actual_qty": [">", 0]})
		self.assertTrue(central_bins > 0)

	def test_10_stock_transfer_duplicate_item_rows_over_ordering(self):
		"""Subtask 4: Verify that splitting an item across multiple rows cannot bypass available stock limits."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		avail = inventory.get_item_availability(item_code, warehouse=central_wh)["actual_qty"]
		# Split total requested into two rows such that sum > avail, but individual row <= avail
		row1 = avail * 0.6
		row2 = avail * 0.6  # Total = 1.2 * avail > avail

		with self.assertRaises(frappe.ValidationError):
			inventory.create_stock_transfer(
				from_warehouse=central_wh,
				to_warehouse=site_wh,
				items=[
					{"item_code": item_code, "qty": row1},
					{"item_code": item_code, "qty": row2},
				],
				company=self.company,
			)

	def test_11_stock_transfer_rejects_group_warehouses(self):
		"""Subtask 4: Verify that stock transfer rejects group warehouses."""
		abbr = self._get_abbr()
		parent_wh = f"All Warehouses - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		if frappe.db.exists("Warehouse", parent_wh):
			with self.assertRaises(frappe.ValidationError):
				inventory.create_stock_transfer(
					from_warehouse=parent_wh,
					to_warehouse=site_wh,
					items=[{"item_code": item_code, "qty": 1}],
					company=self.company,
				)

	def test_12_permission_isolation_and_unauthorized_access(self):
		"""Verify that restricted users without Stock Entry permissions are blocked from transfers."""
		user_email = f"restricted_inv_{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": user_email,
				"first_name": "Restricted",
				"last_name": "User",
				"roles": [{"role": "Employee"}],
			}
		).insert(ignore_permissions=True)

		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

		try:
			frappe.set_user(user_email)
			with self.assertRaises(frappe.PermissionError):
				inventory.create_stock_transfer(
					from_warehouse=central_wh,
					to_warehouse=site_wh,
					items=[{"item_code": item_code, "qty": 1}],
					company=self.company,
				)
		finally:
			frappe.set_user("Administrator")
