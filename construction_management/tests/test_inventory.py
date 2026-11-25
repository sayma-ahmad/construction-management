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

	def _item(self):
		return "CM-CEM-001" if frappe.db.exists("Item", "CM-CEM-001") else frappe.db.get_value("Item", {"is_stock_item": 1}, "name")

	def _user_with_roles(self, *roles):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": f"inv_{frappe.generate_hash(length=6)}@example.com",
				"first_name": "Inventory",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True).name

	def test_13_cancelled_transfer_reverses_stock(self):
		"""Subtask 6: Cancelling a submitted transfer restores both warehouses."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = self._item()
		self._ensure_stock_in_warehouse(item_code, central_wh, 30, rate=380.0)

		source_before = inventory.get_item_availability(item_code, warehouse=central_wh)["actual_qty"]
		target_before = inventory.get_item_availability(item_code, warehouse=site_wh)["actual_qty"]

		res = inventory.create_stock_transfer(
			from_warehouse=central_wh,
			to_warehouse=site_wh,
			items=[{"item_code": item_code, "qty": 12}],
			company=self.company,
		)
		se = frappe.get_doc("Stock Entry", res["name"])
		self.assertEqual(inventory.get_item_availability(item_code, warehouse=site_wh)["actual_qty"], target_before + 12)

		se.cancel()
		self.assertEqual(inventory.get_item_availability(item_code, warehouse=central_wh)["actual_qty"], source_before)
		self.assertEqual(inventory.get_item_availability(item_code, warehouse=site_wh)["actual_qty"], target_before)
		transfers = {t.name: t for t in inventory.get_stock_transfers(company=self.company, limit=100)}
		self.assertEqual(transfers[se.name]["status"], "Cancelled")

	def test_14_draft_transfer_does_not_move_stock(self):
		"""Subtask 4: A draft transfer keeps balances until it is submitted."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = self._item()
		self._ensure_stock_in_warehouse(item_code, central_wh, 10, rate=380.0)
		target_before = inventory.get_item_availability(item_code, warehouse=site_wh)["actual_qty"]

		res = inventory.create_stock_transfer(
			from_warehouse=central_wh,
			to_warehouse=site_wh,
			items=[{"item_code": item_code, "qty": 4}],
			company=self.company,
			submit=0,
		)
		self.assertEqual(res["docstatus"], 0)
		self.assertEqual(inventory.get_item_availability(item_code, warehouse=site_wh)["actual_qty"], target_before)

	def test_15_invalid_quantity_project_and_uom_handling(self):
		"""Subtask 4: Zero/negative quantities and unknown projects are rejected; stock UOM is enforced."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = self._item()
		self._ensure_stock_in_warehouse(item_code, central_wh, 5, rate=380.0)

		for qty in (0, -3):
			with self.assertRaises(frappe.ValidationError):
				inventory.create_stock_transfer(central_wh, site_wh, [{"item_code": item_code, "qty": qty}], company=self.company)

		with self.assertRaises(frappe.ValidationError):
			inventory.create_stock_transfer(
				central_wh, site_wh, [{"item_code": item_code, "qty": 1}], project="NO-SUCH-PROJECT", company=self.company
			)

		res = inventory.create_stock_transfer(
			central_wh, site_wh, [{"item_code": item_code, "qty": 1, "uom": "Kg"}], company=self.company, submit=0
		)
		row = frappe.get_doc("Stock Entry", res["name"]).items[0]
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
		self.assertEqual((row.uom, row.stock_uom, flt(row.conversion_factor)), (stock_uom, stock_uom, 1.0))

	def test_16_sample_stock_data_is_idempotent(self):
		"""Subtask 5: Running the sample stock generator twice creates no extra entries."""
		first = inventory.create_sample_stock_data(company=self.company)
		entries_before = frappe.db.count("Stock Entry", {"company": self.company})
		bins_before = {
			b.warehouse: b.actual_qty
			for b in frappe.get_all("Bin", filters={"item_code": "CM-CEM-001"}, fields=["warehouse", "actual_qty"])
		}

		second = inventory.create_sample_stock_data(company=self.company)
		self.assertEqual(first["material_receipt"], second["material_receipt"])
		self.assertEqual(first["stock_transfer"], second["stock_transfer"])
		self.assertEqual(frappe.db.count("Stock Entry", {"company": self.company}), entries_before)
		self.assertEqual(
			{
				b.warehouse: b.actual_qty
				for b in frappe.get_all("Bin", filters={"item_code": "CM-CEM-001"}, fields=["warehouse", "actual_qty"])
			},
			bins_before,
		)

		transfer = frappe.get_doc("Stock Entry", second["stock_transfer"])
		self.assertEqual(transfer.docstatus, 1)
		self.assertEqual({(r.s_warehouse, r.t_warehouse) for r in transfer.items}, {(second["central_warehouse"], second["site_warehouse"])})

	def test_17_stock_read_permission_required(self):
		"""Stock balance APIs need Bin read permission; Stock Users are allowed."""
		item_code = self._item()
		no_stock_user = self._user_with_roles("Employee")
		stock_user = self._user_with_roles("Stock User")

		frappe.set_user(no_stock_user)
		for call in (
			lambda: inventory.get_item_availability(item_code),
			lambda: inventory.get_inventory_summary(company=self.company),
			lambda: inventory.get_warehouse_stock_breakdown(company=self.company),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

		frappe.set_user(stock_user)
		self.assertIn("kpis", inventory.get_inventory_summary(company=self.company))
		self.assertIn("actual_qty", inventory.get_item_availability(item_code))

	def test_18_summary_matches_bins_and_reorder_levels(self):
		"""Subtask 3: Quantities come from Bin records and low stock means strictly below reorder level."""
		data = inventory.get_inventory_summary(company=self.company)
		warehouses = frappe.get_all("Warehouse", filters={"company": self.company, "is_group": 0}, pluck="name")
		for row in data["items"]:
			bins = frappe.get_all(
				"Bin",
				filters={"item_code": row["item_code"], "warehouse": ["in", warehouses]},
				fields=["actual_qty", "stock_value"],
			)
			self.assertAlmostEqual(row["actual_qty"], sum(flt(b.actual_qty) for b in bins), places=3)
			self.assertAlmostEqual(row["stock_value"], sum(flt(b.stock_value) for b in bins), places=2)
			reorder = sum(
				flt(r)
				for r in frappe.get_all(
					"Item Reorder",
					filters={"parent": row["item_code"], "warehouse": ["in", warehouses]},
					pluck="warehouse_reorder_level",
				)
			)
			self.assertEqual(row["reorder_level"], reorder)
			if row["actual_qty"] > 0:
				self.assertEqual(row["status"] == "Low Stock", reorder > 0 and row["actual_qty"] < reorder)

	def test_19_transfer_queries_and_permissions(self):
		"""TC-07 & TC-12: Transfer Link queries return company non-group stores and stock items."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		group_wh = f"All Warehouses - {abbr}"

		wh_rows = inventory.warehouse_query("Warehouse", "", "name", 0, 50, {"company": self.company})
		wh_names = [r[0] for r in wh_rows]
		self.assertIn(central_wh, wh_names)
		self.assertIn(site_wh, wh_names)
		self.assertNotIn(group_wh, wh_names)

		central_match = inventory.warehouse_query("Warehouse", "Central", "name", 0, 20, {"company": self.company})
		self.assertIn(central_wh, [r[0] for r in central_match])

		item_rows = inventory.material_item_query("Item", "CM-CEM", "name", 0, 20, {})
		self.assertIn("CM-CEM-001", [r[0] for r in item_rows])

		restricted = self._user_with_roles("Employee")
		frappe.set_user(restricted)
		with self.assertRaises(frappe.PermissionError):
			inventory.warehouse_query("Warehouse", "", "name", 0, 20, {"company": self.company})

	def test_20_reserved_stock_validation_and_exact_available_transfer(self):
		"""TC-11: Transfers validate against available_qty (actual - reserved) and reject without creating SE."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = self._item()

		self._ensure_stock_in_warehouse(item_code, central_wh, 20, rate=380.0)
		bin_name = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": central_wh}, "name")
		orig_actual = flt(frappe.db.get_value("Bin", bin_name, "actual_qty"))
		orig_reserved = flt(frappe.db.get_value("Bin", bin_name, "reserved_qty"))
		new_reserved = orig_actual - 5.0
		frappe.db.set_value("Bin", bin_name, "reserved_qty", new_reserved, update_modified=False)

		try:
			avail_info = inventory.get_item_availability(item_code, warehouse=central_wh)
			self.assertAlmostEqual(avail_info["available_qty"], 5.0, places=3)

			se_count_before = frappe.db.count("Stock Entry", {"company": self.company})
			with self.assertRaises(frappe.ValidationError) as ctx:
				inventory.create_stock_transfer(
					from_warehouse=central_wh,
					to_warehouse=site_wh,
					items=[{"item_code": item_code, "qty": 6}],
					company=self.company,
				)
			self.assertIn("Available stock in", str(ctx.exception))
			self.assertEqual(frappe.db.count("Stock Entry", {"company": self.company}), se_count_before)

			# Exact available_qty (5.0) succeeds
			res = inventory.create_stock_transfer(
				from_warehouse=central_wh,
				to_warehouse=site_wh,
				items=[{"item_code": item_code, "qty": 5}],
				company=self.company,
				submit=1,
			)
			self.assertEqual(res["docstatus"], 1)
		finally:
			if frappe.db.exists("Bin", bin_name):
				frappe.db.set_value("Bin", bin_name, "reserved_qty", orig_reserved, update_modified=False)

	def test_21_nested_item_groups_and_breakdown_transfer_filters(self):
		"""TC-03 & TC-05: Summary includes nested Item Groups; breakdown and transfer filters apply."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"

		# Make "Cement & Concrete" a group temporarily or add a nested sub-group
		nested_group_name = f"Sub Cement {frappe.generate_hash(length=4)}"
		parent_group = "Cement & Concrete"
		orig_is_group = frappe.db.get_value("Item Group", parent_group, "is_group")
		frappe.db.set_value("Item Group", parent_group, "is_group", 1, update_modified=False)
		try:
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": nested_group_name,
					"parent_item_group": parent_group,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

			nested_item = f"CM-NEST-{frappe.generate_hash(length=4)}"
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": nested_item,
					"item_name": "Nested Portland Cement",
					"item_group": nested_group_name,
					"cm_material_type": "Civil",
					"stock_uom": "Bag",
					"is_stock_item": 1,
				}
			).insert(ignore_permissions=True)

			self._ensure_stock_in_warehouse(nested_item, central_wh, 8, rate=400.0)
			summary = inventory.get_inventory_summary(company=self.company, search=nested_item)
			self.assertTrue(any(r["item_code"] == nested_item for r in summary["items"]))

			breakdown = inventory.get_warehouse_stock_breakdown(
				company=self.company, warehouse=central_wh, search="Nested Portland"
			)
			self.assertTrue(any(r["item_code"] == nested_item for r in breakdown))

			transfer = inventory.create_stock_transfer(
				from_warehouse=central_wh,
				to_warehouse=site_wh,
				items=[{"item_code": nested_item, "qty": 2}],
				company=self.company,
				submit=1,
			)
			filtered_transfers = inventory.get_stock_transfers(
				company=self.company, warehouse=site_wh, status="Submitted", search=transfer["name"]
			)
			self.assertEqual([t["name"] for t in filtered_transfers], [transfer["name"]])
		finally:
			frappe.db.set_value("Item Group", parent_group, "is_group", orig_is_group, update_modified=False)

	def test_22_purchase_user_and_projects_user_restrictions(self):
		"""TC-17 & TC-18: Purchase User can read stock only; Projects User is blocked from page & APIs."""
		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		site_wh = f"Site Store - {abbr}"
		item_code = self._item()

		purchase_user = self._user_with_roles("Purchase User")
		projects_user = self._user_with_roles("Projects User")

		frappe.set_user(purchase_user)
		self.assertTrue(frappe.get_doc("Page", "construction-inventory").is_permitted())
		self.assertIn("kpis", inventory.get_inventory_summary(company=self.company))
		self.assertIsInstance(inventory.get_warehouse_stock_breakdown(company=self.company), list)
		self.assertTrue(len(inventory.warehouse_query("Warehouse", "", "name", 0, 20, {"company": self.company})) >= 1)
		self.assertTrue(len(inventory.material_item_query("Item", "", "name", 0, 20, {})) >= 1)
		with self.assertRaises(frappe.PermissionError):
			inventory.create_stock_transfer(central_wh, site_wh, [{"item_code": item_code, "qty": 1}], company=self.company)
		with self.assertRaises(frappe.PermissionError):
			inventory.get_stock_transfers(company=self.company)

		frappe.set_user(projects_user)
		self.assertFalse(frappe.get_doc("Page", "construction-inventory").is_permitted())
		for call in (
			lambda: inventory.get_inventory_summary(company=self.company),
			lambda: inventory.get_warehouse_stock_breakdown(company=self.company),
			lambda: inventory.get_item_availability(item_code, warehouse=central_wh),
			lambda: inventory.get_stock_transfers(company=self.company),
			lambda: inventory.create_stock_transfer(central_wh, site_wh, [{"item_code": item_code, "qty": 1}], company=self.company),
			lambda: inventory.warehouse_query("Warehouse", "", "name", 0, 20, {"company": self.company}),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_23_grn_submission_updates_inventory_summary(self):
		"""TC-15: Submitting a Purchase Receipt (GRN) increases inventory summary stock."""
		from frappe.utils import add_days, nowdate
		from construction_management.grn import make_grn

		abbr = self._get_abbr()
		central_wh = f"Central Store - {abbr}"
		item_code = self._item()

		supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"Inv GRN Sup {frappe.generate_hash(length=4)}",
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
				"cm_specialization": "Cement & Concrete",
			}
		).insert(ignore_permissions=True)

		before_summary = next(
			r["actual_qty"]
			for r in inventory.get_inventory_summary(company=self.company, warehouse=central_wh)["items"]
			if r["item_code"] == item_code
		)

		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": supplier.name,
				"company": self.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 3),
				"set_warehouse": central_wh,
				"items": [
					{
						"item_code": item_code,
						"qty": 10,
						"rate": 380,
						"warehouse": central_wh,
						"schedule_date": add_days(nowdate(), 3),
					}
				],
			}
		).insert(ignore_permissions=True)
		po.submit()

		grn_name = make_grn(
			po.name,
			[{"purchase_order_item": po.items[0].name, "qty": 10}],
			warehouse=central_wh,
		)
		# Draft GRN must not change inventory summary
		mid_summary = next(
			r["actual_qty"]
			for r in inventory.get_inventory_summary(company=self.company, warehouse=central_wh)["items"]
			if r["item_code"] == item_code
		)
		self.assertAlmostEqual(mid_summary, before_summary, places=3)

		grn = frappe.get_doc("Purchase Receipt", grn_name)
		grn.submit()

		after_summary = next(
			r["actual_qty"]
			for r in inventory.get_inventory_summary(company=self.company, warehouse=central_wh)["items"]
			if r["item_code"] == item_code
		)
		self.assertAlmostEqual(after_summary, before_summary + 10.0, places=3)

	def test_24_workspace_and_page_metadata(self):
		"""TC-02 & TC-14: Verify Page and Workspace shortcut metadata registration."""
		page = frappe.get_doc("Page", "construction-inventory")
		self.assertEqual(page.standard, "Yes")
		self.assertEqual(page.module, "Construction Management")

		ws = frappe.get_doc("Workspace", "Construction Management")
		shortcuts = {s.label: (s.type, s.link_to) for s in ws.shortcuts}
		self.assertEqual(shortcuts.get("Inventory"), ("Page", "construction-inventory"))
		self.assertEqual(shortcuts.get("Stock Transfers"), ("DocType", "Stock Entry"))
