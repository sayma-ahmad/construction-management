// Sample tasks and the task table shared by the Project Tasks and Project Details pages.
// Real tasks will be loaded from the Task DocType in a later story.
frappe.provide("construction_management");

construction_management.TASK_STATUSES = ["Open", "Working", "Pending Review", "Overdue", "Completed"];

construction_management.TASK_PRIORITIES = ["Low", "Medium", "High", "Urgent"];

construction_management.SAMPLE_TASKS = [
	{ id: "TASK-0001", subject: "Tower A internal plastering", project: "PRJ-001", phase: "Finishing", assigned_to: "Ramesh Patil", priority: "High", status: "Working", start: "2026-10-01", due: "2026-11-30" },
	{ id: "TASK-0002", subject: "Tower B plumbing first fix", project: "PRJ-001", phase: "MEP Works", assigned_to: "Suresh Kulkarni", priority: "Medium", status: "Completed", start: "2026-07-15", due: "2026-09-30" },
	{ id: "TASK-0003", subject: "Basement waterproofing inspection", project: "PRJ-001", phase: "Structure", assigned_to: "Anil Mehta", priority: "Urgent", status: "Overdue", start: "2026-10-20", due: "2026-11-10" },
	{ id: "TASK-0004", subject: "Lift installation - Tower A", project: "PRJ-001", phase: "MEP Works", assigned_to: "Deepak Joshi", priority: "High", status: "Pending Review", start: "2026-09-01", due: "2026-11-20" },
	{ id: "TASK-0005", subject: "Apartment flooring - floors 1 to 8", project: "PRJ-001", phase: "Finishing", assigned_to: "Ramesh Patil", priority: "Medium", status: "Open", start: "2026-12-01", due: "2027-01-15" },
	{ id: "TASK-0006", subject: "Slab casting - floor 14", project: "PRJ-002", phase: "Structure", assigned_to: "Imran Khan", priority: "High", status: "Working", start: "2026-11-01", due: "2026-11-25" },
	{ id: "TASK-0007", subject: "Curtain wall shop drawings", project: "PRJ-002", phase: "Structure", assigned_to: "Priya Nair", priority: "Medium", status: "Pending Review", start: "2026-10-10", due: "2026-11-18" },
	{ id: "TASK-0008", subject: "HVAC ducting - floors 1 to 6", project: "PRJ-002", phase: "MEP Works", assigned_to: "Deepak Joshi", priority: "Medium", status: "Open", start: "2026-12-05", due: "2027-02-10" },
	{ id: "TASK-0009", subject: "Tower crane safety audit", project: "PRJ-002", phase: "Structure", assigned_to: "Imran Khan", priority: "Urgent", status: "Overdue", start: "2026-10-25", due: "2026-11-05" },
	{ id: "TASK-0010", subject: "Revised building permit submission", project: "PRJ-003", phase: "Foundation", assigned_to: "Rahul Verma", priority: "Urgent", status: "Pending Review", start: "2026-09-15", due: "2026-11-30" },
	{ id: "TASK-0011", subject: "Villa 1 to 10 foundation works", project: "PRJ-003", phase: "Foundation", assigned_to: "Manoj Reddy", priority: "High", status: "Open", start: "2026-08-01", due: "2026-12-15" },
	{ id: "TASK-0012", subject: "Site boundary wall", project: "PRJ-003", phase: "Site Preparation", assigned_to: "Manoj Reddy", priority: "Low", status: "Completed", start: "2025-07-01", due: "2025-09-15" },
	{ id: "TASK-0013", subject: "Food court fit-out", project: "PRJ-004", phase: "Finishing", assigned_to: "Sneha Kapoor", priority: "High", status: "Working", start: "2026-09-01", due: "2026-11-28" },
	{ id: "TASK-0014", subject: "HVAC commissioning", project: "PRJ-004", phase: "MEP Works", assigned_to: "Deepak Joshi", priority: "High", status: "Completed", start: "2026-08-01", due: "2026-10-31" },
	{ id: "TASK-0015", subject: "Facade cleaning and snag list", project: "PRJ-004", phase: "Handover", assigned_to: "Arjun Singh", priority: "Medium", status: "Open", start: "2026-11-20", due: "2026-12-05" },
	{ id: "TASK-0016", subject: "Fire NOC inspection", project: "PRJ-004", phase: "Handover", assigned_to: "Sneha Kapoor", priority: "Urgent", status: "Pending Review", start: "2026-11-01", due: "2026-11-25" },
	{ id: "TASK-0017", subject: "Pier 3 concrete repair", project: "PRJ-005", phase: "Structure", assigned_to: "Karthik Iyer", priority: "High", status: "Working", start: "2026-10-01", due: "2026-12-20" },
	{ id: "TASK-0018", subject: "Bearing replacement - span 2", project: "PRJ-005", phase: "Structure", assigned_to: "Vijay Kumar", priority: "Urgent", status: "Overdue", start: "2026-09-15", due: "2026-11-08" },
	{ id: "TASK-0019", subject: "Traffic diversion plan", project: "PRJ-005", phase: "Site Preparation", assigned_to: "Karthik Iyer", priority: "Medium", status: "Completed", start: "2026-03-01", due: "2026-03-31" },
	{ id: "TASK-0020", subject: "Deck resurfacing material approval", project: "PRJ-005", phase: "Finishing", assigned_to: "Vijay Kumar", priority: "Low", status: "Open", start: "2026-12-01", due: "2027-01-10" },
	{ id: "TASK-0021", subject: "Auditorium acoustic panels", project: "PRJ-006", phase: "Finishing", assigned_to: "Ramesh Patil", priority: "Medium", status: "Completed", start: "2026-03-01", due: "2026-04-30" },
	{ id: "TASK-0022", subject: "Lab equipment handover", project: "PRJ-006", phase: "Handover", assigned_to: "Anil Mehta", priority: "High", status: "Completed", start: "2026-05-15", due: "2026-06-25" },
	{ id: "TASK-0023", subject: "Final occupancy certificate", project: "PRJ-006", phase: "Handover", assigned_to: "Anil Mehta", priority: "High", status: "Completed", start: "2026-06-01", due: "2026-06-30" },
	{ id: "TASK-0024", subject: "Soil investigation report", project: "PRJ-007", phase: "Site Preparation", assigned_to: "Fatima Shaikh", priority: "High", status: "Open", start: "2027-01-15", due: "2027-02-05" },
	{ id: "TASK-0025", subject: "Architectural drawing approval", project: "PRJ-007", phase: "Site Preparation", assigned_to: "Fatima Shaikh", priority: "Medium", status: "Pending Review", start: "2026-11-01", due: "2026-12-15" },
	{ id: "TASK-0026", subject: "Contractor tender evaluation", project: "PRJ-007", phase: "Site Preparation", assigned_to: "Arjun Singh", priority: "Medium", status: "Open", start: "2026-12-01", due: "2027-01-10" },
	{ id: "TASK-0027", subject: "Land survey and site marking", project: "PRJ-008", phase: "Site Preparation", assigned_to: "Manoj Reddy", priority: "Medium", status: "Open", start: "2027-03-01", due: "2027-03-20" },
	{ id: "TASK-0028", subject: "Environmental clearance application", project: "PRJ-008", phase: "Site Preparation", assigned_to: "Rahul Verma", priority: "High", status: "Working", start: "2026-10-15", due: "2027-01-31" },
	{ id: "TASK-0029", subject: "Toll booth electrical works", project: "PRJ-009", phase: "MEP Works", assigned_to: "Sanjay Patel", priority: "Medium", status: "Completed", start: "2025-12-01", due: "2026-02-28" },
	{ id: "TASK-0030", subject: "Control room systems testing", project: "PRJ-009", phase: "Handover", assigned_to: "Vikram Desai", priority: "High", status: "Completed", start: "2026-04-01", due: "2026-05-10" },
	{ id: "TASK-0031", subject: "Coastal zone clearance renewal", project: "PRJ-010", phase: "Site Preparation", assigned_to: "Priya Nair", priority: "Urgent", status: "Overdue", start: "2026-08-01", due: "2026-10-31" },
	{ id: "TASK-0032", subject: "Excavation - main block", project: "PRJ-010", phase: "Foundation", assigned_to: "Imran Khan", priority: "Medium", status: "Open", start: "2026-05-01", due: "2026-12-31" },
	{ id: "TASK-0033", subject: "Site office setup", project: "PRJ-010", phase: "Site Preparation", assigned_to: "Imran Khan", priority: "Low", status: "Completed", start: "2026-02-01", due: "2026-02-28" },
];

construction_management.get_project = function (code) {
	return construction_management.SAMPLE_PROJECTS.find((p) => p.code === code);
};

// Priority is shown as signal bars: one filled bar per level.
construction_management.priority_badge = function (priority) {
	const level = construction_management.TASK_PRIORITIES.indexOf(priority) + 1;
	const bars = construction_management.TASK_PRIORITIES.map(
		(_, index) => `<span class="cm-priority-bar${index < level ? " filled" : ""}"></span>`
	).join("");
	const css_class = priority.toLowerCase();
	return `<span class="cm-priority cm-priority-${css_class}"><span class="cm-priority-bars">${bars}</span>${__(priority)}</span>`;
};

construction_management.show_task_create_placeholder = function () {
	frappe.msgprint({
		title: __("New Task"),
		message: __("Task creation will be available in a later release."),
		indicator: "blue",
	});
};

construction_management.show_task_details = function (task) {
	const esc = frappe.utils.escape_html;
	const project = construction_management.get_project(task.project);
	const route = frappe.get_route();
	const on_project_page = route[0] === "construction-project-details" && route[1] === task.project;

	const fields = [
		[__("Task ID"), esc(task.id)],
		[__("Project"), esc(project ? project.name : task.project)],
		[__("Phase"), esc(__(task.phase))],
		[__("Assigned To"), esc(task.assigned_to)],
		[__("Status"), construction_management.status_pill(task.status)],
		[__("Priority"), construction_management.priority_badge(task.priority)],
		[__("Start Date"), frappe.datetime.str_to_user(task.start)],
		[__("Due Date"), frappe.datetime.str_to_user(task.due)],
	];

	const dialog = new frappe.ui.Dialog({
		title: task.subject,
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "details" }],
	});

	if (!on_project_page) {
		dialog.set_primary_action(__("Open Project"), () => {
			dialog.hide();
			frappe.set_route("construction-project-details", task.project);
		});
	}

	dialog.fields_dict.details.$wrapper.html(`
		<div class="cm-task-detail-grid">
			${fields
				.map(
					([label, value]) => `
				<div>
					<div class="cm-task-detail-label">${label}</div>
					<div class="cm-task-detail-value">${value}</div>
				</div>`
				)
				.join("")}
		</div>
		<div class="cm-task-detail-note">${__("Task editing and updates will be available in a later release.")}</div>
	`);
	dialog.show();
};

// Table of tasks with search and filters. Used on the Project Tasks page (all projects)
// and inside the Tasks tab of a project (show_project: false, pre-filtered tasks).
construction_management.TaskList = class TaskList {
	constructor({ parent, tasks, show_project = true, show_create = false }) {
		this.tasks = tasks;
		this.show_project = show_project;
		this.show_create = show_create;
		this.make_layout(parent);
		this.render();
	}

	make_layout(parent) {
		const options = (values, placeholder) =>
			`<option value="">${placeholder}</option>` +
			values.map((v) => `<option value="${frappe.utils.escape_html(v)}">${__(v)}</option>`).join("");

		const assignees = [...new Set(this.tasks.map((t) => t.assigned_to))].sort();
		const project_codes = [...new Set(this.tasks.map((t) => t.project))].sort();
		const project_options =
			`<option value="">${__("All Projects")}</option>` +
			project_codes
				.map((code) => {
					const project = construction_management.get_project(code);
					return `<option value="${code}">${frappe.utils.escape_html(project ? project.name : code)}</option>`;
				})
				.join("");

		this.$wrapper = $(`
			<div class="cm-tasks-card">
				<div class="cm-tasks-filters">
					<input type="search" class="form-control input-sm cm-tasks-search"
						placeholder="${__("Search task name, ID or assignee")}">
					${this.show_project ? `<select class="form-control input-sm" data-filter="project">${project_options}</select>` : ""}
					<select class="form-control input-sm" data-filter="status">${options(construction_management.TASK_STATUSES, __("All Statuses"))}</select>
					<select class="form-control input-sm" data-filter="priority">${options(construction_management.TASK_PRIORITIES, __("All Priorities"))}</select>
					<select class="form-control input-sm" data-filter="assigned_to">${options(assignees, __("All Assignees"))}</select>
				</div>
				<div class="cm-tasks-toolbar">
					<span class="cm-tasks-count"></span>
					<div class="cm-tasks-actions">
						<button class="btn btn-xs btn-default cm-tasks-clear">${__("Clear Filters")}</button>
						${this.show_create ? `<button class="btn btn-xs btn-primary cm-tasks-create">${__("New Task")}</button>` : ""}
					</div>
				</div>
				<div class="cm-tasks-table-wrapper">
					<table class="cm-tasks-table">
						<thead>
							<tr>
								<th>${__("Task Name")}</th>
								<th>${__("Task ID")}</th>
								${this.show_project ? `<th>${__("Project")}</th>` : ""}
								<th>${__("Assigned To")}</th>
								<th>${__("Priority")}</th>
								<th>${__("Status")}</th>
								<th>${__("Start Date")}</th>
								<th>${__("Due Date")}</th>
								<th></th>
							</tr>
						</thead>
						<tbody></tbody>
					</table>
				</div>
			</div>
		`).appendTo(parent);

		this.$search = this.$wrapper.find(".cm-tasks-search");
		this.$search.on("input", frappe.utils.debounce(() => this.render(), 200));
		this.$wrapper.find("select[data-filter]").on("change", () => this.render());

		this.$wrapper.find(".cm-tasks-clear").on("click", () => {
			this.$search.val("");
			this.$wrapper.find("select[data-filter]").val("");
			this.render();
		});
		this.$wrapper.find(".cm-tasks-create").on("click", construction_management.show_task_create_placeholder);

		this.$wrapper.on("click", ".cm-tasks-project-link", (e) => {
			e.stopPropagation();
			frappe.set_route("construction-project-details", $(e.currentTarget).attr("data-project"));
		});
		this.$wrapper.on("click", "tbody tr[data-task]", (e) => {
			const task = this.tasks.find((t) => t.id === $(e.currentTarget).attr("data-task"));
			construction_management.show_task_details(task);
		});
	}

	get_filter(name) {
		return this.$wrapper.find(`select[data-filter="${name}"]`).val() || "";
	}

	set_project(code) {
		const $project = this.$wrapper.find('select[data-filter="project"]');
		$project.val($project.find(`option[value="${code}"]`).length ? code : "");
		this.render();
	}

	get_filtered() {
		const search = (this.$search.val() || "").trim().toLowerCase();
		const filters = ["project", "status", "priority", "assigned_to"]
			.map((name) => [name, this.get_filter(name)])
			.filter(([, value]) => value);

		return this.tasks.filter((task) => {
			const matches_search =
				!search ||
				[task.subject, task.id, task.assigned_to].some((value) => value.toLowerCase().includes(search));
			return matches_search && filters.every(([name, value]) => task[name] === value);
		});
	}

	render() {
		const tasks = this.get_filtered();
		const columns = this.show_project ? 9 : 8;

		this.$wrapper
			.find(".cm-tasks-count")
			.text(__("Showing {0} of {1} tasks", [tasks.length, this.tasks.length]));

		const rows = tasks.length
			? tasks.map((task) => this.task_row(task)).join("")
			: `<tr><td colspan="${columns}" class="cm-tasks-empty">${__("No tasks match the selected filters.")}</td></tr>`;

		this.$wrapper.find("tbody").html(rows);
	}

	task_row(task) {
		const esc = frappe.utils.escape_html;
		const project = construction_management.get_project(task.project);
		const project_cell = this.show_project
			? `<td><a class="cm-tasks-project-link" data-project="${esc(task.project)}">${esc(project ? project.name : task.project)}</a></td>`
			: "";

		return `
			<tr data-task="${esc(task.id)}" title="${__("Open task details")}">
				<td class="cm-tasks-name">${esc(task.subject)}</td>
				<td class="cm-tasks-muted">${esc(task.id)}</td>
				${project_cell}
				<td class="cm-tasks-nowrap">${esc(task.assigned_to)}</td>
				<td>${construction_management.priority_badge(task.priority)}</td>
				<td>${construction_management.status_pill(task.status)}</td>
				<td class="cm-tasks-nowrap">${frappe.datetime.str_to_user(task.start)}</td>
				<td class="cm-tasks-nowrap">${frappe.datetime.str_to_user(task.due)}</td>
				<td class="cm-tasks-open">${frappe.utils.icon("right", "sm")}</td>
			</tr>
		`;
	}
};
