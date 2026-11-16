const CM_PROJECT_DETAIL_ASSETS = [
	"/assets/construction_management/js/sample_projects.js",
	"/assets/construction_management/js/project_tasks.js",
	"/assets/construction_management/js/project_phases.js",
	"/assets/construction_management/css/construction_management.css",
];

const CM_PROJECT_TABS = [
	{ key: "overview", label: "Overview" },
	{ key: "tasks", label: "Tasks" },
	{ key: "phases", label: "Phases" },
	{ key: "dpr", label: "DPR" },
	{ key: "issues", label: "Issues" },
	{ key: "materials", label: "Materials" },
];

const CM_PROJECT_DPRS_METHOD =
	"construction_management.construction_management.doctype.daily_progress_report.daily_progress_report.get_project_dprs";

const CM_PROJECT_PLACEHOLDERS = {
	dpr: {
		icon: "today",
		title: "Daily Progress Reports",
		text: "Daily progress reports submitted from site will appear here.",
	},
	issues: {
		icon: "solid-warning",
		title: "Site Issues",
		text: "Issues raised on site for this project will appear here.",
	},
	materials: {
		icon: "stock",
		title: "Materials",
		text: "Material requests, receipts and stock for this project will appear here.",
	},
};

frappe.pages["construction-project-details"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Project Details"),
		single_column: true,
	});
	page.set_secondary_action(__("Back to Projects"), () => frappe.set_route("construction-projects"));

	wrapper.project_details = new ProjectDetails(page);
};

// Route: /app/construction-project-details/<project code>[/<tab>]
frappe.pages["construction-project-details"].on_page_show = function (wrapper) {
	const route = frappe.get_route();
	wrapper.project_details.show(route[1], route[2]);
};

class ProjectDetails {
	constructor(page) {
		this.page = page;
		this.ready = frappe.require(CM_PROJECT_DETAIL_ASSETS);
		this.$wrapper = $(`<div class="cm-pd"></div>`).appendTo(page.main);
		this.$wrapper.on("click", ".cm-pd-tab", (e) => this.set_tab($(e.currentTarget).attr("data-tab")));
	}

	show(code, tab) {
		this.ready.then(() => {
			const project = construction_management.SAMPLE_PROJECTS.find((p) => p.code === code);
			if (!project) {
				this.render_not_found();
				return;
			}
			this.project = project;
			this.page.set_title(project.name);
			this.render();
			this.set_tab(CM_PROJECT_TABS.some((t) => t.key === tab) ? tab : "overview");
		});
	}

	render() {
		const p = this.project;
		const esc = frappe.utils.escape_html;
		const pending = p.total_tasks - p.completed_tasks;

		this.$wrapper.html(`
			<div class="cm-pd-header">
				<span class="cm-pd-subtitle">${esc(p.code)} · ${esc(p.client)} · ${esc(p.location)}</span>
				${construction_management.status_pill(p.status)}
			</div>

			<div class="cm-pd-summary">
				<div class="cm-pd-card cm-pd-stat">
					<div class="cm-pd-stat-label">${__("Project Progress")}</div>
					<div class="cm-pd-stat-value">${p.progress}%</div>
					${this.progress_bar(p.progress)}
				</div>
				${this.stat_card(__("Total Tasks"), p.total_tasks, __("Across all phases"))}
				${this.stat_card(__("Completed Tasks"), p.completed_tasks, __("{0}% of all tasks", [this.percent(p.completed_tasks, p.total_tasks)]))}
				${this.stat_card(__("Pending Tasks"), pending, __("Still to be done"))}
			</div>

			<div class="cm-pd-tabs" role="tablist">
				${CM_PROJECT_TABS.map(
			(tab) => `<button class="cm-pd-tab" role="tab" data-tab="${tab.key}">${__(tab.label)}</button>`
		).join("")}
			</div>

			<div class="cm-pd-panel" data-panel="overview">${this.overview_panel()}</div>
			<div class="cm-pd-panel" data-panel="tasks"></div>
			<div class="cm-pd-panel" data-panel="phases">${this.phases_panel()}</div>
			<div class="cm-pd-panel" data-panel="dpr">${this.dpr_loading_panel()}</div>
			${Object.keys(CM_PROJECT_PLACEHOLDERS)
				.map((key) => `<div class="cm-pd-panel" data-panel="${key}">${this.placeholder_panel(key)}</div>`)
				.join("")}
		`);
		this.render_tasks();
		this.render_phases();
	}

	render_phases() {
		const $panel = this.$wrapper.find('[data-panel="phases"]');
		$panel.html(`
			<div class="cm-pd-tasks-header">
				<span class="cm-pd-subtitle">${__("Phases for {0}", [frappe.utils.escape_html(this.project.name)])}</span>
				<button class="btn btn-xs btn-default cm-pd-all-phases">${__("Open in Project Phases")}</button>
			</div>
		`);
		$panel.find(".cm-pd-all-phases").on("click", () => frappe.set_route("construction-phases", this.project.code));

		new construction_management.PhaseList({
			parent: $panel,
			phases: construction_management.get_project_phases(this.project),
			show_project: false,
			show_create: true,
		});
	}

	render_tasks() {
		const $panel = this.$wrapper.find('[data-panel="tasks"]');
		$panel.html(`
			<div class="cm-pd-tasks-header">
				<span class="cm-pd-subtitle">${__("Tasks for {0}", [frappe.utils.escape_html(this.project.name)])}</span>
				<button class="btn btn-xs btn-default cm-pd-all-tasks">${__("Open in Project Tasks")}</button>
			</div>
		`);
		$panel.find(".cm-pd-all-tasks").on("click", () => frappe.set_route("construction-tasks", this.project.code));

		new construction_management.TaskList({
			parent: $panel,
			tasks: construction_management.SAMPLE_TASKS.filter((task) => task.project === this.project.code),
			show_project: false,
			show_create: true,
		});
	}

	render_not_found() {
		this.project = null;
		this.page.set_title(__("Project Details"));
		this.$wrapper.html(`
			<div class="cm-pd-card cm-pd-empty">
				<div class="cm-pd-empty-title">${__("Project not found")}</div>
				<div class="cm-pd-empty-text">${__("This project does not exist in the sample data.")}</div>
				<button class="btn btn-sm btn-default cm-pd-back">${__("Back to Projects")}</button>
			</div>
		`);
		this.$wrapper.find(".cm-pd-back").on("click", () => frappe.set_route("construction-projects"));
	}

	set_tab(key) {
		this.$wrapper.find(".cm-pd-tab").each((_, el) => {
			const active = $(el).attr("data-tab") === key;
			$(el).toggleClass("active", active).attr("aria-selected", active);
		});
		this.$wrapper.find(".cm-pd-panel").each((_, el) => {
			$(el).toggle($(el).attr("data-panel") === key);
		});
	}

	overview_panel() {
		const p = this.project;
		const esc = frappe.utils.escape_html;
		const fields = [
			[__("Project Name"), esc(p.name)],
			[__("Project Code"), esc(p.code)],
			[__("Client"), esc(p.client)],
			[__("Location"), esc(p.location)],
			[__("Status"), construction_management.status_pill(p.status)],
			[__("Project Manager"), esc(p.manager)],
			[__("Start Date"), frappe.datetime.str_to_user(p.start)],
			[__("End Date"), frappe.datetime.str_to_user(p.end)],
		];

		const total_days = Math.max(frappe.datetime.get_diff(p.end, p.start), 1);
		const elapsed_days = Math.min(Math.max(frappe.datetime.get_diff(frappe.datetime.get_today(), p.start), 0), total_days);
		const current_phase = construction_management
			.get_project_phases(p)
			.find((phase) => phase.progress < 100);

		return `
			<div class="cm-pd-overview">
				<div class="cm-pd-card">
					<div class="cm-pd-card-title">${__("Project Information")}</div>
					<div class="cm-pd-fields">
						${fields
				.map(
					([label, value]) => `
							<div>
								<div class="cm-pd-field-label">${label}</div>
								<div class="cm-pd-field-value">${value}</div>
							</div>`
				)
				.join("")}
					</div>
					<div class="cm-pd-field-label">${__("Description")}</div>
					<div class="cm-pd-field-value">${esc(p.description)}</div>
				</div>

				<div class="cm-pd-card">
					<div class="cm-pd-card-title">${__("Progress")}</div>
					<div class="cm-pd-progress-row">
						<div class="cm-pd-progress-label">
							<span>${__("Work Completed")}</span>
							<span>${p.progress}%</span>
						</div>
						${this.progress_bar(p.progress)}
					</div>
					<div class="cm-pd-progress-row">
						<div class="cm-pd-progress-label">
							<span>${__("Time Elapsed")}</span>
							<span>${__("{0} of {1} days", [elapsed_days, total_days])}</span>
						</div>
						${this.progress_bar(this.percent(elapsed_days, total_days), "time")}
					</div>
					<div class="cm-pd-current-phase">
						<div class="cm-pd-field-label">${__("Current Phase")}</div>
						<div class="cm-pd-field-value">${current_phase ? __(current_phase.name) : __("All phases complete")}</div>
					</div>
				</div>
			</div>
		`;
	}

	placeholder_panel(key) {
		const placeholder = CM_PROJECT_PLACEHOLDERS[key];
		return `
			<div class="cm-pd-card cm-pd-empty">
				<div class="cm-pd-empty-icon">${frappe.utils.icon(placeholder.icon, "lg")}</div>
				<div class="cm-pd-empty-title">${__(placeholder.title)}</div>
				<div class="cm-pd-empty-text">${__(placeholder.text)}</div>
			</div>
		`;
	}

	dpr_loading_panel() {
		return `
			<div class="cm-pd-card cm-pd-empty">
				<div class="cm-pd-empty-title">${__("Daily Progress Reports")}</div>
				<div class="cm-pd-empty-text">${__("Loading Daily Progress Reports...")}</div>
			</div>
		`;
	}

	load_dprs() {
		const current_code = this.project?.code;
		const $panel = this.$wrapper.find('.cm-pd-panel[data-panel="dpr"]');

		frappe.call({
			method: CM_PROJECT_DPRS_METHOD,
			args: {
				project_name: this.project.name,
				project_code: this.project.code,
			},
			callback: (r) => {
				if (this.project?.code !== current_code) {
					return;
				}
				const data = r.message || {};
				this.render_dpr_panel($panel, data.mapped_project, data.dprs || []);
			},
			error: () => {
				if (this.project?.code !== current_code) {
					return;
				}
				$panel.html(`
					<div class="cm-pd-card cm-pd-empty">
						<div class="cm-pd-empty-title">${__("Unable to load Daily Progress Reports")}</div>
						<div class="cm-pd-empty-text">${__("Please try again or open the Daily Progress Reports page.")}</div>
						<button class="btn btn-sm btn-default cm-pd-open-dprs">${__("Open Daily Progress Reports")}</button>
					</div>
				`);
				$panel
					.find(".cm-pd-open-dprs")
					.on("click", () => frappe.set_route("daily-progress-reports"));
			},
		});
	}

	render_dpr_panel($panel, mapped_project, dprs) {
		const esc = frappe.utils.escape_html;

		if (!mapped_project) {
			$panel.html(`
				<div class="cm-pd-card cm-pd-empty">
					<div class="cm-pd-empty-icon">${frappe.utils.icon("today", "lg")}</div>
					<div class="cm-pd-empty-title">${__("No Linked ERPNext Project Found")}</div>
					<div class="cm-pd-empty-text">
						${__(
				'Project Details currently uses sample project data ("{0}"). No matching ERPNext Project record was found, so unrelated Daily Progress Reports are not displayed.',
				[esc(this.project.name)]
			)}
					</div>
					<button class="btn btn-sm btn-default cm-pd-open-dprs">${__("Open Daily Progress Reports")}</button>
				</div>
			`);
			$panel
				.find(".cm-pd-open-dprs")
				.on("click", () => frappe.set_route("daily-progress-reports"));
			return;
		}

		const rows_html = dprs.length
			? dprs
				.map((row) => {
					const status = row.review_status || "Draft";
					const status_class = status.toLowerCase().replace(/\s+/g, "-");
					const report_date = row.report_date
						? frappe.datetime.str_to_user(row.report_date)
						: "";
					return `
							<tr data-dpr="${esc(row.name)}" title="${__("Open Daily Progress Report")}">
								<td class="cm-pd-dpr-id">${esc(row.name)}</td>
								<td>${esc(report_date)}</td>
								<td>${flt(row.overall_progress || 0)}%</td>
								<td><span class="cm-status cm-status-${status_class}">${__(status)}</span></td>
								<td>${frappe.utils.icon("right", "sm")}</td>
							</tr>
						`;
				})
				.join("")
			: `<tr><td colspan="5" class="cm-pd-empty-text" style="text-align:center; padding: 24px;">${__(
				"No Daily Progress Reports recorded for this project yet."
			)}</td></tr>`;

		$panel.html(`
			<div class="cm-pd-card">
				<div class="cm-pd-dpr-header">
					<div class="cm-pd-card-title">${__("Daily Progress Reports")}</div>
					<div class="cm-pd-dpr-actions">
						<button class="btn btn-xs btn-default cm-pd-open-dprs">${__("View All")}</button>
						<button class="btn btn-xs btn-primary cm-pd-new-dpr">${__("New DPR")}</button>
					</div>
				</div>
				<div class="cm-pd-dpr-table-wrap">
					<table class="cm-pd-dpr-table">
						<thead>
							<tr>
								<th>${__("DPR ID")}</th>
								<th>${__("Report Date")}</th>
								<th>${__("Progress")}</th>
								<th>${__("Review Status")}</th>
								<th></th>
							</tr>
						</thead>
						<tbody>${rows_html}</tbody>
					</table>
				</div>
			</div>
		`);

		$panel
			.find(".cm-pd-open-dprs")
			.on("click", () => frappe.set_route("daily-progress-reports"));
		$panel
			.find(".cm-pd-new-dpr")
			.on("click", () => frappe.new_doc("Daily Progress Report", { project: mapped_project }));
		$panel.on("click", "tbody tr[data-dpr]", (e) => {
			frappe.set_route("Form", "Daily Progress Report", $(e.currentTarget).attr("data-dpr"));
		});
	}

	// Splits overall progress evenly across the standard construction phases.
	get_phases() {
		const phases = construction_management.PROJECT_PHASES;
		const share = 100 / phases.length;

		return phases.map((name, index) => {
			const done = (this.project.progress - index * share) / share;
			const percent = Math.round(Math.min(Math.max(done, 0), 1) * 100);
			const status = percent >= 100 ? "Completed" : percent > 0 ? "In Progress" : "Not Started";
			return { name, percent, status };
		});
	}

	stat_card(label, value, note) {
		return `
			<div class="cm-pd-card cm-pd-stat">
				<div class="cm-pd-stat-label">${label}</div>
				<div class="cm-pd-stat-value">${format_number(value, null, 0)}</div>
				<div class="cm-pd-stat-note">${note}</div>
			</div>
		`;
	}

	progress_bar(percent, variant = "work") {
		return `
			<div class="cm-pd-bar">
				<div class="cm-pd-bar-fill cm-pd-bar-${variant}" style="width: ${percent}%"></div>
			</div>
		`;
	}

	percent(value, total) {
		return total ? Math.round((value / total) * 100) : 0;
	}
}
