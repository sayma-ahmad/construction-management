# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

"""Demo data set with enough records on every page to try filters, paging and workflows.

100 projects with clients, 100 Daily Progress Reports, phases and tasks, site issues, work orders,
extra materials and vendors, material requests, purchase orders, goods receipts, purchase invoices
and stock transfers.

Run manually:
bench --site <site> execute construction_management.seed_data.create_seed_data

Every record carries a "[CM-SEED:...]" marker, so running it again skips what already exists.
"""

import random

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.stock.doctype.material_request.material_request import make_purchase_order
from erpnext.stock.doctype.material_request.material_request import update_status as update_mr_status
from frappe.utils import add_days, date_diff, getdate, nowdate, nowtime

from construction_management import materials
from construction_management.construction_management.doctype.daily_progress_report.daily_progress_report import (
	approve_dpr,
	request_dpr_revision,
)
from construction_management.demo_data import _resolve_company, validate_prerequisites
from construction_management.inventory import create_stock_transfer
from construction_management.inventory import setup as setup_warehouses
from construction_management.vendors import VENDORS_SUPPLIER_GROUP

PROJECT_COUNT = 100
DPR_COUNT = 100

CLIENTS = [
	"Shree Ganesh Developers",
	"Prestige Habitat Builders",
	"Metro Rail Development Corporation",
	"Sunshine Realty Group",
	"Navbharat Infrastructure Ltd",
	"Greenfield Housing Society",
	"Apollo Healthcare Trust",
	"Silverline IT Parks",
	"Deccan Educational Trust",
	"Coastal Logistics Pvt Ltd",
	"Royal Hospitality Group",
	"Urban Retail Ventures",
	"State Public Works Department",
	"Vertex Commercial Estates",
	"Harmony Township Developers",
]

CITIES = [
	"Pune",
	"Mumbai",
	"Bengaluru",
	"Hyderabad",
	"Chennai",
	"Delhi",
	"Ahmedabad",
	"Kolkata",
	"Jaipur",
	"Nagpur",
	"Lucknow",
	"Indore",
	"Kochi",
	"Surat",
	"Chandigarh",
]

NAME_PREFIXES = [
	"Skyline",
	"Lakeview",
	"Emerald",
	"Orchid",
	"Sapphire",
	"Horizon",
	"Palm Grove",
	"Silver Oak",
	"Golden Gate",
	"Riverfront",
	"Hilltop",
	"Lotus",
	"Crescent",
	"Meadow",
	"Harbour",
	"Sunrise",
	"Maple",
	"Cedar",
	"Pearl",
	"Ashoka",
]

PROJECT_TYPES = [
	("Residency", "Residential towers with stilt parking and clubhouse.", (25, 180)),
	("Heights", "High-rise residential tower with podium amenities.", (60, 320)),
	("Business Park", "Grade-A office campus with basement parking.", (80, 450)),
	("Mall", "Retail mall with multiplex and food court.", (90, 380)),
	("Hospital Block", "Multi-speciality hospital wing with OT complex.", (40, 220)),
	("School Campus", "School academic block, labs and sports ground.", (12, 70)),
	("Warehouse", "Pre-engineered warehouse with loading docks.", (8, 60)),
	("Villas", "Gated community of independent villas.", (20, 140)),
	("Flyover", "Four-lane road flyover with service roads.", (50, 260)),
	("Hotel", "Business hotel with banquet and rooftop restaurant.", (45, 210)),
]

# Planning is an Open project whose start date is still in the future.
PROJECT_STATUS_MIX = (
	["In Progress"] * 45 + ["Planning"] * 12 + ["On hold"] * 13 + ["Completed"] * 22 + ["Cancelled"] * 8
)
DPR_REVIEW_MIX = (
	["Approved"] * 45
	+ ["Pending Review"] * 22
	+ ["Draft"] * 13
	+ ["Revision Requested"] * 12
	+ ["Cancelled"] * 8
)

WORK_ITEMS = [
	"Excavation and PCC for footings completed",
	"Raft foundation reinforcement and concreting",
	"Column and beam shuttering for upper floor",
	"Slab concreting with pump and vibrators",
	"Blockwork for internal partition walls",
	"Internal plastering and curing",
	"Electrical conduit and wiring rough-in",
	"Plumbing risers and drainage lines laid",
	"Waterproofing of terrace and toilets",
	"Floor tiling and skirting work",
	"External facade and painting",
	"Road base course and compaction",
]
WEATHER = ["Sunny", "Sunny", "Partly Cloudy", "Cloudy", "Hot", "Rainy", "Windy"]
TRADES = ["Mason", "Helper", "Carpenter", "Bar Bender", "Electrician", "Plumber", "Welder", "Painter"]
MACHINES = ["Concrete Mixer", "Tower Crane", "Excavator", "Concrete Pump", "Vibrator", "Bar Bending Machine"]
MACHINE_STATUS = ["Operational", "Operational", "Operational", "Idle", "Under Maintenance", "Breakdown"]


def create_seed_data(company=None):
	"""Create the demo data for every Construction Management page. Safe to run again."""
	company = _resolve_company(company)
	today = getdate(nowdate())
	counts = {}
	failed = []

	def step(label, fn, *args):
		# A failing section is rolled back and logged; the remaining sections still load.
		savepoint = "cm_seed_step"
		frappe.db.savepoint(savepoint)
		try:
			return fn(*args)
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(title=f"Construction sample data: {label} failed")
			failed.append(label)

	clients = step("Clients", _ensure_clients, counts) or []
	projects = step("Projects", _ensure_projects, counts, company, clients, today) or []
	step("Daily Progress Reports", _ensure_dprs, counts, projects, today)
	tasks_by_project = step("Phases and Tasks", _ensure_phases_and_tasks, counts, projects, today) or {}
	step("Issues", _ensure_issues, counts, projects, company, today)
	step("Vendors", _ensure_vendors, counts)
	# Work orders use every construction vendor on the site, so they load even if new vendors fail.
	step("Work Orders", _ensure_work_orders, counts, projects, tasks_by_project, _construction_contractors(), today)
	warehouses = step("Materials and Stock", _ensure_materials_and_stock, counts, company, today)
	if warehouses:
		step("Purchasing", _ensure_procurement, counts, company, projects, warehouses, today)
		step("Stock Transfers", _ensure_stock_transfers, counts, company, projects, warehouses)
	counts["failed_sections"] = failed
	return counts


def _count(counts, doctype, created):
	row = counts.setdefault(doctype, {"created": 0, "skipped": 0})
	row["created" if created else "skipped"] += 1


def _ensure_clients(counts):
	group = _leaf("Customer Group", "Commercial", "All Customer Groups")
	territory = _leaf("Territory", "India", "All Territories")
	for client in CLIENTS:
		exists = frappe.db.exists("Customer", {"customer_name": client})
		if not exists:
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": client,
					"customer_type": "Company",
					"customer_group": group,
					"territory": territory,
				}
			).insert(ignore_permissions=True)
		_count(counts, "Customer", created=not exists)
	return [frappe.db.get_value("Customer", {"customer_name": c}) for c in CLIENTS]


def _leaf(doctype, preferred, root):
	"""Pick a non-group record (Customer Group or Territory), falling back to the tree root."""
	if frappe.db.exists(doctype, {"name": preferred, "is_group": 0}):
		return preferred
	return frappe.db.get_value(doctype, {"is_group": 0}, "name") or root


def _project_specs(today):
	"""Build the same 100 project definitions on every run (fixed random seed)."""
	rng = random.Random(2026)
	names = [f"{prefix} {ptype[0]}" for prefix in NAME_PREFIXES for ptype in PROJECT_TYPES]
	rng.shuffle(names)
	statuses = PROJECT_STATUS_MIX[:]
	rng.shuffle(statuses)

	specs = []
	for i in range(PROJECT_COUNT):
		name = names[i]
		ptype = next(t for t in PROJECT_TYPES if name.endswith(t[0]))
		status = statuses[i]
		if status == "Completed":
			start = add_days(today, -rng.randint(300, 900))
			end = add_days(start, rng.randint(180, 420))
			if end >= today:
				end = add_days(today, -rng.randint(5, 60))
			progress = 100
		elif status == "Planning":
			start = add_days(today, rng.randint(7, 120))
			end = add_days(start, rng.randint(240, 720))
			progress = 0
		elif status == "On hold":
			start = add_days(today, -rng.randint(90, 500))
			end = add_days(today, rng.randint(-40, 300))
			progress = rng.randint(12, 65)
		elif status == "Cancelled":
			start = add_days(today, -rng.randint(60, 400))
			end = add_days(start, rng.randint(200, 500))
			progress = rng.randint(0, 30)
		else:
			start = add_days(today, -rng.randint(45, 540))
			end = add_days(today, rng.randint(20, 600))
			elapsed = date_diff(today, start) / max(date_diff(end, start), 1)
			progress = max(5, min(95, round(elapsed * 100 + rng.randint(-12, 8))))

		low, high = ptype[2]
		specs.append(
			{
				"marker": f"[CM-SEED:P-{i + 1:03d}]",
				"project_name": name,
				"code": f"PRJ-{101 + i}",
				"city": rng.choice(CITIES),
				"client_index": rng.randrange(len(CLIENTS)),
				"status": "Open" if status in ("In Progress", "Planning") else status,
				"progress": progress,
				"start": start,
				"end": end,
				"cost": rng.randint(low, high) * 1000000,
				"notes": ptype[1],
			}
		)
	return specs


def _ensure_projects(counts, company, clients, today):
	projects = []
	for spec in _project_specs(today):
		existing = frappe.db.get_value("Project", {"notes": ["like", f"%{spec['marker']}%"]}, "name")
		if not existing:
			name = spec["project_name"]
			if frappe.db.exists("Project", {"project_name": name}):
				name = f"{name} {spec['city']}"
			doc = frappe.get_doc(
				{
					"doctype": "Project",
					"naming_series": "PROJ-.####",
					"project_name": name,
					"cm_project_code": spec["code"],
					"cm_site_location": spec["city"],
					"customer": clients[spec["client_index"]],
					"company": company,
					"status": spec["status"],
					"percent_complete_method": "Manual",
					"percent_complete": spec["progress"],
					"estimated_costing": spec["cost"],
					"expected_start_date": spec["start"],
					"expected_end_date": spec["end"],
					"notes": f"{spec['marker']} {spec['notes']}",
				}
			)
			doc.insert(ignore_permissions=True)
			existing = doc.name
			_count(counts, "Project", created=True)
		else:
			_count(counts, "Project", created=False)
		projects.append({**spec, "name": existing})
	return projects


def _ensure_dprs(counts, projects, today):
	rng = random.Random(4242)
	# Follow a fixed group of running projects with about one report per project per month over the
	# last six months, so each project's reported progress (and the dashboard trend) climbs over time.
	months = 6
	per_month = -(-DPR_COUNT // months)
	running = [p for p in projects if p["status"] in ("Open", "On hold") and getdate(p["start"]) < today]
	if not running:
		return
	tracked = [p for p in running if date_diff(today, p["start"]) >= 30 * months] or running
	rng.shuffle(tracked)
	tracked = tracked[:per_month]
	contractors = frappe.get_all(
		"Supplier",
		filters={
			"supplier_group": ["in", [VENDORS_SUPPLIER_GROUP, *frappe.get_all("Supplier Group", {"parent_supplier_group": VENDORS_SUPPLIER_GROUP}, pluck="name")]],
			"disabled": 0,
		},
		pluck="name",
	)
	reviews = DPR_REVIEW_MIX[:]
	rng.shuffle(reviews)

	for i in range(DPR_COUNT):
		marker = f"[CM-SEED:DPR-{i + 1:03d}]"
		project = tracked[i % len(tracked)]
		month = min(i // len(tracked), months - 1)
		report_date = max(
			getdate(project["start"]), add_days(today, -(months - 1 - month) * 30 - rng.randint(0, 20))
		)
		share = date_diff(report_date, project["start"]) / max(date_diff(today, project["start"]), 1)
		progress = max(1, min(100, round(project["progress"] * share + rng.randint(-2, 2))))
		manpower = [
			{
				"trade_or_role": trade,
				"worker_count": rng.randint(3, 25),
				"hours_worked": rng.choice([8, 8, 9, 10]),
				"contractor": rng.choice(contractors) if contractors else None,
			}
			for trade in rng.sample(TRADES, rng.randint(2, 4))
		]
		machinery = [
			{
				"equipment_name": machine,
				"quantity": rng.randint(1, 3),
				"hours_used": rng.randint(3, 9),
				"status": rng.choice(MACHINE_STATUS),
			}
			for machine in rng.sample(MACHINES, rng.randint(1, 3))
		]
		work = rng.sample(WORK_ITEMS, 2)
		review = reviews[i]

		if frappe.db.exists("Daily Progress Report", {"remarks": ["like", f"%{marker}%"]}):
			_count(counts, "Daily Progress Report", created=False)
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Daily Progress Report",
				"naming_series": "DPR-.YYYY.-.#####",
				"project": project["name"],
				"report_date": report_date,
				"weather": rng.choice(WEATHER),
				"shift": rng.choice(["Day", "Day", "Day", "Night", "General"]),
				"overall_progress": progress,
				"work_completed": f"{work[0]}. {work[1]}.",
				"remarks": f"{marker} Site progress for {project['project_name']}",
				"manpower": manpower,
				"machinery": machinery,
			}
		)
		doc.insert(ignore_permissions=True)
		if review != "Draft":
			doc.submit()
		if review == "Approved":
			approve_dpr(doc.name, review_remarks="Progress verified on site.")
		elif review == "Revision Requested":
			request_dpr_revision(doc.name, review_remarks="Please attach updated manpower and quantities.")
		elif review == "Cancelled":
			frappe.get_doc("Daily Progress Report", doc.name).cancel()
		_count(counts, "Daily Progress Report", created=True)


# ---------------------------------------------------------------- phases and tasks

PHASE_PLAN = [
	("Site Preparation", ["Site survey and levelling", "Temporary site office and fencing"]),
	("Foundation Works", ["Excavation and PCC", "Footing reinforcement and concreting"]),
	("Structure", ["Column and beam casting", "Slab shuttering and concreting"]),
	("MEP Works", ["Electrical conduits and wiring", "Plumbing and drainage lines"]),
	("Finishing Works", ["Plastering and tiling", "Painting and final cleaning"]),
]
TASK_PROJECT_COUNT = 40
PRIORITIES = ["Low", "Medium", "Medium", "High", "High", "Urgent"]


def _started(projects, today, statuses=("Open", "On hold", "Completed")):
	return sorted(
		(p for p in projects if p["status"] in statuses and getdate(p["start"]) < today),
		key=lambda p: p["code"],
	)


def _ensure_phases_and_tasks(counts, projects, today):
	rng = random.Random(77)
	tasks_by_project = {}
	for project in _started(projects, today)[:TASK_PROJECT_COUNT]:
		start, end = getdate(project["start"]), getdate(project["end"])
		span = max(date_diff(end, start), len(PHASE_PLAN))
		child_tasks = []
		for idx, (phase_name, task_subjects) in enumerate(PHASE_PLAN):
			p_start = add_days(start, span * idx // len(PHASE_PLAN))
			last = idx == len(PHASE_PLAN) - 1
			p_end = add_days(start, span * (idx + 1) // len(PHASE_PLAN) - (0 if last else 1))
			status, progress = _phase_state(project, p_start, p_end, today)

			marker = f"[CM-SEED:PH-{project['code']}-{idx + 1}]"
			if not frappe.db.exists("Project Phase", {"description": ["like", f"%{marker}%"]}):
				frappe.get_doc(
					{
						"doctype": "Project Phase",
						"phase_name": phase_name,
						"project": project["name"],
						"sequence": idx + 1,
						"status": status,
						"progress": progress,
						"start_date": p_start,
						"end_date": p_end,
						"description": f"{marker} {phase_name} for {project['project_name']}",
					}
				).insert(ignore_permissions=True)
				_count(counts, "Project Phase", created=True)
			else:
				_count(counts, "Project Phase", created=False)

			group = _ensure_task(
				counts,
				f"[CM-SEED:TG-{project['code']}-{idx + 1}]",
				{
					"subject": phase_name,
					"project": project["name"],
					"is_group": 1,
					"status": _task_status(status, progress, p_end, today, rng),
					"exp_start_date": p_start,
					"exp_end_date": p_end,
					"progress": progress,
				},
			)
			for t_idx, subject in enumerate(task_subjects):
				t_end = p_end if t_idx else add_days(p_start, max(date_diff(p_end, p_start) // 2, 0))
				t_progress = progress
				if status == "In Progress":
					t_progress = min(100, max(0, progress + rng.randint(-25, 25)))
				child_tasks.append(
					_ensure_task(
						counts,
						f"[CM-SEED:T-{project['code']}-{idx + 1}-{t_idx + 1}]",
						{
							"subject": subject,
							"project": project["name"],
							"parent_task": group,
							"is_group": 0,
							"status": _task_status(status, t_progress, t_end, today, rng),
							"priority": rng.choice(PRIORITIES),
							"exp_start_date": p_start,
							"exp_end_date": t_end,
							"progress": t_progress,
						},
					)
				)
		tasks_by_project[project["name"]] = child_tasks
	return tasks_by_project


def _phase_state(project, p_start, p_end, today):
	if project["status"] == "Completed" or (p_end < today and project["status"] == "Open"):
		return "Completed", 100
	if p_start > today:
		return "Not Started", 0
	share = date_diff(today, p_start) / max(date_diff(p_end, p_start), 1)
	progress = max(5, min(95, round(share * 100)))
	if project["status"] == "On hold":
		return "On Hold", progress
	return "In Progress", progress


def _task_status(phase_status, progress, exp_end, today, rng):
	if phase_status == "Completed" or progress >= 100:
		return "Completed"
	if phase_status == "Not Started":
		return "Open"
	if exp_end < today:
		return "Overdue"
	return rng.choice(["Working", "Working", "Pending Review", "Open"])


def _ensure_task(counts, marker, values):
	existing = frappe.db.get_value("Task", {"description": ["like", f"%{marker}%"]}, "name")
	if existing:
		_count(counts, "Task", created=False)
		return existing
	doc = frappe.get_doc({"doctype": "Task", "description": f"{marker} {values['subject']}", **values})
	if doc.status == "Completed":
		doc.completed_on = min(getdate(doc.exp_end_date), getdate(nowdate()))
	doc.insert(ignore_permissions=True)
	_count(counts, "Task", created=True)
	return doc.name


# ---------------------------------------------------------------- site issues

ISSUE_COUNT = 60
ISSUE_SUBJECTS = {
	"Safety": ["Workers without harness on scaffolding", "Unbarricaded excavation edge", "Fire extinguishers expired"],
	"Quality": ["Honeycombing in column concrete", "Plaster cracks on east wall", "Tile level mismatch in lobby"],
	"Material": ["Cement delivery short by 40 bags", "Damaged PVC pipes received", "Steel grade certificate missing"],
	"Equipment": ["Tower crane hoist brake fault", "Concrete mixer drum not rotating", "Excavator hydraulic leak"],
	"Design": ["Beam clash with duct routing", "Staircase headroom below standard", "Revised column layout pending"],
	"Delay": ["Monsoon stopped slab casting", "Labour shortage after festival", "Client approval pending for finishes"],
	"Other": ["Neighbour complaint about dust", "Water supply interruption at site", "Site access road blocked"],
}
ISSUE_STATUS_MIX = ["Open"] * 20 + ["Replied"] * 10 + ["On Hold"] * 8 + ["Resolved"] * 12 + ["Closed"] * 10


def _ensure_issues(counts, projects, company, today):
	rng = random.Random(55)
	candidates = _started(projects, today)
	types = [t for t in ISSUE_SUBJECTS if frappe.db.exists("Issue Type", t)]
	priorities = frappe.get_all("Issue Priority", pluck="name") or [None]
	statuses = ISSUE_STATUS_MIX[:]
	rng.shuffle(statuses)
	for i in range(ISSUE_COUNT):
		marker = f"[CM-SEED:ISS-{i + 1:03d}]"
		project = rng.choice(candidates)
		issue_type = rng.choice(types) if types else None
		subject = rng.choice(ISSUE_SUBJECTS[issue_type or "Other"])
		opened = add_days(today, -rng.randint(0, 120))
		priority = rng.choice(priorities)
		status = statuses[i]
		if frappe.db.exists("Issue", {"description": ["like", f"%{marker}%"]}):
			_count(counts, "Issue", created=False)
			continue
		values = {
			"doctype": "Issue",
			"subject": f"{subject} - {project['project_name']}",
			"project": project["name"],
			"company": company,
			"issue_type": issue_type,
			"priority": priority,
			"status": status,
			"opening_date": opened,
			"description": f"{marker} Reported by the site engineer at the {project['city']} site.",
		}
		if status in ("Resolved", "Closed"):
			values["resolution_details"] = "Corrective action completed and verified on site."
		frappe.get_doc(values).insert(ignore_permissions=True)
		_count(counts, "Issue", created=True)


# ---------------------------------------------------------------- vendors

EXTRA_VENDORS = [
	("Sahyadri Civil Works", "Subcontractor", "Civil Works", "Suresh", "Patil", "Pune", "Maharashtra", "411001"),
	("Volt Line Electrical Contractors", "Subcontractor", "Electrical", "Imran", "Shaikh", "Mumbai", "Maharashtra", "400001"),
	("AquaFlow Plumbing Contractors", "Subcontractor", "Plumbing", "Joseph", "Mathew", "Kochi", "Kerala", "682001"),
	("Brickwell Masonry Contractors", "Subcontractor", "Masonry", "Ramesh", "Yadav", "Lucknow", "Uttar Pradesh", "226001"),
	("TerraMove Earthmovers", "Equipment Supplier", "Construction Equipment", "Harpreet", "Singh", "Chandigarh", "Chandigarh", "160017"),
	("LiftPro Crane Services", "Equipment Supplier", "Construction Equipment", "Kiran", "Rao", "Hyderabad", "Telangana", "500001"),
	("SteelCore Fabricators", "Material Supplier", "Steel", "Mahesh", "Gupta", "Ahmedabad", "Gujarat", "380001"),
	("BuildSafe Site Services", "Service Provider", "Civil Works", "Neha", "Kulkarni", "Bengaluru", "Karnataka", "560001"),
]
ON_HOLD_VENDOR = "BuildSafe Site Services"
DISABLED_VENDOR = "SteelCore Fabricators"


def _ensure_vendors(counts):
	country = frappe.db.get_default("country") or "India"
	for i, (name, group, spec, first, last, city, state, pincode) in enumerate(EXTRA_VENDORS):
		exists = frappe.db.exists("Supplier", {"supplier_name": name})
		if not exists:
			slug = name.split()[0].lower()
			doc = frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": name,
					"supplier_type": "Company",
					"supplier_group": group,
					"cm_specialization": spec,
					"country": country,
					"first_name": first,
					"last_name": last,
					"mobile_no": f"+91 98{i + 10:03d}{40000 + i * 137:05d}",
					"email_id": f"contact@{slug}.example.com",
					"address_line1": f"{12 + i} Industrial Estate Road",
					"city": city,
					"state": state,
					"pincode": pincode,
				}
			)
			# One vendor on hold and one disabled, so the Vendors status filter has data.
			if name == ON_HOLD_VENDOR:
				doc.on_hold, doc.hold_type = 1, "All"
			if name == DISABLED_VENDOR:
				doc.disabled = 1
			doc.insert(ignore_permissions=True)
		_count(counts, "Supplier", created=not exists)



def _construction_contractors():
	"""Enabled construction vendors that can be assigned to Work Orders."""
	groups = frappe.get_all("Supplier Group", {"parent_supplier_group": VENDORS_SUPPLIER_GROUP}, pluck="name")
	return frappe.get_all(
		"Supplier",
		filters={"supplier_group": ["in", groups], "disabled": 0, "on_hold": 0},
		pluck="name",
		order_by="name asc",
	)


# ---------------------------------------------------------------- work orders

WORK_ORDER_COUNT = 50
WORK_ORDER_TITLES = [
	"Blockwork for floor {0}",
	"Shuttering and slab casting level {0}",
	"Electrical rough-in tower {0}",
	"Plumbing risers block {0}",
	"External plaster wing {0}",
	"Waterproofing terrace block {0}",
	"Flooring and tiling level {0}",
	"Painting works tower {0}",
]
WORK_ORDER_STATUS_MIX = (
	["Open"] * 12 + ["In Progress"] * 18 + ["On Hold"] * 6 + ["Completed"] * 10 + ["Cancelled"] * 4
)


def _ensure_work_orders(counts, projects, tasks_by_project, contractors, today):
	if not contractors:
		return
	rng = random.Random(99)
	candidates = _started(projects, today, ("Open", "On hold"))
	statuses = WORK_ORDER_STATUS_MIX[:]
	rng.shuffle(statuses)
	for i in range(WORK_ORDER_COUNT):
		marker = f"[CM-SEED:WO-{i + 1:03d}]"
		project = rng.choice(candidates)
		status = statuses[i]
		title = rng.choice(WORK_ORDER_TITLES).format(rng.randint(1, 12))
		contractor = rng.choice(contractors)
		planned_start = add_days(today, rng.randint(-120, 20))
		planned_end = add_days(planned_start, rng.randint(20, 90))
		task_pool = tasks_by_project.get(project["name"]) or []
		task = rng.choice(task_pool) if task_pool and rng.random() < 0.5 else None
		cost = rng.randint(2, 60) * 50000
		priority = rng.choice(["Low", "Medium", "Medium", "High", "Urgent"])
		work_days = rng.randint(10, 60)
		if frappe.db.exists("Construction Work Order", {"remarks": ["like", f"%{marker}%"]}):
			_count(counts, "Construction Work Order", created=False)
			continue
		values = {
			"doctype": "Construction Work Order",
			"title": title,
			"project": project["name"],
			"contractor": contractor,
			"status": status,
			"priority": priority,
			"task": task,
			"estimated_cost": cost,
			"planned_start_date": planned_start,
			"planned_end_date": planned_end,
			"description": f"Scope: {title.lower()} as per approved drawings for {project['project_name']}.",
			"remarks": f"{marker} Seed work order",
		}
		if status in ("In Progress", "On Hold", "Completed"):
			values["actual_start_date"] = min(planned_start, today)
		if status == "Completed":
			values["actual_completion_date"] = min(add_days(values["actual_start_date"], work_days), today)
		frappe.get_doc(values).insert(ignore_permissions=True)
		_count(counts, "Construction Work Order", created=True)


# ---------------------------------------------------------------- materials and opening stock

# item_code, name, category, uom, type, grade, specification, rate, (reorder level, reorder qty), opening qty, HSN
EXTRA_MATERIALS = [
	("CM-CEM-002", "PPC Cement", "Cement & Concrete", "Bag", "Civil", "PPC", "IS 1489, 50 kg bag", 360, (200, 400), 650, ("25232920", "Portland pozzolana cement")),
	("CM-CEM-003", "Ready Mix Concrete M25", "Cement & Concrete", "Cubic Meter", "Civil", "M25", "Pumpable, 20 mm aggregate", 5200, (20, 40), 12, ("38245010", "Ready mix concrete")),
	("CM-STL-002", "TMT Reinforcement Bar 16 mm", "Steel", "Kg", "Structural", "Fe 500D", "IS 1786", 66, (1500, 3000), 4200, ("72142090", "Bars and rods of iron or non-alloy steel")),
	("CM-STL-003", "Binding Wire 18 SWG", "Steel", "Kg", "Structural", "18 SWG", "Annealed GI binding wire", 85, (100, 300), 60, ("72171010", "Wire of iron or non-alloy steel")),
	("CM-STL-004", "MS Angle 50x50x5", "Steel", "Kg", "Structural", "IS 2062", "Mild steel angle section", 72, (500, 1000), 1800, ("72162100", "Angles of iron or non-alloy steel")),
	("CM-AGG-003", "M-Sand", "Aggregates", "Cubic Meter", "Civil", "Zone II", "Manufactured sand for plaster", 1400, (40, 80), 95, ("25059000", "Natural sands")),
	("CM-AGG-004", "Coarse Aggregate 10 mm", "Aggregates", "Cubic Meter", "Civil", "10 mm", "Crushed granite", 1300, (30, 60), 0, ("25171010", "Pebbles, gravel and broken stone")),
	("CM-MAS-003", "AAC Block 600x200x150", "Masonry", "Nos", "Civil", "600x200x150", "Autoclaved aerated concrete block", 58, (1500, 3000), 5200, ("68101190", "Building blocks of cement or concrete")),
	("CM-MAS-004", "Fly Ash Brick", "Masonry", "Nos", "Civil", "Class 10", "230x110x75 mm", 6, (4000, 8000), 2600, ("68101190", "Building blocks of cement or concrete")),
	("CM-PLB-002", "CPVC Pipe 25 mm", "Plumbing", "Meter", "MEP", "SDR 11", "Hot and cold water line", 95, (200, 400), 640, ("39172390", "Tubes, pipes and hoses of PVC")),
	("CM-PLB-003", "GI Pipe 50 mm", "Plumbing", "Meter", "MEP", "Medium class", "IS 1239 galvanised", 420, (100, 200), 75, ("73063090", "Other tubes and pipes of iron or steel")),
	("CM-PLB-004", "Ball Valve 25 mm", "Plumbing", "Nos", "MEP", "Brass", "Full bore, PN 16", 380, (40, 100), 120, ("84818030", "Valves of brass")),
	("CM-ELE-002", "Copper Cable 4 sq mm", "Electrical", "Meter", "MEP", "FR 1.1 kV", "IS 694, single core", 62, (600, 1200), 1500, ("85444999", "Other electric conductors")),
	("CM-ELE-003", "PVC Conduit 25 mm", "Electrical", "Meter", "MEP", "Medium gauge", "ISI marked rigid conduit", 28, (500, 1000), 380, ("39172390", "Tubes, pipes and hoses of PVC")),
	("CM-ELE-004", "MCB Distribution Board 8 Way", "Electrical", "Nos", "MEP", "Double door", "TPN, IP43", 3200, (10, 25), 34, ("85372000", "Boards and panels for electric control")),
	("CM-ELE-005", "LED Flood Light 100 W", "Electrical", "Nos", "MEP", "IP65", "Site lighting fixture", 1450, (10, 20), 0, ("94054900", "Other electric lamps and lighting fittings")),
	("CM-FIN-001", "Wall Putty", "Cement & Concrete", "Bag", "Finishing", "White cement based", "40 kg bag", 750, (60, 120), 140, ("32149090", "Other non-refractory surfacing preparations")),
]
DISABLED_MATERIAL = "CM-AGG-004"
SEED_RECEIPT_MARKER = "[CM-SEED:OPENING-STOCK]"


def _warehouse(company, warehouse_name):
	return frappe.db.get_value("Warehouse", {"warehouse_name": warehouse_name, "company": company}, "name")


def _ensure_uom(uom):
	if not frappe.db.exists("UOM", uom):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": uom == "Nos"}).insert(
			ignore_permissions=True
		)


def _ensure_materials_and_stock(counts, company, today):
	setup_warehouses(company)
	warehouses = {
		"central": _warehouse(company, "Central Store"),
		"site": _warehouse(company, "Site Store"),
		"transit": _warehouse(company, "Transit Store"),
	}
	use_hsn = frappe.get_meta("Item").has_field("gst_hsn_code")
	materials.create_material_categories()

	receipt_rows = []
	for code, name, group, uom, mtype, grade, spec, rate, reorder, qty, hsn in EXTRA_MATERIALS:
		_ensure_uom(uom)
		exists = frappe.db.exists("Item", code)
		if not exists:
			item = {
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": group,
				"stock_uom": uom,
				"is_stock_item": 1,
				"valuation_rate": rate,
				"cm_material_type": mtype,
				"cm_material_grade": grade,
				"cm_specifications": spec,
				"disabled": 1 if code == DISABLED_MATERIAL else 0,
				"reorder_levels": [
					{
						"warehouse": warehouses["central"],
						"warehouse_reorder_level": reorder[0],
						"warehouse_reorder_qty": reorder[1],
						"material_request_type": "Purchase",
					}
				],
			}
			if use_hsn:
				item["gst_hsn_code"] = materials.ensure_hsn_code(*hsn)
			frappe.get_doc(item).insert(ignore_permissions=True)
		_count(counts, "Item", created=not exists)
		if qty and code != DISABLED_MATERIAL:
			receipt_rows.append(
				{
					"item_code": code,
					"qty": qty,
					"uom": uom,
					"stock_uom": uom,
					"conversion_factor": 1,
					"basic_rate": rate,
					"t_warehouse": warehouses["central"],
				}
			)

	exists = frappe.db.exists(
		"Stock Entry", {"remarks": ["like", f"%{SEED_RECEIPT_MARKER}%"], "company": company, "docstatus": 1}
	)
	if not exists and receipt_rows:
		doc = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": company,
				"remarks": f"{SEED_RECEIPT_MARKER} Opening stock for seed materials",
				"items": receipt_rows,
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
	_count(counts, "Stock Entry", created=not exists)
	return warehouses


def _material_rates():
	from construction_management.demo_data import ITEM_RATES

	rates = dict(ITEM_RATES)
	rates.update({m[0]: m[7] for m in EXTRA_MATERIALS if m[0] != DISABLED_MATERIAL})
	return rates


# ---------------------------------------------------------------- purchasing: MR, PO, GRN, invoices

# Outcome of each of the 40 material requests, in order.
MR_PLAN = (
	["Draft"] * 6
	+ ["Pending"] * 10
	+ ["Partially Ordered"] * 6
	+ ["Ordered"] * 8
	+ ["Received"] * 6
	+ ["Stopped"] * 2
	+ ["Cancelled"] * 2
)
SITE_AREAS = ["Tower A", "Tower B", "Block C", "Podium", "Basement", "Clubhouse", "Wing East", "Wing West"]
SERVICE_ITEMS = [
	("CM-SRV-001", "Tower Crane Hire", 185000),
	("CM-SRV-002", "Labour Contract Services", 240000),
	("CM-SRV-003", "Site Security Services", 65000),
	("CM-SRV-004", "Material Testing Services", 28000),
]
SERVICE_GROUP = "Construction Services"


def _ensure_procurement(counts, company, projects, warehouses, today):
	prereqs = validate_prerequisites(company, warehouses["central"])
	rng = random.Random(31)
	rates = _material_rates()
	item_codes = sorted(rates)
	running = _started(projects, today, ("Open", "On hold"))
	suppliers = frappe.get_all(
		"Supplier",
		filters={"supplier_group": "Material Supplier", "disabled": 0, "on_hold": 0},
		pluck="name",
		order_by="name asc",
	)
	price_list = frappe.db.get_value("Price List", {"buying": 1, "currency": prereqs.currency, "enabled": 1}, "name")

	receipts = []
	for i, outcome in enumerate(MR_PLAN):
		project = rng.choice(running)
		lines = [(code, rng.randint(2, 20) * _lot(code)) for code in rng.sample(item_codes, rng.randint(1, 3))]
		tx_date = add_days(today, -rng.randint(10, 90))
		need_by = add_days(tx_date, rng.randint(7, 21))
		supplier = rng.choice(suppliers)
		priority = rng.choice(["Low", "Medium", "Medium", "High", "Urgent"])
		area = rng.choice(SITE_AREAS)
		received_on = min(add_days(tx_date, rng.randint(5, 15)), today)

		item_names = ", ".join(frappe.db.get_value("Item", code, "item_name") for code, _qty in lines)
		title = f"[CM-SEED-MR-{i + 1:03d}] {item_names} - {project['project_name']}"
		if frappe.db.exists("Material Request", {"title": title, "company": company}):
			_count(counts, "Material Request", created=False)
			continue

		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"title": title,
				"material_request_type": "Purchase",
				"company": company,
				"cm_project": project["name"],
				"custom_site_location": area,
				"custom_priority": priority,
				"transaction_date": tx_date,
				"schedule_date": need_by,
				"items": [
					{
						"item_code": code,
						"qty": qty,
						"schedule_date": need_by,
						"warehouse": warehouses["central"],
						"project": project["name"],
					}
					for code, qty in lines
				],
			}
		)
		mr.insert(ignore_permissions=True)
		_count(counts, "Material Request", created=True)
		if outcome == "Draft":
			continue
		mr.submit()
		if outcome == "Stopped":
			update_mr_status(mr.name, "Stopped")
			continue
		if outcome == "Cancelled":
			mr.cancel()
			continue
		if outcome == "Pending":
			continue

		po = _po_from_mr(mr.name, supplier, project, tx_date, need_by, warehouses["central"], rates, prereqs, price_list)
		po.title = f"[CM-SEED-PO-{i + 1:03d}] {supplier} - {project['project_name']}"
		if outcome == "Partially Ordered":
			for row in po.items:
				row.qty = max(1, round(row.qty / 2))
		po.insert(ignore_permissions=True)
		po.submit()
		_count(counts, "Purchase Order", created=True)
		if outcome == "Received":
			receipts.append((po.name, received_on, f"CM-SEED-DN-{i + 1:03d}", True))
		elif outcome == "Ordered":
			# Part of the ordered quantity has already arrived at site.
			receipts.append((po.name, received_on, f"CM-SEED-DN-{i + 1:03d}", False))

	_direct_purchase_orders(counts, company, running, suppliers, warehouses, rates, prereqs, price_list, today, rng)
	_receive(counts, receipts, warehouses)
	_bill_receipts(counts, company, prereqs)
	_service_invoices(counts, company, prereqs, suppliers, running, today, rng)


def _lot(item_code):
	uom = frappe.db.get_value("Item", item_code, "stock_uom")
	return {"Nos": 100, "Kg": 50, "Meter": 20, "Bag": 10}.get(uom, 1)


def _po_from_mr(mr_name, supplier, project, tx_date, need_by, warehouse, rates, prereqs, price_list):
	target = frappe.new_doc("Purchase Order")
	target.supplier = supplier
	target.company = prereqs.company
	po = make_purchase_order(mr_name, target_doc=target)
	po.supplier = supplier
	po.company = prereqs.company
	po.currency = prereqs.currency
	po.conversion_rate = 1
	if price_list:
		po.buying_price_list = price_list
	po.price_list_currency = prereqs.currency
	po.plc_conversion_rate = 1
	po.transaction_date = tx_date
	po.schedule_date = need_by
	po.set_warehouse = warehouse
	po.project = project["name"]
	if po.meta.has_field("cm_material_request"):
		po.cm_material_request = mr_name
	for row in po.items:
		row.rate = rates.get(row.item_code, 100)
		row.schedule_date = need_by
		row.warehouse = warehouse
		row.project = project["name"]
	po.run_method("set_missing_values")
	return po


def _direct_purchase_orders(counts, company, running, suppliers, warehouses, rates, prereqs, price_list, today, rng):
	codes = sorted(rates)
	for i in range(10):
		title_prefix = f"[CM-SEED-PO-D{i + 1:02d}]"
		project = rng.choice(running)
		supplier = rng.choice(suppliers)
		lines = [(code, rng.randint(2, 15) * _lot(code)) for code in rng.sample(codes, rng.randint(1, 3))]
		tx_date = add_days(today, -rng.randint(1, 45))
		need_by = add_days(tx_date, rng.randint(7, 20))
		area = rng.choice(SITE_AREAS)
		contact = rng.choice(["Site Engineer", "Store Keeper", "Project Manager"])
		if frappe.db.exists("Purchase Order", {"title": ["like", f"{title_prefix}%"], "company": company}):
			_count(counts, "Purchase Order", created=False)
			continue
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"title": f"{title_prefix} {supplier} - {project['project_name']}",
				"supplier": supplier,
				"company": company,
				"currency": prereqs.currency,
				"conversion_rate": 1,
				"buying_price_list": price_list,
				"price_list_currency": prereqs.currency,
				"plc_conversion_rate": 1,
				"transaction_date": tx_date,
				"schedule_date": need_by,
				"set_warehouse": warehouses["central"],
				"project": project["name"],
				"cm_delivery_site": f"{project['city']} site, {area}",
				"cm_delivery_contact": contact,
				"items": [
					{
						"item_code": code,
						"qty": qty,
						"rate": rates.get(code, 100),
						"schedule_date": need_by,
						"warehouse": warehouses["central"],
						"project": project["name"],
					}
					for code, qty in lines
				],
			}
		)
		po.run_method("set_missing_values")
		po.insert(ignore_permissions=True)
		# The first four stay as drafts so the Draft status has data.
		if i >= 4:
			po.submit()
		_count(counts, "Purchase Order", created=True)


def _receive(counts, receipts, warehouses):
	for idx, (po_name, posting_date, delivery_note, full) in enumerate(receipts):
		if frappe.db.exists("Purchase Receipt", {"supplier_delivery_note": delivery_note, "docstatus": ["<", 2]}):
			_count(counts, "Purchase Receipt", created=False)
			continue
		pr = make_purchase_receipt(po_name)
		pr.set_posting_time = 1
		pr.posting_date = posting_date
		pr.posting_time = nowtime()
		pr.supplier_delivery_note = delivery_note
		pr.remarks = f"[CM-SEED:GRN] Goods received against {po_name}"
		for row in pr.items:
			row.warehouse = warehouses["central"]
			if not full:
				row.qty = row.received_qty = max(1, round(row.qty * 0.4))
		pr.insert(ignore_permissions=True)
		# Some partial receipts stay as drafts waiting for the store keeper to submit.
		if full or idx % 3:
			pr.submit()
		_count(counts, "Purchase Receipt", created=True)


def _bill_receipts(counts, company, prereqs):
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice as make_pi_from_pr

	receipts = frappe.get_all(
		"Purchase Receipt",
		filters={"remarks": ["like", "%[CM-SEED:GRN]%"], "docstatus": 1, "company": company},
		fields=["name", "posting_date", "supplier_delivery_note"],
		order_by="supplier_delivery_note asc",
	)
	for pr in receipts[:5]:
		bill_no = f"CM-SEED-BILL-{pr.supplier_delivery_note[-3:]}"
		if frappe.db.exists("Purchase Invoice", {"bill_no": bill_no, "company": company, "docstatus": ["<", 2]}):
			_count(counts, "Purchase Invoice", created=False)
			continue
		pi = make_pi_from_pr(pr.name)
		_prepare_invoice(pi, prereqs, bill_no, add_days(pr.posting_date, 2), add_days(pr.posting_date, 32))
		pi.insert(ignore_permissions=True)
		pi.submit()
		_count(counts, "Purchase Invoice", created=True)


def _service_invoices(counts, company, prereqs, suppliers, running, today, rng):
	if not frappe.db.exists("Item Group", SERVICE_GROUP):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": SERVICE_GROUP, "parent_item_group": "All Item Groups"}
		).insert(ignore_permissions=True)
	use_hsn = frappe.get_meta("Item").has_field("gst_hsn_code")
	for code, name, _rate in SERVICE_ITEMS:
		if not frappe.db.exists("Item", code):
			item = {
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": SERVICE_GROUP,
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
			if use_hsn:
				item["gst_hsn_code"] = materials.ensure_hsn_code("995411", "Construction services of buildings")
			frappe.get_doc(item).insert(ignore_permissions=True)

	# Two service bills a month for six months, so Expense Flow and Total Payables have history.
	for i in range(12):
		bill_no = f"CM-SEED-SRV-{i + 1:02d}"
		code, name, rate = SERVICE_ITEMS[i % len(SERVICE_ITEMS)]
		project = rng.choice(running)
		supplier = rng.choice(suppliers)
		posting = add_days(today, -(i // 2) * 30 - rng.randint(0, 20))
		amount = round(rate * rng.uniform(0.6, 1.4), -2)
		if frappe.db.exists("Purchase Invoice", {"bill_no": bill_no, "company": company, "docstatus": ["<", 2]}):
			_count(counts, "Purchase Invoice", created=False)
			continue
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"supplier": supplier,
				"company": company,
				"currency": prereqs.currency,
				"conversion_rate": 1,
				"project": project["name"],
				"items": [{"item_code": code, "item_name": name, "qty": 1, "rate": amount, "project": project["name"]}],
			}
		)
		_prepare_invoice(pi, prereqs, bill_no, posting, add_days(posting, 30))
		pi.run_method("set_missing_values")
		pi.insert(ignore_permissions=True)
		pi.submit()
		_count(counts, "Purchase Invoice", created=True)


def _prepare_invoice(pi, prereqs, bill_no, posting_date, due_date):
	pi.update_stock = 0
	pi.set_posting_time = 1
	pi.posting_date = posting_date
	pi.bill_no = bill_no
	pi.bill_date = posting_date
	pi.set("payment_schedule", [])
	pi.due_date = due_date
	pi.credit_to = prereqs.payable_account
	pi.remarks = f"[CM-SEED:{bill_no}] Construction purchase invoice"
	for row in pi.items:
		row.expense_account = row.expense_account or prereqs.expense_account
		row.cost_center = row.cost_center or prereqs.cost_center


# ---------------------------------------------------------------- stock transfers

TRANSFER_COUNT = 15
DRAFT_TRANSFERS = (3, 9, 14)


def _ensure_stock_transfers(counts, company, projects, warehouses):
	rng = random.Random(13)
	running = _started(projects, getdate(nowdate()), ("Open", "On hold"))
	codes = sorted(_material_rates())
	for i in range(TRANSFER_COUNT):
		marker = f"[CM-SEED:ST-{i + 1:03d}]"
		project = rng.choice(running)
		target = warehouses["site"] if i % 4 else warehouses["transit"]
		code = rng.choice(codes)
		share = rng.uniform(0.03, 0.1)
		if frappe.db.exists("Stock Entry", {"remarks": ["like", f"%{marker}%"], "company": company}):
			_count(counts, "Stock Entry", created=False)
			continue
		available = frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouses["central"]}, "actual_qty")
		qty = int((available or 0) * share)
		if qty < 1:
			continue
		create_stock_transfer(
			warehouses["central"],
			target,
			[{"item_code": code, "qty": qty}],
			project=project["name"],
			company=company,
			remarks=f"{marker} Material moved to {project['project_name']} site",
			submit=0 if i in DRAFT_TRANSFERS else 1,
		)
		_count(counts, "Stock Entry", created=True)
