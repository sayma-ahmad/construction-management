# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, getdate, nowdate, pretty_date


@frappe.whitelist()
def get_dashboard_data(company=None):
	"""Return comprehensive construction dashboard metrics, charts, and activity feeds.
	Aggregates live ERPNext and Construction Management records with strict role & User Permission isolation.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required to view dashboard data"), frappe.PermissionError)

	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_default("company")

	project_summary = _get_project_summary(company)
	procurement_summary = _get_procurement_summary(company)
	inventory_issues = _get_inventory_and_issues_summary(company)
	financial_summary = _get_financial_summary(company)

	# KPI Cards covering all US-17 subtasks with explicit permission tags
	kpis = [
		{
			"label": "Total Projects",
			"value": project_summary["total_projects"],
			"note": _("{0} active, {1} completed").format(
				project_summary["active_projects"], project_summary["completed_projects"]
			),
			"icon": "project",
			"doctype": "Project",
			"route": "List/Project",
			"has_permission": frappe.has_permission("Project", "read"),
		},
		{
			"label": "Purchase Orders",
			"value": procurement_summary["total_purchase_orders"],
			"note": _("{0} active, {1} draft").format(
				procurement_summary["active_purchase_orders"], procurement_summary["draft_purchase_orders"]
			),
			"icon": "buying",
			"doctype": "Purchase Order",
			"route": "List/Purchase Order",
			"has_permission": frappe.has_permission("Purchase Order", "read"),
		},
		{
			"label": "Work Orders",
			"value": procurement_summary["total_work_orders"],
			"note": _("{0} in progress").format(procurement_summary["open_work_orders"]),
			"icon": "tool",
			"doctype": procurement_summary["work_order_doctype"],
			"route": f"List/{procurement_summary['work_order_doctype']}",
			"has_permission": procurement_summary["has_wo_permission"],
		},
		{
			"label": "Material Requests",
			"value": procurement_summary["total_material_requests"],
			"note": _("{0} pending fulfillment").format(procurement_summary["open_material_requests"]),
			"icon": "list-alt",
			"doctype": "Material Request",
			"route": "List/Material Request",
			"has_permission": frappe.has_permission("Material Request", "read"),
		},
		{
			"label": "Goods Received (GRN)",
			"value": procurement_summary["total_grns"],
			"note": _("{0} received at site").format(procurement_summary["submitted_grns"]),
			"icon": "stock",
			"doctype": "Purchase Receipt",
			"route": "List/Purchase Receipt",
			"has_permission": frappe.has_permission("Purchase Receipt", "read"),
		},
		{
			"label": "Site Issues",
			"value": inventory_issues["total_issues"],
			"note": _("{0} open issues").format(inventory_issues["open_issues"]),
			"icon": "solid-warning",
			"doctype": "Issue",
			"route": "List/Issue",
			"has_permission": frappe.has_permission("Issue", "read"),
		},
		{
			"label": "Inventory Items",
			"value": inventory_issues["total_items"],
			"note": _("{0} low stock items").format(inventory_issues["low_stock_items"]),
			"icon": "assets",
			"doctype": "Item",
			"route": "List/Item",
			"has_permission": frappe.has_permission("Item", "read"),
		},
		{
			"label": "Total Payables",
			"value": financial_summary["total_payables"],
			"is_currency": True,
			"currency": financial_summary["currency"],
			"note": _("{0} unpaid invoices (Spend: {1})").format(
				financial_summary["unpaid_invoices_count"],
				frappe.format(financial_summary["total_expenses"], {"fieldtype": "Currency", "currency": financial_summary["currency"]})
			),
			"icon": "expenses",
			"doctype": "Purchase Invoice",
			"route": "List/Purchase Invoice",
			"has_permission": frappe.has_permission("Purchase Invoice", "read"),
		},
	]

	return {
		"kpis": kpis,
		"metrics": {
			"project": project_summary,
			"procurement": procurement_summary,
			"inventory_issues": inventory_issues,
			"financial": financial_summary,
		},
		"completion": _get_completion_chart_data(company),
		"task_status": _get_task_status_chart_data(company),
		"projects": _get_project_progress_table(company),
		"inventory": inventory_issues["chart"],
		"activity": _get_recent_activity_feed(company),
		"expense_flow": financial_summary.get("expense_flow"),
	}


def _get_project_summary(company=None):
	"""Subtask 1: Fetch total, active, and completed project counts with permission awareness."""
	if not frappe.db.exists("DocType", "Project") or not frappe.has_permission("Project", "read"):
		return {"total_projects": 0, "active_projects": 0, "completed_projects": 0, "avg_progress": 0.0}

	filters = {}
	if company:
		filters["company"] = company

	projects = frappe.get_list(
		"Project",
		filters=filters,
		fields=["name", "status", "percent_complete"],
		limit_page_length=0,
	)

	active_projects = [p for p in projects if p.status == "Open"]
	completed_projects = [p for p in projects if p.status == "Completed"]
	total_valid = [p for p in projects if p.status != "Cancelled"]

	avg_progress = 0.0
	if active_projects:
		avg_progress = sum(flt(p.percent_complete) for p in active_projects) / len(active_projects)

	return {
		"total_projects": len(total_valid),
		"active_projects": len(active_projects),
		"completed_projects": len(completed_projects),
		"avg_progress": round(flt(avg_progress), 1),
	}


def _get_procurement_summary(company=None):
	"""Subtasks 2 & 3: Fetch Purchase Orders, Work Orders, GRNs, and Material Requests."""
	base_filters = {}
	if company:
		base_filters["company"] = company

	# 1. Purchase Orders
	total_po = 0
	active_po = 0
	draft_po = 0
	if frappe.db.exists("DocType", "Purchase Order") and frappe.has_permission("Purchase Order", "read"):
		po_list = frappe.get_list(
			"Purchase Order",
			filters=base_filters,
			fields=["name", "status", "docstatus"],
			limit_page_length=0,
		)
		valid_pos = [po for po in po_list if po.docstatus != 2 and po.status != "Cancelled"]
		total_po = len(valid_pos)
		draft_po = len([po for po in valid_pos if po.docstatus == 0])
		active_po = len([
			po for po in valid_pos
			if po.docstatus == 1 and po.status in ("To Receive and Bill", "To Receive", "To Bill")
		])

	# 2. Construction Work Orders
	has_cwo = frappe.db.exists("DocType", "Construction Work Order")
	wo_doctype = "Construction Work Order" if has_cwo else "Work Order"
	has_wo_permission = frappe.has_permission(wo_doctype, "read") if frappe.db.exists("DocType", wo_doctype) else False

	total_wo = 0
	open_wo = 0
	if has_wo_permission:
		wo_filters = {}
		if company and frappe.db.has_column(wo_doctype, "company"):
			wo_filters["company"] = company

		wo_list = frappe.get_list(
			wo_doctype,
			filters=wo_filters,
			fields=["name", "status", "docstatus"],
			limit_page_length=0,
		)
		valid_wos = [w for w in wo_list if w.docstatus != 2 and w.status != "Cancelled"]
		total_wo = len(valid_wos)
		open_wo = len([
			w for w in valid_wos
			if w.status in ("Draft", "Not Started", "In Progress", "In Process", "Open")
		])

	# 3. Goods Received Note (Purchase Receipt)
	total_grn = 0
	submitted_grn = 0
	if frappe.db.exists("DocType", "Purchase Receipt") and frappe.has_permission("Purchase Receipt", "read"):
		pr_list = frappe.get_list(
			"Purchase Receipt",
			filters=base_filters,
			fields=["name", "docstatus", "is_return"],
			limit_page_length=0,
		)
		non_returns = [pr for pr in pr_list if not pr.is_return and pr.docstatus != 2]
		total_grn = len(non_returns)
		submitted_grn = len([pr for pr in non_returns if pr.docstatus == 1])

	# 4. Material Requests (Purchase requisitions)
	total_mr = 0
	open_mr = 0
	if frappe.db.exists("DocType", "Material Request") and frappe.has_permission("Material Request", "read"):
		mr_filters = {"material_request_type": "Purchase", "docstatus": 1, "status": ["not in", ["Cancelled", "Stopped"]]}
		if company:
			mr_filters["company"] = company

		mr_list = frappe.get_list(
			"Material Request",
			filters=mr_filters,
			fields=["name", "docstatus", "status", "per_ordered"],
			limit_page_length=0,
		)
		total_mr = len(mr_list)
		open_mr = len([
			m for m in mr_list
			if flt(m.per_ordered) < 100.0 and m.status not in ("Ordered", "Transferred")
		])

	return {
		"total_purchase_orders": total_po,
		"active_purchase_orders": active_po,
		"draft_purchase_orders": draft_po,
		"total_work_orders": total_wo,
		"open_work_orders": open_wo,
		"work_order_doctype": wo_doctype,
		"has_wo_permission": has_wo_permission,
		"total_grns": total_grn,
		"submitted_grns": submitted_grn,
		"total_material_requests": total_mr,
		"open_material_requests": open_mr,
	}


def _get_inventory_and_issues_summary(company=None):
	"""Subtask 4: Fetch construction issues and aggregated warehouse inventory levels without N+1 queries."""
	# 1. Issues
	total_issues = 0
	open_issues = 0
	if frappe.db.exists("DocType", "Issue") and frappe.has_permission("Issue", "read"):
		issue_filters = {"status": ["!=", "Cancelled"]}
		if company and frappe.db.has_column("Issue", "company"):
			issue_filters["company"] = company

		issue_list = frappe.get_list(
			"Issue",
			filters=issue_filters,
			fields=["name", "status"],
			limit_page_length=0,
		)
		total_issues = len(issue_list)
		open_issues = len([i for i in issue_list if i.status in ("Open", "Replied", "On Hold")])

	# 2. Inventory Items & Stock
	total_items = 0
	low_stock_count = 0
	chart_labels = []
	chart_in_stock = []
	chart_reorder = []

	if (
		frappe.db.exists("DocType", "Item")
		and frappe.has_permission("Item", "read")
		and frappe.db.exists("DocType", "Bin")
		and frappe.has_permission("Bin", "read")
	):
		items = frappe.get_list(
			"Item",
			filters={"is_stock_item": 1, "disabled": 0},
			fields=["name", "item_code", "item_name", "stock_uom"],
			order_by="creation asc",
			limit_page_length=0,
		)
		total_items = len(items)

		if items:
			item_codes = [it.item_code for it in items]

			# Batch query: aggregated stock from Bin per item
			bin_conditions = ["i.is_stock_item = 1", "i.disabled = 0"]
			bin_args = {"item_codes": tuple(item_codes)}
			if company:
				bin_conditions.append("w.company = %(company)s")
				bin_args["company"] = company

			stock_by_item = {}
			bin_rows = frappe.db.sql(
				f"""
				SELECT b.item_code, SUM(b.actual_qty) as actual_qty
				FROM `tabBin` b
				INNER JOIN `tabItem` i ON i.name = b.item_code
				INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
				WHERE {' AND '.join(bin_conditions)} AND b.item_code IN %(item_codes)s
				GROUP BY b.item_code
				""",
				bin_args,
				as_dict=True,
			)
			for b in bin_rows:
				stock_by_item[b.item_code] = flt(b.actual_qty)

			# Batch query: item reorder levels per item
			reorder_by_item = {}
			if frappe.db.exists("DocType", "Item Reorder"):
				reorder_conditions = ["parent IN %(item_codes)s"]
				reorder_args = {"item_codes": tuple(item_codes)}
				if company:
					reorder_conditions.append("(warehouse IN (SELECT name FROM `tabWarehouse` WHERE company = %(company)s) OR warehouse IS NULL)")
					reorder_args["company"] = company

				reorder_rows = frappe.db.sql(
					f"""
					SELECT parent as item_code, SUM(warehouse_reorder_level) as reorder_level
					FROM `tabItem Reorder`
					WHERE {' AND '.join(reorder_conditions)}
					GROUP BY parent
					""",
					reorder_args,
					as_dict=True,
				)
				for r in reorder_rows:
					reorder_by_item[r.item_code] = flt(r.reorder_level)

			# Evaluate low stock across ALL stock items without synthetic thresholds
			for it in items:
				qty = stock_by_item.get(it.item_code, 0.0)
				reorder = reorder_by_item.get(it.item_code, 0.0)
				if reorder > 0 and qty <= reorder:
					low_stock_count += 1

			# Select top items (up to 6) for chart visualization
			chart_items = items[:6]
			for it in chart_items:
				qty = max(0.0, stock_by_item.get(it.item_code, 0.0))
				reorder = reorder_by_item.get(it.item_code, 0.0)
				uom_suffix = f" ({it.stock_uom})" if it.stock_uom else ""
				short_name = (it.item_name or it.item_code)[:18] + uom_suffix
				chart_labels.append(short_name)
				chart_in_stock.append(round(qty, 1))
				chart_reorder.append(round(reorder, 1))

	return {
		"total_issues": total_issues,
		"open_issues": open_issues,
		"total_items": total_items,
		"low_stock_items": low_stock_count,
		"chart": {
			"labels": chart_labels,
			"in_stock": chart_in_stock,
			"reorder_level": chart_reorder,
		},
	}


def _get_financial_summary(company=None):
	"""Subtask 5: Fetch company-currency expense and payable summaries using base amounts."""
	default_currency = frappe.defaults.get_global_default("currency") or "INR"
	if company and frappe.db.exists("Company", company):
		default_currency = frappe.db.get_value("Company", company, "default_currency") or default_currency

	today = getdate(nowdate())
	month_names = []
	month_ranges = []
	for i in range(5, -1, -1):
		m_start = add_months(today.replace(day=1), -i)
		m_end = add_months(m_start, 1)
		month_names.append(m_start.strftime("%b"))
		month_ranges.append((m_start, m_end))

	monthly_expenses = [0.0] * 6
	total_payables = 0.0
	unpaid_count = 0
	total_expenses = 0.0

	if frappe.db.exists("DocType", "Purchase Invoice") and frappe.has_permission("Purchase Invoice", "read"):
		filters = {"docstatus": 1, "is_return": 0}
		if company:
			filters["company"] = company

		invoices = frappe.get_list(
			"Purchase Invoice",
			filters=filters,
			fields=[
				"name",
				"base_grand_total",
				"outstanding_amount",
				"party_account_currency",
				"conversion_rate",
				"posting_date",
			],
			limit_page_length=0,
		)
		for inv in invoices:
			base_out = flt(inv.outstanding_amount)
			if inv.party_account_currency and inv.party_account_currency != default_currency:
				base_out *= flt(inv.conversion_rate) or 1
			if base_out > 0:
				total_payables += base_out
				unpaid_count += 1
			grand_total = flt(inv.base_grand_total)
			total_expenses += grand_total

			p_date = getdate(inv.posting_date) if inv.posting_date else None
			if p_date:
				for idx, (m_start, m_end) in enumerate(month_ranges):
					if m_start <= p_date < m_end:
						monthly_expenses[idx] += grand_total
						break

	return {
		"total_payables": round(total_payables, 2),
		"unpaid_invoices_count": unpaid_count,
		"total_expenses": round(total_expenses, 2),
		"currency": default_currency,
		"expense_flow": {
			"labels": month_names,
			"values": [round(v, 2) for v in monthly_expenses],
			"currency": default_currency,
		},
	}


def _get_completion_chart_data(company=None):
	"""Subtask 6: Connect completion chart with actual submitted Daily Progress Reports without synthetic trends."""
	today = getdate(nowdate())
	month_names = []
	month_starts = []
	for i in range(5, -1, -1):
		m_date = add_months(today, -i)
		month_names.append(m_date.strftime("%b"))
		month_starts.append(m_date.replace(day=1))

	has_dpr = frappe.db.exists("DocType", "Daily Progress Report")
	has_dpr_perm = frappe.has_permission("Daily Progress Report", "read") if has_dpr else False

	if not has_dpr or not has_dpr_perm:
		return {"labels": [], "planned": [], "actual": []}

	six_months_ago = add_months(today, -6)
	dpr_filters = {"docstatus": 1, "report_date": [">=", six_months_ago]}

	dprs = frappe.get_list(
		"Daily Progress Report",
		filters=dpr_filters,
		fields=["report_date", "overall_progress", "project"],
		order_by="report_date asc",
		limit_page_length=0,
	)

	if not dprs:
		return {"labels": [], "planned": [], "actual": []}

	monthly_actuals = []
	for start_date in month_starts:
		end_date = add_months(start_date, 1)
		reports_in_month = [
			flt(d.overall_progress) for d in dprs
			if getdate(d.report_date) >= start_date and getdate(d.report_date) < end_date and d.overall_progress is not None
		]
		avg = round(sum(reports_in_month) / len(reports_in_month), 1) if reports_in_month else 0.0
		monthly_actuals.append(avg)

	if sum(monthly_actuals) <= 0:
		return {"labels": [], "planned": [], "actual": []}

	return {
		"labels": month_names,
		"planned": [],
		"actual": monthly_actuals,
	}


def _get_task_status_chart_data(company=None):
	"""Subtask 6: Real task distribution from Task DocType with mutually exclusive slices."""
	if not frappe.db.exists("DocType", "Task") or not frappe.has_permission("Task", "read"):
		return {
			"labels": ["Completed", "In Progress", "Open", "Overdue"],
			"values": [0, 0, 0, 0],
		}

	today = getdate(nowdate())
	filters = {"status": ["not in", ["Cancelled", "Template"]]}
	if company and frappe.db.has_column("Task", "company"):
		filters["company"] = company

	tasks = frappe.get_list(
		"Task",
		filters=filters,
		fields=["name", "status", "exp_end_date"],
		limit_page_length=0,
	)

	completed = 0
	in_progress = 0
	open_tasks = 0
	overdue = 0

	for t in tasks:
		is_overdue = False
		if t.status == "Overdue":
			is_overdue = True
		elif t.exp_end_date and getdate(t.exp_end_date) < today and t.status != "Completed":
			is_overdue = True

		if is_overdue:
			overdue += 1
		elif t.status == "Completed":
			completed += 1
		elif t.status in ("Working", "In Progress"):
			in_progress += 1
		else:
			open_tasks += 1

	return {
		"labels": ["Completed", "In Progress", "Open", "Overdue"],
		"values": [cint(completed), cint(in_progress), cint(open_tasks), cint(overdue)],
	}


def _get_project_progress_table(company=None):
	"""Subtask 6: Active project records for the progress table with valid sites and dates."""
	if not frappe.db.exists("DocType", "Project") or not frappe.has_permission("Project", "read"):
		return []

	filters = {"status": ["in", ["Open", "On hold"]]}
	if company:
		filters["company"] = company

	fields = ["name", "project_name", "status", "percent_complete", "expected_end_date"]
	if frappe.db.has_column("Project", "cm_site_location"):
		fields.append("cm_site_location")

	projects = frappe.get_list(
		"Project",
		filters=filters,
		fields=fields,
		order_by="modified desc",
		limit_page_length=8,
	)

	today = getdate(nowdate())

	result = []
	for p in projects:
		pct = round(flt(p.percent_complete), 1)
		due_date = str(p.expected_end_date) if p.expected_end_date else ""

		if p.status == "On hold":
			status = "On Hold"
		elif p.expected_end_date and getdate(p.expected_end_date) < today and pct < 100:
			status = "Delayed"
		elif p.expected_end_date and getdate(p.expected_end_date) <= add_days(today, 15) and pct < 50:
			status = "At Risk"
		else:
			status = "On Track"

		result.append(
			{
				"id": p.name,
				"name": p.project_name or p.name,
				"site": p.get("cm_site_location") or "",
				"due": due_date,
				"progress": pct,
				"status": status,
			}
		)

	return result


def _get_recent_activity_feed(company=None):
	"""Subtask 6: Real recent activity aggregated from DPRs, Issues, Goods Received, POs, MRs with doc navigation."""
	feed = []

	# 1. Daily Progress Reports
	if frappe.db.exists("DocType", "Daily Progress Report") and frappe.has_permission("Daily Progress Report", "read"):
		dprs = frappe.get_list(
			"Daily Progress Report",
			filters={"docstatus": 1},
			fields=["name", "project", "project_name", "review_status", "modified"],
			order_by="modified desc",
			limit_page_length=3,
		)
		for d in dprs:
			p_name = d.project_name or d.project or "Site"
			action = "approved" if d.review_status == "Approved" else "submitted"
			feed.append(
				{
					"doctype": "Daily Progress Report",
					"docname": d.name,
					"text": _("Daily progress report {0} for {1}").format(action, p_name),
					"time": pretty_date(d.modified),
					"timestamp": str(d.modified),
				}
			)

	# 2. Issues
	if frappe.db.exists("DocType", "Issue") and frappe.has_permission("Issue", "read"):
		issue_filters = {"status": ["not in", ["Closed", "Cancelled"]]}
		if company and frappe.db.has_column("Issue", "company"):
			issue_filters["company"] = company

		issues = frappe.get_list(
			"Issue",
			filters=issue_filters,
			fields=["name", "subject", "modified"],
			order_by="modified desc",
			limit_page_length=3,
		)
		for iss in issues:
			feed.append(
				{
					"doctype": "Issue",
					"docname": iss.name,
					"text": _("Site issue raised: {0}").format(iss.subject or iss.name),
					"time": pretty_date(iss.modified),
					"timestamp": str(iss.modified),
				}
			)

	# 3. Goods Received (Purchase Receipt)
	if frappe.db.exists("DocType", "Purchase Receipt") and frappe.has_permission("Purchase Receipt", "read"):
		pr_filters = {"docstatus": 1, "is_return": 0}
		if company:
			pr_filters["company"] = company

		grns = frappe.get_list(
			"Purchase Receipt",
			filters=pr_filters,
			fields=["name", "supplier_name", "modified"],
			order_by="modified desc",
			limit_page_length=3,
		)
		for grn in grns:
			feed.append(
				{
					"doctype": "Purchase Receipt",
					"docname": grn.name,
					"text": _("Goods received ({0}) from {1}").format(grn.name, grn.supplier_name or "Vendor"),
					"time": pretty_date(grn.modified),
					"timestamp": str(grn.modified),
				}
			)

	# 4. Purchase Orders
	if frappe.db.exists("DocType", "Purchase Order") and frappe.has_permission("Purchase Order", "read"):
		po_filters = {"docstatus": 1}
		if company:
			po_filters["company"] = company

		pos = frappe.get_list(
			"Purchase Order",
			filters=po_filters,
			fields=["name", "supplier_name", "status", "modified"],
			order_by="modified desc",
			limit_page_length=3,
		)
		for po in pos:
			feed.append(
				{
					"doctype": "Purchase Order",
					"docname": po.name,
					"text": _("Purchase order {0} ({1}) for {2}").format(
						po.name, po.status, po.supplier_name or "Vendor"
					),
					"time": pretty_date(po.modified),
					"timestamp": str(po.modified),
				}
			)

	# 5. Material Requests
	if frappe.db.exists("DocType", "Material Request") and frappe.has_permission("Material Request", "read"):
		mr_filters = {"docstatus": 1, "material_request_type": "Purchase", "status": ["not in", ["Stopped", "Cancelled"]]}
		if company:
			mr_filters["company"] = company

		mrs = frappe.get_list(
			"Material Request",
			filters=mr_filters,
			fields=["name", "status", "modified"],
			order_by="modified desc",
			limit_page_length=2,
		)
		for mr in mrs:
			feed.append(
				{
					"doctype": "Material Request",
					"docname": mr.name,
					"text": _("Material request {0} ({1})").format(mr.name, mr.status),
					"time": pretty_date(mr.modified),
					"timestamp": str(mr.modified),
				}
			)

	feed.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
	return feed[:6]
