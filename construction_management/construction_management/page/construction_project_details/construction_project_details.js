const CM_PROJECT_DETAIL_ASSETS = [
	"/assets/construction_management/js/sample_projects.js",
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

const CM_PROJECT_PLACEHOLDERS = {
	tasks: {
		icon: "list-alt",
		title: "Tasks",
		text: "The task list for this project will appear here once task tracking is connected.",
	},
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

frappe.pages["construction-project-details"].on_page_show = function (wrapper) {
	wrapper.project_details.show(frappe.get_route()[1]);
};

class ProjectDetails {
	constructor(page) {
		this.page = page;
		this.ready = frappe.require(CM_PROJECT_DETAIL_ASSETS);
		this.$wrapper = $(`<div class="cm-pd"></div>`).appendTo(page.main);
		this.$wrapper.on("click", ".cm-pd-tab", (e) => this.set_tab($(e.currentTarget).attr("data-tab")));
	}

	show(code) {
		this.ready.then(() => {
			const project = construction_management.SAMPLE_PROJECTS.find((p) => p.code === code);
			if (!project) {
				this.render_not_found();
				return;
			}
			this.project = project;
			this.page.set_title(project.name);
			this.render();
			this.set_tab("overview");
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
			<div class="cm-pd-panel" data-panel="phases">${this.phases_panel()}</div>
			${Object.keys(CM_PROJECT_PLACEHOLDERS)
				.map((key) => `<div class="cm-pd-panel" data-panel="${key}">${this.placeholder_panel(key)}</div>`)
				.join("")}
		`);
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
		const current_phase = this.get_phases().find((phase) => phase.percent < 100);

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

	phases_panel() {
		const rows = this.get_phases()
			.map(
				(phase, index) => `
				<div class="cm-pd-phase">
					<div class="cm-pd-phase-index">${index + 1}</div>
					<div class="cm-pd-phase-body">
						<div class="cm-pd-phase-title">
							<span>${__(phase.name)}</span>
							${construction_management.status_pill(phase.status)}
						</div>
						${this.progress_bar(phase.percent)}
					</div>
					<div class="cm-pd-phase-percent">${phase.percent}%</div>
				</div>`
			)
			.join("");

		return `
			<div class="cm-pd-card">
				<div class="cm-pd-card-title">${__("Phases")}</div>
				${rows}
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
