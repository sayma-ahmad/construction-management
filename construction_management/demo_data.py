# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

"""Idempotent demo/sample construction data generator for development sites.

Run manually:
    bench --site <site> execute construction_management.demo_data.create_sample_data
"""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import (
	make_purchase_invoice as make_pi_from_po,
	make_purchase_receipt,
)
from erpnext.stock.doctype.material_request.material_request import make_purchase_order
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
	make_purchase_invoice as make_pi_from_pr,
)
from frappe import _
from frappe.utils import add_days, cint, flt, nowdate, nowtime

from construction_management import materials, vendors
from construction_management.construction_management.doctype.daily_progress_report.daily_progress_report import (
	approve_dpr,
)

DEMO_SAVEPOINT = "cm_demo_data_setup"

REQUIRED_UOMS = (
	("Bag", 1),
	("Kg", 0),
	("Cubic Meter", 0),
	("Nos", 1),
	("Meter", 0),
)

SUBCONTRACTOR_VENDOR = {
	"supplier_name": "BuildCraft Civil Contractors",
	"supplier_group": "Subcontractor",
	"cm_specialization": "Civil Works",
	"first_name": "Mahesh",
	"last_name": "Kulkarni",
	"mobile_no": "+91 98220 11007",
	"email_id": "projects@buildcraft.example.com",
	"address_line1": "Office 12, Baner High Street",
	"city": "Pune",
	"state": "Maharashtra",
	"pincode": "411045",
}

ITEM_RATES = {
	"CM-CEM-001": 380.0,
	"CM-STL-001": 68.0,
	"CM-AGG-001": 1400.0,
	"CM-AGG-002": 1250.0,
	"CM-MAS-001": 9.0,
	"CM-MAS-002": 45.0,
	"CM-PLB-001": 240.0,
	"CM-ELE-001": 95.0,
}

# Target reorder config: CM-STL-001 (1500 < 2000) and CM-ELE-001 (250 < 500)
# finish below reorder level after all opening, receipt, and issue transactions.
ITEM_REORDER_SPECS = {
	"CM-CEM-001": (150.0, 300.0),
	"CM-STL-001": (2000.0, 3000.0),
	"CM-AGG-001": (30.0, 50.0),
	"CM-AGG-002": (35.0, 50.0),
	"CM-MAS-001": (3000.0, 5000.0),
	"CM-MAS-002": (1000.0, 2000.0),
	"CM-PLB-001": (120.0, 200.0),
	"CM-ELE-001": (500.0, 1000.0),
}

SAMPLE_PROJECTS = (
	{
		"key": "PRJ-01",
		"marker": "CM-DEMO:PRJ-01",
		"estimated_costing": 185000000.0,
		"project_name": "Riverside Apartments",
		"status": "Open",
		"percent_complete": 78.0,
		"start_offset": -180,
		"end_offset": 90,
		"notes": "Two residential towers with 180 apartments and basement parking.",
	},
	{
		"key": "PRJ-02",
		"marker": "CM-DEMO:PRJ-02",
		"estimated_costing": 320000000.0,
		"project_name": "Metro Office Tower",
		"status": "Open",
		"percent_complete": 54.0,
		"start_offset": -150,
		"end_offset": 180,
		"notes": "22-floor commercial office tower with retail on the ground floor.",
	},
	{
		"key": "PRJ-03",
		"marker": "CM-DEMO:PRJ-03",
		"estimated_costing": 96000000.0,
		"project_name": "Green Valley Villas",
		"status": "On hold",
		"percent_complete": 32.0,
		"start_offset": -210,
		"end_offset": -10,
		"notes": "Gated community of 40 independent villas. Paused for permit revision.",
	},
	{
		"key": "PRJ-04",
		"marker": "CM-DEMO:PRJ-04",
		"estimated_costing": 42000000.0,
		"project_name": "City Mall Renovation",
		"status": "Open",
		"percent_complete": 40.0,
		"start_offset": -90,
		"end_offset": 10,
		"notes": "Facade upgrade, new food court and HVAC replacement.",
	},
	{
		"key": "PRJ-05",
		"marker": "CM-DEMO:PRJ-05",
		"estimated_costing": 68000000.0,
		"project_name": "Sunrise School Block",
		"status": "Completed",
		"percent_complete": 100.0,
		"start_offset": -300,
		"end_offset": -30,
		"notes": "Three-storey academic block with labs and an auditorium.",
	},
)

SAMPLE_PHASES = (
	("PHASE-01", "PRJ-01", "Foundation Works", -180, -4, "Working"),
	("PHASE-02", "PRJ-01", "Finishing Works", -45, 90, "Working"),
	("PHASE-03", "PRJ-02", "Superstructure Works", -150, 60, "Working"),
	("PHASE-04", "PRJ-02", "MEP Installation", 10, 180, "Open"),
	("PHASE-05", "PRJ-03", "Site & Foundation Phase", -210, -10, "Working"),
	("PHASE-06", "PRJ-04", "Interior & MEP Upgrade", -90, 10, "Working"),
	("PHASE-07", "PRJ-05", "Testing & Handover", -90, -30, "Completed"),
)

SAMPLE_TASKS = (
	("TASK-01", "PRJ-01", "PHASE-01", "Excavation and footing concrete", "Completed", "High", -180, -120, 100),
	("TASK-02", "PRJ-01", "PHASE-01", "Basement waterproofing inspection", "Overdue", "Urgent", -115, -5, 40),
	("TASK-03", "PRJ-01", "PHASE-02", "Tower A internal plastering", "Working", "High", -45, 30, 65),
	("TASK-04", "PRJ-01", "PHASE-02", "Tower B staircase railing", "Pending Review", "Medium", -30, 15, 95),
	("TASK-05", "PRJ-02", "PHASE-03", "Podium piling and pile caps", "Completed", "High", -150, -60, 100),
	("TASK-06", "PRJ-02", "PHASE-03", "Floor 14 slab casting", "Working", "High", -20, 25, 55),
	("TASK-07", "PRJ-02", "PHASE-03", "Tower crane safety audit", "Overdue", "Urgent", -25, -7, 20),
	("TASK-08", "PRJ-02", "PHASE-04", "HVAC riser ducting floors 1 to 6", "Open", "Medium", 10, 90, 0),
	("TASK-09", "PRJ-03", "PHASE-05", "Site boundary wall construction", "Completed", "Low", -210, -150, 100),
	("TASK-10", "PRJ-03", "PHASE-05", "Revised structural permit submission", "Pending Review", "Urgent", -40, -10, 80),
	("TASK-11", "PRJ-03", "PHASE-05", "Villa 1 to 10 plinth beams", "Open", "High", -30, -10, 10),
	("TASK-12", "PRJ-04", "PHASE-06", "HVAC chiller replacement", "Completed", "High", -90, -45, 100),
	("TASK-13", "PRJ-04", "PHASE-06", "Food court fit-out and ceiling", "Working", "High", -35, 5, 45),
	("TASK-14", "PRJ-04", "PHASE-06", "Facade glazing snag clearance", "Open", "Medium", 0, 10, 0),
	("TASK-15", "PRJ-05", "PHASE-07", "Auditorium acoustic paneling", "Completed", "Medium", -90, -45, 100),
	("TASK-16", "PRJ-05", "PHASE-07", "Fire NOC and occupancy handover", "Completed", "High", -44, -30, 100),
)

SAMPLE_ISSUES = (
	(
		"ISSUE-01",
		"PRJ-01",
		"Basement retaining wall water seepage",
		"Open",
		"High",
		"Minor water seepage observed near grid B-4 retaining joint after dewatering pause.",
	),
	(
		"ISSUE-02",
		"PRJ-02",
		"Tower crane swing clearance notice",
		"Open",
		"Medium",
		"Adjacent plot boundary clearance certificate required before extending jib sector.",
	),
	(
		"ISSUE-03",
		"PRJ-03",
		"Revised villa layout approval hold",
		"On Hold",
		"High",
		"Villa cluster 2 plinth works paused awaiting municipal setback amendment sign-off.",
	),
	(
		"ISSUE-04",
		"PRJ-04",
		"Food court exhaust duct clash with chilled water line",
		"Replied",
		"Medium",
		"MEP consultant issued offset routing drawing for shaft S-2.",
	),
	(
		"ISSUE-05",
		"PRJ-05",
		"Auditorium acoustic baffle alignment rectification",
		"Resolved",
		"Low",
		"Baffle channels re-leveled and inspected prior to academic block handover.",
	),
)

SAMPLE_ISSUE_TYPES = {
	"ISSUE-01": "Quality",
	"ISSUE-02": "Safety",
	"ISSUE-03": "Delay",
	"ISSUE-04": "Design",
	"ISSUE-05": "Quality",
}


def _new_counts():
	doctypes = (
		"UOM",
		"Item",
		"Item Reorder",
		"Supplier",
		"Project",
		"Task",
		"Issue",
		"Daily Progress Report",
		"Stock Entry",
		"Material Request",
		"Purchase Order",
		"Purchase Receipt",
		"Purchase Invoice",
	)
	return {dt: {"created": 0, "skipped": 0} for dt in doctypes}


def _record(counts, doctype, created):
	counts[doctype]["created" if created else "skipped"] += 1


def _resolve_company(company=None):
	if company:
		if not frappe.db.exists("Company", company):
			frappe.throw(_("Company {0} does not exist.").format(company), frappe.ValidationError)
		return company

	resolved = (
		frappe.defaults.get_global_default("company")
		or frappe.db.get_default("company")
		or frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	)
	if not resolved:
		frappe.throw(
			_("No ERPNext Company found. Complete ERPNext setup before generating sample data."),
			frappe.ValidationError,
		)
	return resolved


def _resolve_warehouse(company, warehouse=None):
	if warehouse:
		wh = frappe.db.get_value(
			"Warehouse",
			{"name": warehouse},
			["name", "company", "is_group", "disabled"],
			as_dict=True,
		)
		if not wh:
			frappe.throw(_("Warehouse {0} does not exist.").format(warehouse), frappe.ValidationError)
		if wh.company != company:
			frappe.throw(
				_("Warehouse {0} does not belong to Company {1}.").format(warehouse, company),
				frappe.ValidationError,
			)
		if cint(wh.is_group) or cint(wh.disabled):
			frappe.throw(
				_("Warehouse {0} must be an enabled non-group Warehouse.").format(warehouse),
				frappe.ValidationError,
			)
		return wh.name

	candidates = frappe.get_all(
		"Warehouse",
		filters={"company": company, "is_group": 0, "disabled": 0},
		fields=["name", "warehouse_type"],
		order_by="creation asc",
	)
	non_transit = [w.name for w in candidates if (w.warehouse_type or "").lower() != "transit"]
	chosen = non_transit[0] if non_transit else (candidates[0].name if candidates else None)
	if not chosen:
		frappe.throw(
			_("No active non-group Warehouse found for Company {0}. Create a Warehouse before generating sample data.").format(
				company
			),
			frappe.ValidationError,
		)
	return chosen


def _preflight_project_and_vendor_conflicts(target_company):
	conflicts = []

	for spec in SAMPLE_PROJECTS:
		marker = f"[{spec['marker']}]"
		existing_marker = frappe.db.get_value(
			"Project",
			{"notes": ["like", f"%{marker}%"], "company": target_company},
			"name",
		)
		if existing_marker:
			continue

		conflicting_project = frappe.db.get_value(
			"Project", {"project_name": spec["project_name"]}, "name"
		)
		if conflicting_project:
			conflicts.append(
				_(
					"Project name '{0}' is already used by existing Project {1} (missing sample marker {2})"
				).format(spec["project_name"], conflicting_project, marker)
			)

	for vendor_spec in (*vendors.SAMPLE_VENDORS, SUBCONTRACTOR_VENDOR):
		sup = frappe.db.get_value(
			"Supplier",
			{"supplier_name": vendor_spec["supplier_name"]},
			["name", "disabled", "on_hold"],
			as_dict=True,
		)
		if sup and (cint(sup.disabled) or cint(sup.on_hold)):
			conflicts.append(
				_(
					"Sample Vendor '{0}' ({1}) is currently disabled or on hold and cannot be used for procurement"
				).format(vendor_spec["supplier_name"], sup.name)
			)

	for mat_spec in materials.SAMPLE_MATERIALS:
		item = frappe.db.get_value(
			"Item",
			mat_spec["item_code"],
			["name", "disabled", "is_stock_item"],
			as_dict=True,
		)
		if item and (cint(item.disabled) or not cint(item.is_stock_item)):
			conflicts.append(
				_(
					"Sample Material '{0}' must be an active stock Item"
				).format(mat_spec["item_code"])
			)

	return conflicts


def validate_prerequisites(company=None, warehouse=None, verify_uoms=False):
	"""Validate permissions, Company, Warehouse, accounts, UOMs, and record conflicts before writes."""
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles(
		frappe.session.user
	):
		frappe.throw(
			_("Administrator or System Manager role is required to generate sample data."),
			frappe.PermissionError,
		)

	target_company = _resolve_company(company)
	target_warehouse = _resolve_warehouse(target_company, warehouse)

	comp_doc = frappe.db.get_value(
		"Company",
		target_company,
		[
			"name",
			"abbr",
			"default_currency",
			"country",
			"cost_center",
			"default_payable_account",
			"default_expense_account",
			"stock_received_but_not_billed",
			"enable_perpetual_inventory",
			"default_inventory_account",
			"stock_adjustment_account",
		],
		as_dict=True,
	)

	missing = []

	if not comp_doc.default_currency:
		missing.append(_("Default Currency for Company {0}").format(target_company))

	cost_center = comp_doc.cost_center or frappe.db.get_value(
		"Cost Center", {"company": target_company, "is_group": 0, "disabled": 0}, "name"
	)
	if not cost_center:
		missing.append(_("Default Cost Center for Company {0}").format(target_company))

	payable_account = comp_doc.default_payable_account or frappe.db.get_value(
		"Account",
		{"company": target_company, "account_type": "Payable", "is_group": 0, "disabled": 0},
		"name",
	)
	if not payable_account:
		missing.append(_("Default Payable Account (default_payable_account) for Company {0}").format(target_company))

	expense_account = comp_doc.default_expense_account or frappe.db.get_value(
		"Account",
		{
			"company": target_company,
			"account_type": ["in", ["Cost of Goods Sold", "Expense Account"]],
			"is_group": 0,
			"disabled": 0,
		},
		"name",
	)
	if not expense_account:
		missing.append(_("Default Expense Account (default_expense_account) for Company {0}").format(target_company))

	srnb_account = comp_doc.stock_received_but_not_billed or frappe.db.get_value(
		"Account",
		{"company": target_company, "account_type": "Stock Received But Not Billed", "is_group": 0, "disabled": 0},
		"name",
	)
	stock_adjustment_account = comp_doc.stock_adjustment_account or frappe.db.get_value(
		"Account",
		{"company": target_company, "account_type": "Stock Adjustment", "is_group": 0, "disabled": 0},
		"name",
	)

	if cint(comp_doc.enable_perpetual_inventory):
		if not srnb_account:
			missing.append(
				_("Stock Received But Not Billed account (stock_received_but_not_billed) for Company {0}").format(
					target_company
				)
			)
		if not stock_adjustment_account:
			missing.append(
				_("Stock Adjustment Account (stock_adjustment_account) for Company {0}").format(target_company)
			)
		wh_account = frappe.db.get_value("Warehouse", target_warehouse, "account") or comp_doc.default_inventory_account or frappe.db.get_value(
			"Account",
			{"company": target_company, "account_type": "Stock", "is_group": 0, "disabled": 0},
			"name",
		)
		if not wh_account:
			missing.append(
				_("Stock / Inventory Account for Warehouse {0} or Company {1}").format(
					target_warehouse, target_company
				)
			)

	for se_type in ("Material Receipt", "Material Issue"):
		if not frappe.db.exists("Stock Entry Type", se_type):
			missing.append(_("Stock Entry Type '{0}'").format(se_type))

	if not frappe.db.has_column("Address", "tax_category"):
		missing.append(
			_("ERPNext Address custom field 'tax_category' (run `erpnext.setup.install.create_address_and_contact_custom_fields`)")
		)

	if verify_uoms:
		for uom_name, _whole in REQUIRED_UOMS:
			if not frappe.db.exists("UOM", uom_name):
				missing.append(_("UOM '{0}'").format(uom_name))

	missing.extend(_preflight_project_and_vendor_conflicts(target_company))

	if missing:
		frappe.throw(
			_("Cannot generate sample construction data due to missing prerequisites or conflicts: {0}").format(
				"; ".join(missing)
			),
			frappe.ValidationError,
		)

	return frappe._dict(
		company=target_company,
		currency=comp_doc.default_currency,
		country=comp_doc.country or frappe.db.get_default("country") or "India",
		warehouse=target_warehouse,
		warehouse_group=frappe.db.get_value("Warehouse", target_warehouse, "parent_warehouse"),
		cost_center=cost_center,
		payable_account=payable_account,
		expense_account=expense_account,
	)


def _ensure_required_uoms(counts):
	"""Create missing UOMs required by sample construction materials without modifying existing UOMs."""
	for uom_name, must_be_whole in REQUIRED_UOMS:
		if frappe.db.exists("UOM", uom_name):
			_record(counts, "UOM", created=False)
		else:
			frappe.get_doc(
				{
					"doctype": "UOM",
					"uom_name": uom_name,
					"must_be_whole_number": must_be_whole,
				}
			).insert(ignore_permissions=True)
			_record(counts, "UOM", created=True)


def _ensure_materials_and_reorders(counts, warehouse, warehouse_group):
	sample_codes = [m["item_code"] for m in materials.SAMPLE_MATERIALS]
	existing_before = set(
		frappe.get_all("Item", filters={"item_code": ["in", sample_codes]}, pluck="item_code")
	)

	materials.create_sample_materials(run_setup=False)

	for item_code in sample_codes:
		_record(counts, "Item", created=item_code not in existing_before)

	resolved_group = warehouse_group if warehouse_group and cint(frappe.db.get_value("Warehouse", warehouse_group, "is_group")) else None

	for item_code, (reorder_level, reorder_qty) in ITEM_REORDER_SPECS.items():
		item_doc = frappe.get_doc("Item", item_code)
		has_rule = any(r.warehouse == warehouse for r in item_doc.reorder_levels)
		if has_rule:
			_record(counts, "Item Reorder", created=False)
			continue
		reorder_row = {
			"warehouse": warehouse,
			"warehouse_reorder_level": reorder_level,
			"warehouse_reorder_qty": reorder_qty,
			"material_request_type": "Purchase",
		}
		if resolved_group:
			reorder_row["warehouse_group"] = resolved_group
		item_doc.append("reorder_levels", reorder_row)
		item_doc.save(ignore_permissions=True)
		_record(counts, "Item Reorder", created=True)


def _ensure_vendors(counts, country):
	vendor_names = [v["supplier_name"] for v in vendors.SAMPLE_VENDORS]
	existing_before = set(
		frappe.get_all("Supplier", filters={"supplier_name": ["in", vendor_names]}, pluck="supplier_name")
	)

	vendors.create_sample_vendors(run_setup=False)

	for name in vendor_names:
		_record(counts, "Supplier", created=name not in existing_before)

	sub_name = frappe.db.get_value(
		"Supplier", {"supplier_name": SUBCONTRACTOR_VENDOR["supplier_name"]}, "name"
	)
	if sub_name:
		_record(counts, "Supplier", created=False)
	else:
		doc = frappe.get_doc(
			{"doctype": "Supplier", "supplier_type": "Company", "country": country, **SUBCONTRACTOR_VENDOR}
		)
		doc.insert(ignore_permissions=True)
		sub_name = doc.name
		_record(counts, "Supplier", created=True)

	resolved = {}
	for name in (*vendor_names, SUBCONTRACTOR_VENDOR["supplier_name"]):
		resolved[name] = frappe.db.get_value("Supplier", {"supplier_name": name}, "name")
	return resolved


def _ensure_projects(counts, company, today):
	projects_by_key = {}
	for spec in SAMPLE_PROJECTS:
		marker = f"[{spec['marker']}]"
		existing = frappe.db.get_value(
			"Project",
			{"notes": ["like", f"%{marker}%"], "company": company},
			"name",
		)
		if existing:
			projects_by_key[spec["key"]] = existing
			_record(counts, "Project", created=False)
			continue

		# Preflight checks guarantee no unrelated user record occupies this project_name.
		if frappe.db.exists("Project", {"project_name": spec["project_name"]}):
			frappe.throw(
				_("Project name '{0}' is already occupied by an unrelated Project.").format(
					spec["project_name"]
				),
				frappe.ValidationError,
			)

		doc = frappe.get_doc(
			{
				"doctype": "Project",
				"naming_series": "PROJ-.####",
				"project_name": spec["project_name"],
				"company": company,
				"status": spec["status"],
				"percent_complete_method": "Manual",
				"percent_complete": spec["percent_complete"],
				"estimated_costing": spec["estimated_costing"],
				"expected_start_date": add_days(today, spec["start_offset"]),
				"expected_end_date": add_days(today, spec["end_offset"]),
				"notes": f"{marker} {spec['notes']}",
			}
		)
		doc.insert(ignore_permissions=True)
		projects_by_key[spec["key"]] = doc.name
		_record(counts, "Project", created=True)
	return projects_by_key


def _ensure_tasks(counts, projects_by_key, today):
	phases_by_key = {}
	for phase_key, proj_key, subject, start_off, end_off, status in SAMPLE_PHASES:
		project = projects_by_key.get(proj_key)
		if not project:
			continue
		marker = f"[CM-DEMO:{phase_key}]"
		existing = frappe.db.get_value(
			"Task",
			{"project": project, "description": ["like", f"%{marker}%"]},
			"name",
		)
		if existing:
			phases_by_key[phase_key] = existing
			_record(counts, "Task", created=False)
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project,
				"is_group": 1,
				"status": status,
				"exp_start_date": add_days(today, start_off),
				"exp_end_date": add_days(today, end_off),
				"description": f"{marker} Phase group for {subject}",
			}
		)
		doc.insert(ignore_permissions=True)
		phases_by_key[phase_key] = doc.name
		_record(counts, "Task", created=True)

	tasks_by_key = {}
	for task_key, proj_key, phase_key, subject, status, priority, start_off, end_off, progress in SAMPLE_TASKS:
		project = projects_by_key.get(proj_key)
		if not project:
			continue
		marker = f"[CM-DEMO:{task_key}]"
		existing = frappe.db.get_value(
			"Task",
			{"project": project, "description": ["like", f"%{marker}%"]},
			"name",
		)
		if existing:
			tasks_by_key[task_key] = existing
			_record(counts, "Task", created=False)
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project,
				"parent_task": phases_by_key.get(phase_key),
				"is_group": 0,
				"status": status,
				"priority": priority,
				"exp_start_date": add_days(today, start_off),
				"exp_end_date": add_days(today, end_off),
				"progress": progress,
				"description": f"{marker} {subject}",
			}
		)
		doc.insert(ignore_permissions=True)
		tasks_by_key[task_key] = doc.name
		_record(counts, "Task", created=True)

	return {"phases": phases_by_key, "tasks": tasks_by_key}


def _resolve_issue_priority(desired):
	if desired and frappe.db.exists("Issue Priority", desired):
		return desired
	return frappe.db.get_value("Issue Priority", {}, "name")


def _ensure_issues(counts, projects_by_key, company, today):
	issue_names = []
	for issue_key, proj_key, subject, status, priority, desc in SAMPLE_ISSUES:
		project = projects_by_key.get(proj_key)
		if not project:
			continue
		marker = f"[CM-DEMO:{issue_key}]"
		existing = frappe.db.get_value(
			"Issue",
			{"project": project, "description": ["like", f"%{marker}%"]},
			"name",
		)
		if existing:
			issue_names.append(existing)
			_record(counts, "Issue", created=False)
			continue

		issue_type = SAMPLE_ISSUE_TYPES.get(issue_key)
		doc = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": subject,
				"project": project,
				"company": company,
				"issue_type": issue_type if frappe.db.exists("Issue Type", issue_type) else None,
				"status": status,
				"priority": _resolve_issue_priority(priority),
				"opening_date": today,
				"description": f"{marker} {desc}",
			}
		)
		doc.insert(ignore_permissions=True)
		issue_names.append(doc.name)
		_record(counts, "Issue", created=True)
	return issue_names


def _ensure_dprs(counts, projects_by_key, tasks_by_key, suppliers, today):
	contractor = suppliers.get(SUBCONTRACTOR_VENDOR["supplier_name"])
	dpr_specs = (
		{
			"marker": "CM-DEMO:DPR-01",
			"project_key": "PRJ-01",
			"report_date": add_days(today, -20),
			"overall_progress": 68,
			"weather": "Sunny",
			"shift": "Day",
			"work_completed": "Completed Tower A brick masonry up to 6th floor and started internal plastering.",
			"tasks": [("TASK-01", 100, "Footings cured and inspected")],
			"manpower": [("Mason", 14, 8, contractor), ("Helper", 18, 8, contractor)],
			"machinery": [("Concrete Mixer", 2, 7.5, "Operational")],
			"submit": True,
			"approve": True,
		},
		{
			"marker": "CM-DEMO:DPR-02",
			"project_key": "PRJ-01",
			"report_date": add_days(today, -5),
			"overall_progress": 78,
			"weather": "Partly Cloudy",
			"shift": "Day",
			"work_completed": "Tower A internal plastering progressed on floors 4 and 5; Tower B railing fabricated.",
			"tasks": [("TASK-03", 65, "Completed floor 4 plastering")],
			"manpower": [("Plasterer", 12, 8, contractor), ("Site Supervisor", 2, 9, contractor)],
			"machinery": [("Material Hoist", 1, 8.0, "Operational")],
			"submit": True,
			"approve": True,
		},
		{
			"marker": "CM-DEMO:DPR-03",
			"project_key": "PRJ-02",
			"report_date": add_days(today, -10),
			"overall_progress": 50,
			"weather": "Sunny",
			"shift": "Day",
			"work_completed": "Completed podium pile cap waterproofing and started floor 14 formwork.",
			"tasks": [("TASK-05", 100, "Podium pile caps signed off"), ("TASK-06", 35, "Formwork erected")],
			"manpower": [("Bar Bender", 16, 8, contractor), ("Rigger", 6, 8, contractor)],
			"machinery": [("Tower Crane", 1, 9.0, "Operational")],
			"submit": True,
			"approve": True,
		},
		{
			"marker": "CM-DEMO:DPR-04",
			"project_key": "PRJ-02",
			"report_date": add_days(today, -2),
			"overall_progress": 54,
			"weather": "Windy",
			"shift": "Day",
			"work_completed": "Completed 55% of floor 14 reinforcement tying and scheduled safety audit.",
			"tasks": [("TASK-06", 55, "Slab steel reinforcement inspection pending")],
			"manpower": [("Bar Bender", 14, 8, contractor), ("Safety Steward", 2, 8, contractor)],
			"machinery": [("Bar Cutting Machine", 2, 6.5, "Operational")],
			"submit": True,
			"approve": False,
		},
		{
			"marker": "CM-DEMO:DPR-05",
			"project_key": "PRJ-04",
			"report_date": add_days(today, -1),
			"overall_progress": 40,
			"weather": "Sunny",
			"shift": "General",
			"work_completed": "Installed food court gypsum framing and tested chilled water isolation valves.",
			"tasks": [("TASK-13", 45, "Ceiling grid framing 45% complete")],
			"manpower": [("Carpenter", 10, 8, contractor), ("MEP Technician", 6, 8, contractor)],
			"machinery": [("Scaffolding Rig", 4, 8.0, "Operational")],
			"submit": True,
			"approve": False,
		},
		{
			"marker": "CM-DEMO:DPR-06",
			"project_key": "PRJ-03",
			"report_date": today,
			"overall_progress": 32,
			"weather": "Cloudy",
			"shift": "Day",
			"work_completed": "Site housekeeping, boundary drainage inspection, and rebar stacking during permit hold.",
			"tasks": [("TASK-11", 10, "Plinth shuttering material stacked on site")],
			"manpower": [("Helper", 6, 6, contractor)],
			"machinery": [("Dewatering Pump", 1, 3.0, "Idle")],
			"submit": False,
			"approve": False,
		},
	)

	dpr_names = []
	for spec in dpr_specs:
		project = projects_by_key.get(spec["project_key"])
		if not project:
			continue
		marker = f"[{spec['marker']}]"
		existing = frappe.db.get_value(
			"Daily Progress Report",
			{"project": project, "remarks": ["like", f"%{marker}%"], "docstatus": ["!=", 2]},
			"name",
		)
		if existing:
			dpr_names.append(existing)
			_record(counts, "Daily Progress Report", created=False)
			continue

		task_rows = []
		for task_key, pct, work_done in spec["tasks"]:
			task_name = tasks_by_key.get(task_key)
			if task_name:
				task_rows.append({"task": task_name, "progress_percent": pct, "work_done": work_done})

		doc = frappe.get_doc(
			{
				"doctype": "Daily Progress Report",
				"naming_series": "DPR-.YYYY.-.#####",
				"project": project,
				"report_date": spec["report_date"],
				"weather": spec["weather"],
				"shift": spec["shift"],
				"overall_progress": spec["overall_progress"],
				"work_completed": spec["work_completed"],
				"remarks": f"{marker} Demo Daily Progress Report",
				"task_progress": task_rows,
				"manpower": [
					{
						"trade_or_role": role,
						"worker_count": count,
						"hours_worked": hours,
						"contractor": sup,
					}
					for role, count, hours, sup in spec["manpower"]
				],
				"machinery": [
					{
						"equipment_name": equip,
						"quantity": qty,
						"hours_used": hours,
						"status": st,
					}
					for equip, qty, hours, st in spec["machinery"]
				],
			}
		)
		doc.insert(ignore_permissions=True)
		if spec["submit"]:
			doc.submit()
			if spec["approve"]:
				approve_dpr(doc.name, review_remarks="Verified sample site progress report.")
		dpr_names.append(doc.name)
		_record(counts, "Daily Progress Report", created=True)
	return dpr_names


def _get_bin_qty(item_code, warehouse):
	return flt(
		frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
	)


def _ensure_stock_entry(counts, marker, se_type, company, posting_date, items_spec, warehouse):
	tag = f"[{marker}]"
	existing = frappe.db.get_value(
		"Stock Entry",
		{"remarks": ["like", f"%{tag}%"], "company": company, "docstatus": ["!=", 2]},
		"name",
	)
	if existing:
		_record(counts, "Stock Entry", created=False)
		return existing

	items = []
	for item_code, qty in items_spec:
		uom = frappe.db.get_value("Item", item_code, "stock_uom")
		row = {
			"item_code": item_code,
			"qty": qty,
			"uom": uom,
			"stock_uom": uom,
			"conversion_factor": 1.0,
		}
		if se_type == "Material Receipt":
			row["t_warehouse"] = warehouse
			row["basic_rate"] = ITEM_RATES[item_code]
		else:
			available = _get_bin_qty(item_code, warehouse)
			if available < qty:
				frappe.throw(
					_("Insufficient stock for {0} in Warehouse {1}: available {2}, required {3}.").format(
						item_code, warehouse, available, qty
					),
					frappe.ValidationError,
				)
			row["s_warehouse"] = warehouse
		items.append(row)

	doc = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"naming_series": "MAT-STE-.YYYY.-",
			"stock_entry_type": se_type,
			"company": company,
			"set_posting_time": 1,
			"posting_date": posting_date,
			"posting_time": nowtime(),
			"remarks": f"{tag} Sample construction {se_type.lower()}",
			"items": items,
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	_record(counts, "Stock Entry", created=True)
	return doc.name


def _ensure_material_requests(counts, company, warehouse, projects_by_key, today):
	mr_specs = (
		{
			"key": "MR-01",
			"title": "[CM-DEMO-MR-01] Cement & Steel - Riverside Apartments",
			"project_key": "PRJ-01",
			"tx_date": add_days(today, -30),
			"sched_date": add_days(today, -20),
			"items": [("CM-CEM-001", 100.0), ("CM-STL-001", 300.0)],
		},
		{
			"key": "MR-02",
			"title": "[CM-DEMO-MR-02] Sand & Plumbing - Metro Office Tower",
			"project_key": "PRJ-02",
			"tx_date": add_days(today, -28),
			"sched_date": add_days(today, -18),
			"items": [("CM-AGG-001", 20.0), ("CM-PLB-001", 60.0)],
		},
		{
			"key": "MR-03",
			"title": "[CM-DEMO-MR-03] Electrical Cabling - City Mall Renovation",
			"project_key": "PRJ-04",
			"tx_date": add_days(today, -15),
			"sched_date": add_days(today, 5),
			"items": [("CM-ELE-001", 1000.0)],
		},
		{
			"key": "MR-04",
			"title": "[CM-DEMO-MR-04] Aggregates & Masonry - Green Valley Villas",
			"project_key": "PRJ-03",
			"tx_date": add_days(today, -7),
			"sched_date": add_days(today, 10),
			"items": [("CM-AGG-002", 40.0), ("CM-MAS-001", 2500.0)],
		},
	)

	mrs = {}
	for spec in mr_specs:
		existing = frappe.db.get_value(
			"Material Request",
			{"title": spec["title"], "company": company, "docstatus": ["!=", 2]},
			"name",
		)
		if existing:
			mrs[spec["key"]] = existing
			_record(counts, "Material Request", created=False)
			continue

		project = projects_by_key.get(spec["project_key"])
		items = []
		for item_code, qty in spec["items"]:
			uom = frappe.db.get_value("Item", item_code, "stock_uom")
			items.append(
				{
					"item_code": item_code,
					"qty": qty,
					"uom": uom,
					"stock_uom": uom,
					"conversion_factor": 1.0,
					"schedule_date": spec["sched_date"],
					"warehouse": warehouse,
					"project": project,
				}
			)

		doc = frappe.get_doc(
			{
				"doctype": "Material Request",
				"naming_series": "MAT-MR-.YYYY.-",
				"title": spec["title"],
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project,
				"transaction_date": spec["tx_date"],
				"schedule_date": spec["sched_date"],
				"items": items,
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		mrs[spec["key"]] = doc.name
		_record(counts, "Material Request", created=True)
	return mrs


def _ensure_purchase_orders(counts, company, currency, warehouse, mrs, projects_by_key, suppliers, today):
	pos = {}
	matching_price_list = frappe.db.get_value(
		"Price List", {"buying": 1, "currency": currency, "enabled": 1}, "name"
	)

	def _create_po_from_mr(po_key, title, mr_name, supplier_name, tx_date, sched_date, project, qty_overrides=None):
		existing = frappe.db.get_value(
			"Purchase Order",
			{"title": title, "company": company, "docstatus": ["!=", 2]},
			"name",
		)
		if existing:
			if frappe.get_meta("Purchase Order").has_field("cm_material_request") and not frappe.db.get_value(
				"Purchase Order", existing, "cm_material_request"
			):
				frappe.db.set_value("Purchase Order", existing, "cm_material_request", mr_name, update_modified=False)
			pos[po_key] = existing
			_record(counts, "Purchase Order", created=False)
			return

		po_target = frappe.new_doc("Purchase Order")
		po_target.supplier = suppliers[supplier_name]
		po_target.company = company
		po_target.currency = currency
		po_target.conversion_rate = 1.0
		if matching_price_list:
			po_target.buying_price_list = matching_price_list
		po_target.price_list_currency = currency
		po_target.plc_conversion_rate = 1.0

		po = make_purchase_order(mr_name, target_doc=po_target)
		po.naming_series = "PUR-ORD-.YYYY.-"
		po.title = title
		po.supplier = suppliers[supplier_name]
		po.company = company
		po.currency = currency
		po.conversion_rate = 1.0
		if matching_price_list:
			po.buying_price_list = matching_price_list
		po.price_list_currency = currency
		po.plc_conversion_rate = 1.0
		po.transaction_date = tx_date
		po.schedule_date = sched_date
		po.set_warehouse = warehouse
		po.project = project
		if po.meta.has_field("cm_material_request"):
			po.cm_material_request = mr_name
		for row in po.items:
			if qty_overrides and row.item_code in qty_overrides:
				row.qty = qty_overrides[row.item_code]
			row.rate = ITEM_RATES[row.item_code]
			row.schedule_date = sched_date
			row.warehouse = warehouse
			row.project = project
		po.run_method("set_missing_values")
		po.insert(ignore_permissions=True)
		po.submit()
		pos[po_key] = po.name
		_record(counts, "Purchase Order", created=True)

	# PO-01 from MR-01 (full qty; will become To Bill after PR-01)
	_create_po_from_mr(
		"PO-01",
		"[CM-DEMO-PO-01] Cement & Steel Order",
		mrs["MR-01"],
		"Apex Cement Traders",
		add_days(today, -26),
		add_days(today, -20),
		projects_by_key.get("PRJ-01"),
	)

	# PO-02 from MR-02 (full qty; will become Completed after PR-02 + PI-01)
	_create_po_from_mr(
		"PO-02",
		"[CM-DEMO-PO-02] Sand & Plumbing Order",
		mrs["MR-02"],
		"Riverstone Sand & Aggregates",
		add_days(today, -25),
		add_days(today, -18),
		projects_by_key.get("PRJ-02"),
	)

	# PO-03 from MR-03 (partial qty 400 / 1000 so MR-03 stays Partially Ordered; PO-03 stays To Receive and Bill)
	_create_po_from_mr(
		"PO-03",
		"[CM-DEMO-PO-03] Electrical Cabling Partial Order",
		mrs["MR-03"],
		"Brightline Electricals",
		add_days(today, -12),
		add_days(today, 5),
		projects_by_key.get("PRJ-04"),
		qty_overrides={"CM-ELE-001": 400.0},
	)

	# PO-04 direct PO (not from MR-04 so MR-04 stays Pending; becomes To Receive if pr_required == No after PI-02)
	po4_title = "[CM-DEMO-PO-04] Plumbing & Concrete Blocks Order"
	existing_po4 = frappe.db.get_value(
		"Purchase Order",
		{"title": po4_title, "company": company, "docstatus": ["!=", 2]},
		"name",
	)
	if existing_po4:
		pos["PO-04"] = existing_po4
		_record(counts, "Purchase Order", created=False)
	else:
		proj4 = projects_by_key.get("PRJ-03")
		sched4 = add_days(today, 8)
		po4_items = []
		for item_code, qty in (("CM-PLB-001", 150.0), ("CM-MAS-002", 500.0)):
			uom = frappe.db.get_value("Item", item_code, "stock_uom")
			po4_items.append(
				{
					"item_code": item_code,
					"qty": qty,
					"uom": uom,
					"stock_uom": uom,
					"conversion_factor": 1.0,
					"rate": ITEM_RATES[item_code],
					"schedule_date": sched4,
					"warehouse": warehouse,
					"project": proj4,
				}
			)
		po4 = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"naming_series": "PUR-ORD-.YYYY.-",
				"title": po4_title,
				"supplier": suppliers["FlowRight Plumbing Supplies"],
				"company": company,
				"currency": currency,
				"conversion_rate": 1.0,
				"buying_price_list": matching_price_list,
				"price_list_currency": currency,
				"plc_conversion_rate": 1.0,
				"transaction_date": add_days(today, -25),
				"schedule_date": sched4,
				"set_warehouse": warehouse,
				"project": proj4,
				"items": po4_items,
			}
		)
		po4.run_method("set_missing_values")
		po4.insert(ignore_permissions=True)
		po4.submit()
		pos["PO-04"] = po4.name
		_record(counts, "Purchase Order", created=True)

	return pos


def _ensure_purchase_receipts(counts, company, warehouse, pos, today):
	pr_specs = (
		("PR-01", "CM-DEMO:PR-01", "CM-DEMO-DN-01", pos["PO-01"], add_days(today, -20)),
		("PR-02", "CM-DEMO:PR-02", "CM-DEMO-DN-02", pos["PO-02"], add_days(today, -20)),
	)

	prs = {}
	for pr_key, marker, dn_no, po_name, posting_date in pr_specs:
		tag = f"[{marker}]"
		existing = frappe.db.get_value(
			"Purchase Receipt",
			{"remarks": ["like", f"%{tag}%"], "company": company, "docstatus": ["!=", 2]},
			"name",
		)
		if existing:
			prs[pr_key] = existing
			_record(counts, "Purchase Receipt", created=False)
			continue

		pr = make_purchase_receipt(po_name)
		pr.naming_series = "MAT-PRE-.YYYY.-"
		pr.set_posting_time = 1
		pr.posting_date = posting_date
		pr.posting_time = nowtime()
		pr.supplier_delivery_note = dn_no
		pr.remarks = f"{tag} Site goods receipt for {po_name}"
		for row in pr.items:
			row.warehouse = warehouse
		pr.insert(ignore_permissions=True)
		pr.submit()
		prs[pr_key] = pr.name
		_record(counts, "Purchase Receipt", created=True)
	return prs


def _ensure_purchase_invoices(counts, prereqs, prs, pos, today):
	pr_required = frappe.db.get_single_value("Buying Settings", "pr_required") == "Yes"
	pis = {}

	def _create_pi(pi_key, bill_no, marker, source_doc_name, from_pr, posting_date, due_date, partial_first_item=False):
		tag = f"[{marker}]"
		existing = frappe.db.get_value(
			"Purchase Invoice",
			{"bill_no": bill_no, "company": prereqs.company, "docstatus": ["!=", 2]},
			"name",
		)
		if existing:
			pis[pi_key] = existing
			_record(counts, "Purchase Invoice", created=False)
			return

		pi = make_pi_from_pr(source_doc_name) if from_pr else make_pi_from_po(source_doc_name)
		if partial_first_item and len(pi.items) > 1:
			pi.items = [pi.items[0]]
		pi.naming_series = "ACC-PINV-.YYYY.-"
		pi.update_stock = 0
		pi.set_posting_time = 1
		pi.posting_date = posting_date
		pi.bill_no = bill_no
		pi.bill_date = posting_date
		pi.set("payment_schedule", [])
		pi.due_date = due_date
		pi.credit_to = prereqs.payable_account
		pi.remarks = f"{tag} Sample construction payable invoice"
		for row in pi.items:
			if not row.expense_account:
				row.expense_account = prereqs.expense_account
			if not row.cost_center:
				row.cost_center = prereqs.cost_center
		pi.insert(ignore_permissions=True)
		pi.submit()
		pis[pi_key] = pi.name
		_record(counts, "Purchase Invoice", created=True)

	# PI-01 from PR-02 (Unpaid, due in 12 days)
	_create_pi(
		"PI-01",
		"CM-DEMO-BILL-01",
		"CM-DEMO:PI-01",
		prs["PR-02"],
		from_pr=True,
		posting_date=add_days(today, -18),
		due_date=add_days(today, 12),
	)

	# PI-02 from PO-04 when pr_required != Yes (Overdue, due 5 days ago),
	# or partial billing of PR-01 if Buying Settings enforces Purchase Receipt first.
	if not pr_required:
		_create_pi(
			"PI-02",
			"CM-DEMO-BILL-02",
			"CM-DEMO:PI-02",
			pos["PO-04"],
			from_pr=False,
			posting_date=add_days(today, -18),
			due_date=add_days(today, -5),
		)
	else:
		_create_pi(
			"PI-02",
			"CM-DEMO-BILL-02",
			"CM-DEMO:PI-02",
			prs["PR-01"],
			from_pr=True,
			posting_date=add_days(today, -18),
			due_date=add_days(today, -5),
			partial_first_item=True,
		)
	return pis


def _compute_stock_summary(warehouse):
	summary = []
	low_stock = []
	for item_code, (reorder_level, _reorder_qty) in ITEM_REORDER_SPECS.items():
		qty = _get_bin_qty(item_code, warehouse)
		is_low = qty < reorder_level
		row = {
			"item_code": item_code,
			"actual_qty": qty,
			"reorder_level": reorder_level,
			"below_reorder": is_low,
		}
		summary.append(row)
		if is_low:
			low_stock.append(item_code)
	return summary, low_stock


def _ensure_schema_custom_fields():
	"""Install Item/Supplier custom fields before transactional writes when not yet present."""
	if not frappe.db.has_column("Item", "cm_material_type"):
		materials.ensure_custom_fields()
	if not frappe.db.has_column("Supplier", "cm_specialization"):
		vendors.ensure_custom_fields()


def create_sample_data(company=None, warehouse=None):
	"""Populate an idempotent, realistic set of construction sample records.

	Run manually:
	    bench --site <site> execute construction_management.demo_data.create_sample_data
	"""
	prereqs = validate_prerequisites(company=company, warehouse=warehouse)
	counts = _new_counts()
	today = nowdate()

	# Keep any Custom Field schema DDL outside the business-data savepoint so
	# implicit MariaDB DDL commits cannot break savepoint rollback, while Item Group
	# and Supplier Group document writes run inside the savepoint.
	_ensure_schema_custom_fields()

	frappe.db.savepoint(DEMO_SAVEPOINT)
	try:
		_ensure_required_uoms(counts)
		_ensure_materials_and_reorders(counts, prereqs.warehouse, prereqs.warehouse_group)
		suppliers = _ensure_vendors(counts, prereqs.country)
		projects_by_key = _ensure_projects(counts, prereqs.company, today)
		tasks = _ensure_tasks(counts, projects_by_key, today)
		issues = _ensure_issues(counts, projects_by_key, prereqs.company, today)
		dprs = _ensure_dprs(counts, projects_by_key, tasks["tasks"], suppliers, today)

		# Stock Entry #1: opening stock receipt into target Warehouse
		se1 = _ensure_stock_entry(
			counts,
			marker="CM-DEMO:SE-01",
			se_type="Material Receipt",
			company=prereqs.company,
			posting_date=add_days(today, -30),
			items_spec=(
				("CM-CEM-001", 250.0),
				("CM-STL-001", 1200.0),
				("CM-AGG-001", 50.0),
				("CM-AGG-002", 55.0),
				("CM-MAS-001", 6000.0),
				("CM-MAS-002", 1800.0),
				("CM-PLB-001", 200.0),
				("CM-ELE-001", 350.0),
			),
			warehouse=prereqs.warehouse,
		)

		mrs = _ensure_material_requests(counts, prereqs.company, prereqs.warehouse, projects_by_key, today)
		pos = _ensure_purchase_orders(
			counts,
			prereqs.company,
			prereqs.currency,
			prereqs.warehouse,
			mrs,
			projects_by_key,
			suppliers,
			today,
		)
		prs = _ensure_purchase_receipts(counts, prereqs.company, prereqs.warehouse, pos, today)

		# Stock Entry #2: site consumption material issue after opening stock & GRNs exist
		se2 = _ensure_stock_entry(
			counts,
			marker="CM-DEMO:SE-02",
			se_type="Material Issue",
			company=prereqs.company,
			posting_date=add_days(today, -3),
			items_spec=(
				("CM-CEM-001", 80.0),
				("CM-MAS-001", 1200.0),
				("CM-ELE-001", 100.0),
			),
			warehouse=prereqs.warehouse,
		)

		pis = _ensure_purchase_invoices(counts, prereqs, prs, pos, today)
		stock_summary, low_stock_items = _compute_stock_summary(prereqs.warehouse)
	except Exception:
		frappe.db.rollback(save_point=DEMO_SAVEPOINT)
		raise
	else:
		if hasattr(frappe.db, "release_savepoint"):
			frappe.db.release_savepoint(DEMO_SAVEPOINT)

	return {
		"company": prereqs.company,
		"currency": prereqs.currency,
		"warehouse": prereqs.warehouse,
		"counts": counts,
		"stock_summary": stock_summary,
		"low_stock_items": low_stock_items,
		"records": {
			"projects": list(projects_by_key.values()),
			"phases": list(tasks["phases"].values()),
			"tasks": list(tasks["tasks"].values()),
			"issues": issues,
			"dprs": dprs,
			"stock_entries": [se1, se2],
			"material_requests": list(mrs.values()),
			"purchase_orders": list(pos.values()),
			"purchase_receipts": list(prs.values()),
			"purchase_invoices": list(pis.values()),
		},
	}
