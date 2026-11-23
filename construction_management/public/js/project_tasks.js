// Task table, task dialogs and helpers shared by the Project Tasks and Project Details pages.
// Tasks are ERPNext Task records loaded through construction_management...task.get_construction_tasks.
frappe.provide("construction_management");

construction_management.TASK_STATUSES = ["Open", "Working", "Pending Review", "Overdue", "Completed"];

construction_management.TASK_PRIORITIES = ["Low", "Medium", "High", "Urgent"];

construction_management.TASKS_METHOD = "construction_management.construction_management.task.get_construction_tasks";

construction_management.load_tasks = function (args = {}) {
	return frappe
		.call({ method: construction_management.TASKS_METHOD, args })
		.then((r) => {
			const data = r.message || {};
			return {
				mapped_project: data.mapped_project,
				tasks: (data.tasks || []).map((t) => ({
					id: t.name,
					subject: t.subject || "",
					project: t.project || "",
					project_name: t.project_name || "",
					project_code: t.project_code || "",
					phase: t.phase || "",
					assigned_to: t.assigned_to || "",
					priority: t.priority || "",
					status: t.status || "Open",
					start: t.exp_start_date || "",
					due: t.exp_end_date || "",
					progress: t.progress || 0,
				})),
			};
		});
};

// Priority is shown as signal bars: one filled bar per level.
construction_management.priority_badge = function (priority) {
	if (!priority) return "";
	const level = construction_management.TASK_PRIORITIES.indexOf(priority) + 1;
	const bars = construction_management.TASK_PRIORITIES.map(
		(_, index) => `<span class="cm-priority-bar${index < level ? " filled" : ""}"></span>`
	).join("");
	const css_class = priority.toLowerCase();
	return `<span class="cm-priority cm-priority-${css_class}"><span class="cm-priority-bars">${bars}</span>${__(priority)}</span>`;
};

construction_management.task_form_fields = function (values = {}) {
	return [
		{ fieldname: "subject", fieldtype: "Data", label: __("Subject"), reqd: 1, default: values.subject },
		{ fieldname: "project", fieldtype: "Link", options: "Project", label: __("Project"), default: values.project },
		{
			fieldname: "status",
			fieldtype: "Select",
			label: __("Status"),
			options: construction_management.TASK_STATUSES,
			default: values.status || "Open",
		},
		{
			fieldname: "priority",
			fieldtype: "Select",
			label: __("Priority"),
			options: ["", ...construction_management.TASK_PRIORITIES],
			default: values.priority || "Medium",
		},
		{ fieldtype: "Column Break" },
		{ fieldname: "exp_start_date", fieldtype: "Date", label: __("Start Date"), default: values.start },
		{ fieldname: "exp_end_date", fieldtype: "Date", label: __("Due Date"), default: values.due },
		{ fieldname: "progress", fieldtype: "Percent", label: __("% Progress"), default: values.progress || 0 },
	];
};

construction_management.show_task_create_dialog = function ({ project, on_saved } = {}) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Task"),
		size: "large",
		fields: construction_management.task_form_fields({ project }),
		primary_action_label: __("Create"),
		primary_action: (values) => {
			frappe.db.insert({ doctype: "Task", ...values }).then((doc) => {
				dialog.hide();
				frappe.show_alert({ message: __("Task {0} created", [doc.name]), indicator: "green" });
				on_saved && on_saved(doc);
			});
		},
	});
	dialog.show();
};

construction_management.show_task_details = function (task, { on_saved } = {}) {
	const esc = frappe.utils.escape_html;
	const route = frappe.get_route();
	const on_project_page = route[0] === "construction-project-details" && !!task.project_code && route[1] === task.project_code;
	const can_edit = frappe.model.can_write("Task");

	const summary = [
		[__("Task ID"), esc(task.id)],
		[__("Phase"), esc(task.phase || "-")],
		[__("Assigned To"), esc(task.assigned_to || __("Unassigned"))],
	];
	const fields = [{ fieldtype: "HTML", fieldname: "summary" }, { fieldtype: "Section Break" }];
	fields.push(...construction_management.task_form_fields(task));
	if (!can_edit) {
		fields.forEach((df) => df.fieldname && df.fieldname !== "summary" && (df.read_only = 1));
	}

	const dialog = new frappe.ui.Dialog({ title: task.subject, size: "large", fields });
	dialog.fields_dict.summary.$wrapper.html(`
		<div class="cm-task-detail-grid">
			${summary
				.map(
					([label, value]) => `
				<div>
					<div class="cm-task-detail-label">${label}</div>
					<div class="cm-task-detail-value">${value}</div>
				</div>`
				)
				.join("")}
		</div>
	`);

	if (can_edit) {
		dialog.set_primary_action(__("Save"), (values) => {
			frappe
				.call({
					method: "frappe.client.set_value",
					args: { doctype: "Task", name: task.id, fieldname: values },
				})
				.then(() => {
					dialog.hide();
					frappe.show_alert({ message: __("Task {0} updated", [task.id]), indicator: "green" });
					on_saved && on_saved();
				});
		});
	}

	if (!on_project_page) {
		dialog.add_custom_action(__("Open Project"), () => {
			dialog.hide();
			construction_management.open_task_project(task);
		});
	}
	dialog.show();
};

construction_management.open_task_project = function (task) {
	if (task.project) {
		frappe.set_route("construction-project-details", task.project_code || task.project);
	}
};

// Table of tasks with search and filters. Used on the Project Tasks page (all projects)
// and inside the Tasks tab of a project (show_project: false, that project's tasks).
construction_management.TaskList = class TaskList {
	constructor({ parent, loader, show_project = true, show_create = false, default_project = null }) {
		this.loader = loader;
		this.tasks = [];
		this.show_project = show_project;
		this.show_create = show_create && frappe.model.can_create("Task");
		this.default_project = default_project;
		this.make_layout(parent);
		this.ready = this.reload();
	}

	reload() {
		this.show_message(__("Loading tasks..."));
		return this.loader().then((tasks) => {
			this.tasks = tasks;
			this.refresh_filter_options();
			this.render();
		});
	}

	make_layout(parent) {
		this.$wrapper = $(`
			<div class="cm-tasks-card">
				<div class="cm-tasks-filters">
					<input type="search" class="form-control input-sm cm-tasks-search"
						placeholder="${__("Search task name, ID or assignee")}">
					${this.show_project ? `<select class="form-control input-sm" data-filter="project"></select>` : ""}
					<select class="form-control input-sm" data-filter="status"></select>
					<select class="form-control input-sm" data-filter="priority"></select>
					<select class="form-control input-sm" data-filter="assigned_to"></select>
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
		this.$wrapper.find(".cm-tasks-create").on("click", () => this.create_task());

		this.$wrapper.on("click", ".cm-tasks-project-link", (e) => {
			e.stopPropagation();
			const task = this.tasks.find((t) => t.id === $(e.currentTarget).attr("data-task"));
			construction_management.open_task_project(task);
		});
		this.$wrapper.on("click", "tbody tr[data-task]", (e) => {
			const task = this.tasks.find((t) => t.id === $(e.currentTarget).attr("data-task"));
			construction_management.show_task_details(task, { on_saved: () => this.reload() });
		});
	}

	create_task() {
		const project = this.default_project || this.get_filter("project") || null;
		construction_management.show_task_create_dialog({ project, on_saved: () => this.reload() });
	}

	refresh_filter_options() {
		const esc = frappe.utils.escape_html;
		const options = (values, placeholder) =>
			`<option value="">${placeholder}</option>` +
			values.map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join("");
		const set = (name, html) => {
			const $select = this.$wrapper.find(`select[data-filter="${name}"]`);
			const current = $select.val();
			$select.html(html);
			if (current && $select.find(`option[value="${current}"]`).length) $select.val(current);
		};

		const projects = new Map(this.tasks.filter((t) => t.project).map((t) => [t.project, t.project_name]));
		const assignees = [...new Set(this.tasks.map((t) => t.assigned_to).filter(Boolean))].sort();
		set("project", options([...projects].sort((a, b) => a[1].localeCompare(b[1])), __("All Projects")));
		set("status", options(construction_management.TASK_STATUSES.map((s) => [s, __(s)]), __("All Statuses")));
		set("priority", options(construction_management.TASK_PRIORITIES.map((p) => [p, __(p)]), __("All Priorities")));
		set("assigned_to", options(assignees.map((a) => [a, a]), __("All Assignees")));
	}

	get_filter(name) {
		return this.$wrapper.find(`select[data-filter="${name}"]`).val() || "";
	}

	// Accepts an ERPNext Project name or a Project Code (for example PRJ-001).
	set_project(value) {
		this.ready.then(() => {
			const $project = this.$wrapper.find('select[data-filter="project"]');
			let match = value && $project.find(`option[value="${value}"]`).length ? value : "";
			if (!match && value) {
				match = this.tasks.find((t) => t.project_code === value)?.project || "";
			}
			$project.val(match);
			this.render();
		});
	}

	get_filtered() {
		const search = (this.$search.val() || "").trim().toLowerCase();
		const filters = ["project", "status", "priority", "assigned_to"]
			.map((name) => [name, this.get_filter(name)])
			.filter(([, value]) => value);

		return this.tasks.filter((task) => {
			const matches_search =
				!search ||
				[task.subject, task.id, task.assigned_to].some((value) => (value || "").toLowerCase().includes(search));
			return matches_search && filters.every(([name, value]) => task[name] === value);
		});
	}

	show_message(message) {
		const columns = this.show_project ? 9 : 8;
		this.$wrapper.find("tbody").html(`<tr><td colspan="${columns}" class="cm-tasks-empty">${message}</td></tr>`);
	}

	render() {
		const tasks = this.get_filtered();

		this.$wrapper
			.find(".cm-tasks-count")
			.text(__("Showing {0} of {1} tasks", [tasks.length, this.tasks.length]));

		if (!tasks.length) {
			this.show_message(__("No tasks match the selected filters."));
			return;
		}
		this.$wrapper.find("tbody").html(tasks.map((task) => this.task_row(task)).join(""));
	}

	task_row(task) {
		const esc = frappe.utils.escape_html;
		const project_cell = this.show_project
			? `<td><a class="cm-tasks-project-link" data-task="${esc(task.id)}">${esc(task.project_name)}</a></td>`
			: "";

		return `
			<tr data-task="${esc(task.id)}" title="${__("Open task details")}">
				<td class="cm-tasks-name">${esc(task.subject)}</td>
				<td class="cm-tasks-muted">${esc(task.id)}</td>
				${project_cell}
				<td class="cm-tasks-nowrap">${esc(task.assigned_to)}</td>
				<td>${construction_management.priority_badge(task.priority)}</td>
				<td>${construction_management.status_pill(task.status)}</td>
				<td class="cm-tasks-nowrap">${task.start ? frappe.datetime.str_to_user(task.start) : ""}</td>
				<td class="cm-tasks-nowrap">${task.due ? frappe.datetime.str_to_user(task.due) : ""}</td>
				<td class="cm-tasks-open">${frappe.utils.icon("right", "sm")}</td>
			</tr>
		`;
	}
};
