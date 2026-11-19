# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

from copy import deepcopy
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint, flt

from construction_management import demo_data, materials


class TestDemoData(FrappeTestCase):
	"""Comprehensive tests for US-18 sample construction data generator."""

	def _require_erpnext_address_fields(self):
		if not frappe.db.has_column("Address", "tax_category"):
			self.skipTest(
				"Requires ERPNext Address custom fields (`Address.tax_category`); "
				"run ERPNext setup/migration first."
			)

	def _create_isolated_company(self, currency="INR", country="India", perpetual=1):
		suffix = frappe.generate_hash(length=4).upper()
		abbr = f"D{suffix[:4]}"
		company_name = f"Demo Test Co {suffix}"
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company_name,
				"abbr": abbr,
				"default_currency": currency,
				"country": country,
				"enable_perpetual_inventory": perpetual,
			}
		)
		company.insert(ignore_permissions=True)
		company.reload()
		warehouse = frappe.db.get_value(
			"Warehouse",
			{"company": company.name, "is_group": 0, "disabled": 0},
			"name",
			order_by="creation asc",
		)
		return company, warehouse

	def _isolated_projects(self, tag=None):
		token = tag or frappe.generate_hash(length=5).upper()
		isolated = []
		for spec in deepcopy(demo_data.SAMPLE_PROJECTS):
			spec["project_name"] = f"{spec['project_name']} [{token}]"
			isolated.append(spec)
		return tuple(isolated)

	def test_01_full_demo_data_generation_and_relationships(self):
		self._require_erpnext_address_fields()
		self.assertSetEqual(
			{p["project_name"] for p in demo_data.SAMPLE_PROJECTS},
			{
				"Riverside Apartments",
				"Metro Office Tower",
				"Green Valley Villas",
				"City Mall Renovation",
				"Sunrise School Block",
			},
		)

		company, warehouse = self._create_isolated_company()
		expected_group = frappe.db.get_value("Warehouse", warehouse, "parent_warehouse")
		isolated_projects = self._isolated_projects()

		with patch.object(demo_data, "SAMPLE_PROJECTS", isolated_projects):
			result = demo_data.create_sample_data(company=company.name, warehouse=warehouse)

		self.assertEqual(result["company"], company.name)
		self.assertEqual(result["currency"], "INR")
		self.assertEqual(result["warehouse"], warehouse)

		counts = result["counts"]
		self.assertEqual(counts["Project"]["created"], 5)
		self.assertEqual(counts["Task"]["created"], 7 + 16)
		self.assertEqual(counts["Issue"]["created"], 5)
		self.assertEqual(counts["Daily Progress Report"]["created"], 6)
		self.assertEqual(counts["Stock Entry"]["created"], 2)
		self.assertEqual(counts["Material Request"]["created"], 4)
		self.assertEqual(counts["Purchase Order"]["created"], 4)
		self.assertEqual(counts["Purchase Receipt"]["created"], 2)
		self.assertEqual(counts["Purchase Invoice"]["created"], 2)
		self.assertEqual(counts["Item Reorder"]["created"], 8)

		# Projects match company and mixed status distribution
		projects = frappe.get_all(
			"Project",
			filters={"name": ["in", result["records"]["projects"]]},
			fields=["name", "project_name", "status", "company"],
		)
		self.assertEqual(len(projects), 5)
		self.assertTrue(all(p.company == company.name for p in projects))
		self.assertSetEqual({p.status for p in projects}, {"Open", "On hold", "Completed"})

		# Group phases and leaf tasks link cleanly to their Projects
		phases = frappe.get_all(
			"Task",
			filters={"name": ["in", result["records"]["phases"]]},
			fields=["name", "project", "is_group"],
		)
		self.assertEqual(len(phases), 7)
		self.assertTrue(all(t.is_group == 1 and t.project in result["records"]["projects"] for t in phases))

		tasks = frappe.get_all(
			"Task",
			filters={"name": ["in", result["records"]["tasks"]]},
			fields=["name", "project", "parent_task", "is_group", "status"],
		)
		self.assertEqual(len(tasks), 16)
		phase_project_map = {p.name: p.project for p in phases}
		self.assertTrue(all(t.is_group == 0 and t.parent_task in phase_project_map for t in tasks))
		self.assertTrue(all(t.project == phase_project_map[t.parent_task] for t in tasks))
		self.assertTrue({"Completed", "Working", "Pending Review", "Open", "Overdue"}.issubset({t.status for t in tasks}))

		# Issues link to sample projects
		issues = frappe.get_all(
			"Issue",
			filters={"name": ["in", result["records"]["issues"]]},
			fields=["name", "project", "status"],
		)
		self.assertEqual(len(issues), 5)
		self.assertTrue(all(iss.project in result["records"]["projects"] for iss in issues))
		self.assertSetEqual({iss.status for iss in issues}, {"Open", "On Hold", "Replied", "Resolved"})

		# DPR lifecycle (docstatus, review_status, reviewer metadata) & child constraints
		dprs = [frappe.get_doc("Daily Progress Report", name) for name in result["records"]["dprs"]]
		self.assertEqual(len(dprs), 6)
		self.assertEqual([(d.docstatus, d.review_status) for d in dprs].count((1, "Approved")), 3)
		self.assertEqual([(d.docstatus, d.review_status) for d in dprs].count((1, "Pending Review")), 2)
		self.assertEqual([(d.docstatus, d.review_status) for d in dprs].count((0, "Draft")), 1)
		for dpr in dprs:
			if dpr.review_status == "Approved":
				self.assertTrue(bool(dpr.reviewed_by))
				self.assertTrue(bool(dpr.reviewed_on))
			self.assertGreater(dpr.total_workers, 0)
			self.assertGreater(dpr.total_machinery, 0)
			self.assertTrue(len(dpr.task_progress) >= 1)
			for row in dpr.task_progress:
				self.assertEqual(frappe.db.get_value("Task", row.task, "project"), dpr.project)
			for mrow in dpr.manpower:
				self.assertTrue(bool(mrow.contractor))
				self.assertTrue(frappe.db.exists("Supplier", mrow.contractor))

		# Stock Entries submitted with expected types
		stock_entries = frappe.get_all(
			"Stock Entry",
			filters={"name": ["in", result["records"]["stock_entries"]]},
			fields=["name", "docstatus", "stock_entry_type"],
		)
		self.assertEqual(len(stock_entries), 2)
		self.assertTrue(all(se.docstatus == 1 for se in stock_entries))
		self.assertSetEqual(
			{se.stock_entry_type for se in stock_entries},
			{"Material Receipt", "Material Issue"},
		)

		# Material Requests submitted and natively transitioned statuses
		mrs = frappe.get_all(
			"Material Request",
			filters={"name": ["in", result["records"]["material_requests"]]},
			fields=["name", "docstatus", "status", "per_ordered"],
		)
		self.assertEqual(len(mrs), 4)
		self.assertTrue(all(m.docstatus == 1 for m in mrs))
		self.assertEqual({m.status for m in mrs}, {"Received", "Partially Ordered", "Pending"})

		# Purchase Orders submitted, linked to MRs (first 3), and natively transitioned statuses
		po_docs = [frappe.get_doc("Purchase Order", name) for name in result["records"]["purchase_orders"]]
		self.assertEqual(len(po_docs), 4)
		self.assertTrue(all(po.docstatus == 1 for po in po_docs))
		self.assertTrue(
			{"To Bill", "Completed", "To Receive and Bill", "To Receive"}.issubset(
				{po.status for po in po_docs}
			)
		)
		mr_names_set = set(result["records"]["material_requests"])
		for po_doc in po_docs[:3]:
			self.assertTrue(all(row.material_request in mr_names_set for row in po_doc.items))
			self.assertTrue(all(bool(row.material_request_item) for row in po_doc.items))

		# Purchase Receipts submitted, natively transitioned statuses, and linked to Purchase Orders
		pr_docs = [frappe.get_doc("Purchase Receipt", name) for name in result["records"]["purchase_receipts"]]
		self.assertEqual(len(pr_docs), 2)
		self.assertTrue(all(pr.docstatus == 1 for pr in pr_docs))
		self.assertSetEqual({pr.status for pr in pr_docs}, {"To Bill", "Completed"})
		po_names_set = set(result["records"]["purchase_orders"])
		for pr_doc in pr_docs:
			self.assertTrue(all(row.purchase_order in po_names_set for row in pr_doc.items))
			self.assertTrue(all(bool(row.purchase_order_item) for row in pr_doc.items))

		# Purchase Invoices submitted, outstanding balance > 0, and linked to PR or PO
		pi_docs = [frappe.get_doc("Purchase Invoice", name) for name in result["records"]["purchase_invoices"]]
		self.assertEqual(len(pi_docs), 2)
		self.assertTrue(all(pi.docstatus == 1 and flt(pi.outstanding_amount) > 0 for pi in pi_docs))
		self.assertSetEqual({pi.status for pi in pi_docs}, {"Unpaid", "Overdue"})
		pr_names_set = set(result["records"]["purchase_receipts"])
		for pi_doc in pi_docs:
			self.assertTrue(
				all(
					(row.purchase_receipt in pr_names_set) or (row.purchase_order in po_names_set)
					for row in pi_doc.items
				)
			)

		# Item Reorder warehouse and warehouse_group correctness
		for item_code, (expected_lvl, _qty) in demo_data.ITEM_REORDER_SPECS.items():
			item_doc = frappe.get_doc("Item", item_code)
			matching_rules = [r for r in item_doc.reorder_levels if r.warehouse == warehouse]
			self.assertEqual(len(matching_rules), 1)
			self.assertEqual(flt(matching_rules[0].warehouse_reorder_level), expected_lvl)
			if expected_group and cint(frappe.db.get_value("Warehouse", expected_group, "is_group")):
				self.assertEqual(matching_rules[0].warehouse_group, expected_group)

		# Final Bin stock quantities after opening receipt + PRs + issue
		bin_map = {
			row.item_code: flt(row.actual_qty)
			for row in frappe.get_all(
				"Bin",
				filters={"warehouse": warehouse, "item_code": ["in", list(demo_data.ITEM_REORDER_SPECS)]},
				fields=["item_code", "actual_qty"],
			)
		}
		self.assertEqual(bin_map["CM-CEM-001"], 270.0)
		self.assertEqual(bin_map["CM-STL-001"], 1500.0)
		self.assertEqual(bin_map["CM-AGG-001"], 70.0)
		self.assertEqual(bin_map["CM-AGG-002"], 55.0)
		self.assertEqual(bin_map["CM-MAS-001"], 4800.0)
		self.assertEqual(bin_map["CM-MAS-002"], 1800.0)
		self.assertEqual(bin_map["CM-PLB-001"], 260.0)
		self.assertEqual(bin_map["CM-ELE-001"], 250.0)
		self.assertSetEqual(set(result["low_stock_items"]), {"CM-STL-001", "CM-ELE-001"})

	def test_02_idempotency_no_duplicate_records_or_ledgers(self):
		self._require_erpnext_address_fields()
		company, warehouse = self._create_isolated_company()
		isolated_projects = self._isolated_projects()

		with patch.object(demo_data, "SAMPLE_PROJECTS", isolated_projects):
			first = demo_data.create_sample_data(company=company.name, warehouse=warehouse)

			sle_before = frappe.db.count("Stock Ledger Entry", {"company": company.name})
			gle_before = frappe.db.count("GL Entry", {"company": company.name})
			proj_before = frappe.db.count("Project", {"company": company.name})
			mr_before = frappe.db.count("Material Request", {"company": company.name})
			po_before = frappe.db.count("Purchase Order", {"company": company.name})
			pr_before = frappe.db.count("Purchase Receipt", {"company": company.name})
			pi_before = frappe.db.count("Purchase Invoice", {"company": company.name})
			se_before = frappe.db.count("Stock Entry", {"company": company.name})

			second = demo_data.create_sample_data(company=company.name, warehouse=warehouse)

		for dt, count_info in second["counts"].items():
			self.assertEqual(count_info["created"], 0, f"Unexpected new {dt} created on rerun")

		self.assertEqual(second["records"], first["records"])
		self.assertEqual(frappe.db.count("Stock Ledger Entry", {"company": company.name}), sle_before)
		self.assertEqual(frappe.db.count("GL Entry", {"company": company.name}), gle_before)
		self.assertEqual(frappe.db.count("Project", {"company": company.name}), proj_before)
		self.assertEqual(frappe.db.count("Material Request", {"company": company.name}), mr_before)
		self.assertEqual(frappe.db.count("Purchase Order", {"company": company.name}), po_before)
		self.assertEqual(frappe.db.count("Purchase Receipt", {"company": company.name}), pr_before)
		self.assertEqual(frappe.db.count("Purchase Invoice", {"company": company.name}), pi_before)
		self.assertEqual(frappe.db.count("Stock Entry", {"company": company.name}), se_before)

	def test_03_project_collision_disabled_vendor_and_user_preservation(self):
		self._require_erpnext_address_fields()
		company, warehouse = self._create_isolated_company()
		isolated_projects = self._isolated_projects()

		# 1. Create a fresh unrelated Project colliding on the first isolated sample project_name
		colliding_name = isolated_projects[0]["project_name"]
		user_proj = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": colliding_name,
				"company": company.name,
				"notes": "Custom user project - must remain untouched",
			}
		).insert(ignore_permissions=True)

		with patch.object(demo_data, "SAMPLE_PROJECTS", isolated_projects):
			with self.assertRaises(frappe.ValidationError) as ctx:
				demo_data.create_sample_data(company=company.name, warehouse=warehouse)

		self.assertIn(colliding_name, str(ctx.exception))
		self.assertEqual(
			frappe.db.get_value("Project", user_proj.name, "notes"),
			"Custom user project - must remain untouched",
		)
		self.assertEqual(frappe.db.count("Project", {"company": company.name}), 1)
		self.assertEqual(frappe.db.count("Task", {"company": company.name}), 0)
		self.assertEqual(frappe.db.count("Material Request", {"company": company.name}), 0)
		self.assertEqual(frappe.db.count("Purchase Order", {"company": company.name}), 0)

		# 2. Disabled/On-hold sample vendor preflight check leaves records untouched
		sup_name = demo_data.SUBCONTRACTOR_VENDOR["supplier_name"]
		if not frappe.db.exists("Supplier", {"supplier_name": sup_name}):
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_type": "Company",
					"country": company.country,
					"disabled": 1,
					**demo_data.SUBCONTRACTOR_VENDOR,
				}
			).insert(ignore_permissions=True)
		else:
			frappe.db.set_value("Supplier", {"supplier_name": sup_name}, "disabled", 1)

		non_colliding_projects = self._isolated_projects()
		with patch.object(demo_data, "SAMPLE_PROJECTS", non_colliding_projects):
			with self.assertRaises(frappe.ValidationError) as vctx:
				demo_data.create_sample_data(company=company.name, warehouse=warehouse)
		self.assertIn(sup_name, str(vctx.exception))
		self.assertEqual(frappe.db.count("Project", {"company": company.name}), 1)
		self.assertEqual(frappe.db.count("Purchase Order", {"company": company.name}), 0)

		# Restore supplier flag inside transaction and verify unrelated user data + UOM preservation
		frappe.db.set_value("Supplier", {"supplier_name": sup_name}, "disabled", 0)
		custom_proj = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"User Site {frappe.generate_hash(length=5)}",
				"company": company.name,
			}
		).insert(ignore_permissions=True)
		custom_task = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": "User Custom Task",
				"project": custom_proj.name,
			}
		).insert(ignore_permissions=True)

		if frappe.db.exists("UOM", "Kg"):
			kg_whole_before = frappe.db.get_value("UOM", "Kg", "must_be_whole_number")
		else:
			kg_whole_before = None

		with patch.object(demo_data, "SAMPLE_PROJECTS", non_colliding_projects):
			result = demo_data.create_sample_data(company=company.name, warehouse=warehouse)

		self.assertNotIn(custom_proj.name, result["records"]["projects"])
		self.assertTrue(frappe.db.exists("Project", custom_proj.name))
		self.assertTrue(frappe.db.exists("Task", custom_task.name))
		if kg_whole_before is not None:
			self.assertEqual(frappe.db.get_value("UOM", "Kg", "must_be_whole_number"), kg_whole_before)

	def test_04_missing_prerequisites_fail_safely(self):
		self._require_erpnext_address_fields()

		# 1. Missing Company
		with self.assertRaises(frappe.ValidationError):
			demo_data.validate_prerequisites(company="NonExistent Company XYZ")

		# 2. Missing / Invalid Warehouse
		company, warehouse = self._create_isolated_company()
		with self.assertRaises(frappe.ValidationError):
			demo_data.validate_prerequisites(company=company.name, warehouse="NonExistent Warehouse XYZ")

		group_wh = frappe.db.get_value("Warehouse", {"company": company.name, "is_group": 1}, "name")
		self.assertTrue(bool(group_wh))
		with self.assertRaises(frappe.ValidationError):
			demo_data.validate_prerequisites(company=company.name, warehouse=group_wh)

		# 3. Deterministic missing UOM check without modifying real UOM records
		with patch.object(demo_data, "REQUIRED_UOMS", (("NonExistent Demo UOM", 0),)):
			with self.assertRaises(frappe.ValidationError) as uom_ctx:
				demo_data.validate_prerequisites(
					company=company.name, warehouse=warehouse, verify_uoms=True
				)
		self.assertIn("NonExistent Demo UOM", str(uom_ctx.exception))

		# 4. Insufficient Company accounting configuration leaves zero partial records
		frappe.local.flags.ignore_chart_of_accounts = True
		try:
			co_bare = frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": f"Bare Co {frappe.generate_hash(length=5)}",
					"abbr": f"B{frappe.generate_hash(length=3).upper()}",
					"default_currency": "INR",
					"country": "India",
					"enable_perpetual_inventory": 0,
				}
			).insert(ignore_permissions=True)
		finally:
			frappe.local.flags.ignore_chart_of_accounts = False

		bare_wh = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "Bare Main Store",
				"company": co_bare.name,
			}
		).insert(ignore_permissions=True).name

		frappe.db.set_value(
			"Company",
			co_bare.name,
			{
				"default_payable_account": None,
				"default_expense_account": None,
				"cost_center": None,
				"stock_received_but_not_billed": None,
				"stock_adjustment_account": None,
			},
		)
		frappe.db.delete("Cost Center", {"company": co_bare.name})

		proj_count_before = frappe.db.count("Project", {"company": co_bare.name})
		with self.assertRaises(frappe.ValidationError) as ctx:
			demo_data.create_sample_data(company=co_bare.name, warehouse=bare_wh)

		self.assertIn("missing prerequisites", str(ctx.exception).lower())
		self.assertEqual(frappe.db.count("Project", {"company": co_bare.name}), proj_count_before)
		self.assertEqual(frappe.db.count("Purchase Order", {"company": co_bare.name}), 0)
		self.assertEqual(frappe.db.count("Stock Entry", {"company": co_bare.name}), 0)

	def test_05_non_whitelisted_and_admin_system_manager_only(self):
		# create_sample_data must not be exposed as a whitelisted HTTP endpoint
		self.assertNotIn(demo_data.create_sample_data, frappe.whitelisted)

		for role in ("Projects User", "Projects Manager"):
			email = f"demo_{role.lower().replace(' ', '_')}_{frappe.generate_hash(length=5)}@example.com"
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Demo",
					"last_name": role,
					"send_welcome_email": 0,
					"roles": [{"role": role}],
				}
			).insert(ignore_permissions=True)
			frappe.set_user(user.name)
			try:
				with self.assertRaises(frappe.PermissionError):
					demo_data.create_sample_data()
			finally:
				frappe.set_user("Administrator")

	def test_06_mid_run_failure_rolls_back_all_changes(self):
		self._require_erpnext_address_fields()
		company, warehouse = self._create_isolated_company()
		isolated_projects = self._isolated_projects()

		# Pre-existing unrelated user Project must survive a failed demo run
		user_proj = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Keep Existing {frappe.generate_hash(length=5)}",
				"company": company.name,
			}
		).insert(ignore_permissions=True)

		# Ensure a taxonomy Item Group and Supplier would be created inside the transaction
		if frappe.db.exists("Item Group", "Plumbing"):
			pass
		test_subcontractor_name = f"Rollback Subcontractor {frappe.generate_hash(length=4)}"
		sub_spec = {**demo_data.SUBCONTRACTOR_VENDOR, "supplier_name": test_subcontractor_name}

		# Clear custom sample item group temporarily inside test txn if empty of links so we verify taxonomy rollback
		extra_item_group = f"Demo Rollback Cat {frappe.generate_hash(length=4)}"
		patched_cats = [*materials.MATERIAL_CATEGORIES, extra_item_group]

		dpr_before = frappe.db.count(
			"Daily Progress Report", {"remarks": ["like", "%[CM-DEMO:DPR-%"]}
		)

		with (
			patch.object(demo_data, "SAMPLE_PROJECTS", isolated_projects),
			patch.object(demo_data, "SUBCONTRACTOR_VENDOR", sub_spec),
			patch.object(materials, "MATERIAL_CATEGORIES", patched_cats),
			patch.object(demo_data, "_ensure_purchase_receipts", side_effect=RuntimeError("Simulated PR failure")),
		):
			with self.assertRaises(RuntimeError):
				demo_data.create_sample_data(company=company.name, warehouse=warehouse)

		# Only pre-existing user_proj survives; all created projects, tasks, issues, DPRs,
		# MRs, POs, Stock Entries, ledgers, new Supplier, and new Item Group rolled back cleanly
		self.assertTrue(frappe.db.exists("Project", user_proj.name))
		self.assertEqual(frappe.db.count("Project", {"company": company.name}), 1)
		self.assertEqual(frappe.db.count("Task", {"company": company.name}), 0)
		self.assertEqual(frappe.db.count("Issue", {"company": company.name}), 0)
		self.assertEqual(
			frappe.db.count("Daily Progress Report", {"project": ["in", [user_proj.name]]}), 0
		)
		self.assertEqual(
			frappe.db.count("Daily Progress Report", {"remarks": ["like", "%[CM-DEMO:DPR-%"]}),
			dpr_before,
		)
		self.assertEqual(frappe.db.count("Stock Entry", {"company": company.name}), 0)
		self.assertEqual(frappe.db.count("Material Request", {"company": company.name}), 0)
		self.assertEqual(frappe.db.count("Purchase Order", {"company": company.name}), 0)
		self.assertEqual(frappe.db.count("Stock Ledger Entry", {"company": company.name}), 0)
		self.assertEqual(frappe.db.count("GL Entry", {"company": company.name}), 0)
		self.assertFalse(frappe.db.exists("Supplier", {"supplier_name": test_subcontractor_name}))
		self.assertFalse(frappe.db.exists("Item Group", extra_item_group))

	def test_07_non_inr_company_currency_consistency(self):
		self._require_erpnext_address_fields()
		company, warehouse = self._create_isolated_company(currency="USD", country="United States")
		if not frappe.db.exists("Price List", {"buying": 1, "currency": "USD", "enabled": 1}):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": f"USD Buying {frappe.generate_hash(length=4)}",
					"currency": "USD",
					"buying": 1,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		isolated_projects = self._isolated_projects()

		with patch.object(demo_data, "SAMPLE_PROJECTS", isolated_projects):
			result = demo_data.create_sample_data(company=company.name, warehouse=warehouse)

		self.assertEqual(result["currency"], "USD")
		pos = frappe.get_all(
			"Purchase Order",
			filters={"name": ["in", result["records"]["purchase_orders"]]},
			fields=["name", "currency", "conversion_rate", "docstatus"],
		)
		self.assertEqual(len(pos), 4)
		self.assertTrue(all(po.currency == "USD" and flt(po.conversion_rate) == 1.0 and po.docstatus == 1 for po in pos))

		pis = frappe.get_all(
			"Purchase Invoice",
			filters={"name": ["in", result["records"]["purchase_invoices"]]},
			fields=["name", "currency", "conversion_rate", "outstanding_amount", "docstatus"],
		)
		self.assertEqual(len(pis), 2)
		self.assertTrue(
			all(
				pi.currency == "USD"
				and flt(pi.conversion_rate) == 1.0
				and pi.docstatus == 1
				and flt(pi.outstanding_amount) > 0
				for pi in pis
			)
		)

	def test_08_project_phase_task_date_range_consistency(self):
		self._require_erpnext_address_fields()
		company, warehouse = self._create_isolated_company()
		isolated_projects = self._isolated_projects()

		with patch.object(demo_data, "SAMPLE_PROJECTS", isolated_projects):
			result = demo_data.create_sample_data(company=company.name, warehouse=warehouse)

		projects = {
			p.name: p
			for p in frappe.get_all(
				"Project",
				filters={"name": ["in", result["records"]["projects"]]},
				fields=["name", "expected_start_date", "expected_end_date"],
			)
		}
		phases = {
			t.name: t
			for t in frappe.get_all(
				"Task",
				filters={"name": ["in", result["records"]["phases"]]},
				fields=["name", "project", "exp_start_date", "exp_end_date"],
			)
		}
		tasks = frappe.get_all(
			"Task",
			filters={"name": ["in", result["records"]["tasks"]]},
			fields=["name", "project", "parent_task", "exp_start_date", "exp_end_date", "status"],
		)

		for proj in projects.values():
			self.assertLessEqual(proj.expected_start_date, proj.expected_end_date)

		for phase in phases.values():
			proj = projects[phase.project]
			self.assertLessEqual(phase.exp_start_date, phase.exp_end_date)
			self.assertGreaterEqual(phase.exp_start_date, proj.expected_start_date)
			self.assertLessEqual(phase.exp_end_date, proj.expected_end_date)

		for task in tasks:
			proj = projects[task.project]
			phase = phases[task.parent_task]
			self.assertLessEqual(task.exp_start_date, task.exp_end_date)
			self.assertGreaterEqual(task.exp_start_date, proj.expected_start_date)
			self.assertLessEqual(task.exp_end_date, proj.expected_end_date)
			self.assertGreaterEqual(task.exp_start_date, phase.exp_start_date)
			self.assertLessEqual(task.exp_end_date, phase.exp_end_date)

		# ERPNext Task.validate_parent_project_dates() short-circuits when frappe.flags.in_test is True;
		# verify directly with in_test=False so live bench execute enforcement is exercised.
		prev_in_test = frappe.flags.in_test
		frappe.flags.in_test = False
		try:
			for name in [*result["records"]["phases"], *result["records"]["tasks"]]:
				doc = frappe.get_doc("Task", name)
				doc.validate_dates()
		finally:
			frappe.flags.in_test = prev_in_test
