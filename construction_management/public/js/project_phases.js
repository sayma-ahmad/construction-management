// Sample phases and the phase table shared by the Project Phases and Project Details pages.
// Phases are derived from the sample projects: the project timeline and overall progress
// are split evenly across the standard construction phases.
// Real phases will be loaded from the backend in a later story.
frappe.provide("construction_management");

construction_management.PHASE_STATUSES = ["Not Started", "In Progress", "On Hold", "Completed"];

construction_management.get_project_phases = function (project) {
	const phases = construction_management.PROJECT_PHASES;
	const share = 100 / phases.length;
	const total_days = Math.max(frappe.datetime.get_diff(project.end, project.start), phases.length);
	const phase_days = Math.floor(total_days / phases.length);

	return phases.map((name, index) => {
		const done = (project.progress - index * share) / share;
		const progress = Math.round(Math.min(Math.max(done, 0), 1) * 100);
		let status = progress >= 100 ? "Completed" : progress > 0 ? "In Progress" : "Not Started";
		if (status === "In Progress" && project.status === "On Hold") {
			status = "On Hold";
		}

		const start = frappe.datetime.add_days(project.start, index * phase_days);
		const end =
			index === phases.length - 1
				? project.end
				: frappe.datetime.add_days(project.start, (index + 1) * phase_days - 1);

		return { number: index + 1, name, project: project.code, start, end, status, progress };
	});
};

construction_management.get_all_phases = function () {
	return construction_management.SAMPLE_PROJECTS.flatMap(construction_management.get_project_phases);
};

construction_management.progress_bar = function (percent) {
	return `
		<div class="cm-progress">
			<div class="cm-progress-bar"><div class="cm-progress-fill" style="width: ${percent}%"></div></div>
			<span class="cm-progress-value">${percent}%</span>
		</div>
	`;
};

construction_management.show_phase_create_placeholder = function () {
	frappe.msgprint({
		title: __("New Phase"),
		message: __("Phase creation will be available in a later release."),
		indicator: "blue",
	});
};

// Table of phases with search and filters. Used on the Project Phases page (all projects)
// and inside the Phases tab of a project (show_project: false, that project's phases).
construction_management.PhaseList = class PhaseList {
	constructor({ parent, phases, show_project = true, show_create = false }) {
		this.phases = phases;
		this.show_project = show_project;
		this.show_create = show_create;
		this.make_layout(parent);
		this.render();
	}

	make_layout(parent) {
		const esc = frappe.utils.escape_html;
		const options = (values, placeholder) =>
			`<option value="">${placeholder}</option>` +
			values.map((v) => `<option value="${esc(v)}">${__(v)}</option>`).join("");

		const project_codes = [...new Set(this.phases.map((p) => p.project))];
		const project_options =
			`<option value="">${__("All Projects")}</option>` +
			project_codes
				.map((code) => `<option value="${esc(code)}">${esc(construction_management.get_project(code).name)}</option>`)
				.join("");

		this.$wrapper = $(`
			<div class="cm-tasks-card">
				<div class="cm-tasks-filters">
					<input type="search" class="form-control input-sm cm-phases-search"
						placeholder="${__("Search phase or project")}">
					${this.show_project ? `<select class="form-control input-sm" data-filter="project">${project_options}</select>` : ""}
					<select class="form-control input-sm" data-filter="name">${options(construction_management.PROJECT_PHASES, __("All Phases"))}</select>
					<select class="form-control input-sm" data-filter="status">${options(construction_management.PHASE_STATUSES, __("All Statuses"))}</select>
				</div>
				<div class="cm-tasks-toolbar">
					<span class="cm-tasks-count"></span>
					<div class="cm-tasks-actions">
						<button class="btn btn-xs btn-default cm-phases-clear">${__("Clear Filters")}</button>
						${this.show_create ? `<button class="btn btn-xs btn-primary cm-phases-create">${__("New Phase")}</button>` : ""}
					</div>
				</div>
				<div class="cm-tasks-table-wrapper">
					<table class="cm-tasks-table">
						<thead>
							<tr>
								<th>${__("Phase No.")}</th>
								<th>${__("Phase Name")}</th>
								${this.show_project ? `<th>${__("Project")}</th>` : ""}
								<th>${__("Start Date")}</th>
								<th>${__("End Date")}</th>
								<th>${__("Status")}</th>
								<th>${__("Progress")}</th>
								<th></th>
							</tr>
						</thead>
						<tbody></tbody>
					</table>
				</div>
			</div>
		`).appendTo(parent);

		this.$search = this.$wrapper.find(".cm-phases-search");
		this.$search.on("input", frappe.utils.debounce(() => this.render(), 200));
		this.$wrapper.find("select[data-filter]").on("change", () => this.render());

		this.$wrapper.find(".cm-phases-clear").on("click", () => {
			this.$search.val("");
			this.$wrapper.find("select[data-filter]").val("");
			this.render();
		});
		this.$wrapper.find(".cm-phases-create").on("click", construction_management.show_phase_create_placeholder);

		// On the Project Phases page a row opens the project's Phases tab.
		// Inside that tab the row is already in context, so it is not clickable.
		if (this.show_project) {
			this.$wrapper.on("click", "tbody tr[data-project]", (e) => {
				frappe.set_route("construction-project-details", $(e.currentTarget).attr("data-project"), "phases");
			});
		}
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
		const filters = ["project", "name", "status"]
			.map((name) => [name, this.get_filter(name)])
			.filter(([, value]) => value);

		return this.phases.filter((phase) => {
			const project = construction_management.get_project(phase.project);
			const matches_search =
				!search ||
				[phase.name, project.name, project.code].some((value) => value.toLowerCase().includes(search));
			return matches_search && filters.every(([name, value]) => phase[name] === value);
		});
	}

	render() {
		const phases = this.get_filtered();
		const columns = this.show_project ? 8 : 7;

		this.$wrapper
			.find(".cm-tasks-count")
			.text(__("Showing {0} of {1} phases", [phases.length, this.phases.length]));

		const rows = phases.length
			? phases.map((phase) => this.phase_row(phase)).join("")
			: `<tr><td colspan="${columns}" class="cm-tasks-empty">${__("No phases match the selected filters.")}</td></tr>`;

		this.$wrapper.find("tbody").html(rows);
	}

	phase_row(phase) {
		const esc = frappe.utils.escape_html;
		const project = construction_management.get_project(phase.project);
		const clickable = this.show_project;

		return `
			<tr ${clickable ? `data-project="${esc(phase.project)}" title="${__("Open project phases")}"` : ""}>
				<td><span class="cm-phase-number">${phase.number}</span></td>
				<td class="cm-tasks-name">${__(phase.name)}</td>
				${this.show_project ? `<td class="cm-tasks-nowrap">${esc(project.name)} <span class="cm-tasks-muted">${esc(project.code)}</span></td>` : ""}
				<td class="cm-tasks-nowrap">${frappe.datetime.str_to_user(phase.start)}</td>
				<td class="cm-tasks-nowrap">${frappe.datetime.str_to_user(phase.end)}</td>
				<td>${construction_management.status_pill(phase.status)}</td>
				<td class="cm-phase-progress">${construction_management.progress_bar(phase.progress)}</td>
				<td class="cm-tasks-open">${clickable ? frappe.utils.icon("right", "sm") : ""}</td>
			</tr>
		`;
	}
};
