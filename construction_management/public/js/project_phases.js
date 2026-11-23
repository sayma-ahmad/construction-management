// Phase table and New Phase dialog shared by the Project Phases and Project Details pages.
// Phases are Project Phase records loaded through construction_management...phase.get_project_phases.
frappe.provide("construction_management");

construction_management.PHASE_STATUSES = ["Not Started", "In Progress", "On Hold", "Completed"];

construction_management.PHASES_METHOD = "construction_management.construction_management.phase.get_project_phases";

construction_management.load_phases = function (args = {}) {
	return frappe.call({ method: construction_management.PHASES_METHOD, args }).then((r) => {
		const data = r.message || {};
		const position = {};
		return {
			mapped_project: data.mapped_project,
			phases: (data.phases || []).map((p) => {
				position[p.project] = (position[p.project] || 0) + 1;
				return {
					id: p.name,
					name: p.phase_name,
					number: p.sequence || position[p.project],
					project: p.project,
					project_name: p.project_name,
					start: p.start_date,
					end: p.end_date,
					status: p.display_status || p.status,
					progress: Math.round(p.progress || 0),
				};
			}),
		};
	});
};

construction_management.progress_bar = function (percent) {
	return `
		<div class="cm-progress">
			<div class="cm-progress-bar"><div class="cm-progress-fill" style="width: ${percent}%"></div></div>
			<span class="cm-progress-value">${percent}%</span>
		</div>
	`;
};

construction_management.show_phase_create_dialog = function ({ project, on_saved } = {}) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Phase"),
		fields: [
			{ fieldname: "phase_name", fieldtype: "Data", label: __("Phase Name"), reqd: 1 },
			{ fieldname: "project", fieldtype: "Link", options: "Project", label: __("Project"), reqd: 1, default: project },
			{
				fieldname: "status",
				fieldtype: "Select",
				label: __("Status"),
				options: construction_management.PHASE_STATUSES,
				default: "Not Started",
			},
			{ fieldtype: "Column Break" },
			{ fieldname: "start_date", fieldtype: "Date", label: __("Start Date"), reqd: 1 },
			{ fieldname: "end_date", fieldtype: "Date", label: __("End Date"), reqd: 1 },
			{ fieldname: "progress", fieldtype: "Percent", label: __("Progress"), default: 0 },
		],
		primary_action_label: __("Create"),
		primary_action: (values) => {
			frappe.db.insert({ doctype: "Project Phase", ...values }).then((doc) => {
				dialog.hide();
				frappe.show_alert({ message: __("Phase {0} created", [doc.phase_name]), indicator: "green" });
				on_saved && on_saved(doc);
			});
		},
	});
	dialog.show();
};

// Project Details still identifies projects by their sample code; ERPNext projects are matched by name.
construction_management.open_phase_project = function (phase) {
	const sample = construction_management.SAMPLE_PROJECTS.find((p) => p.name === phase.project_name);
	if (sample) {
		frappe.set_route("construction-project-details", sample.code, "phases");
	} else {
		frappe.set_route("Form", "Project Phase", phase.id);
	}
};

// Table of phases with search and filters. Used on the Project Phases page (all projects)
// and inside the Phases tab of a project (show_project: false, that project's phases).
construction_management.PhaseList = class PhaseList {
	constructor({ parent, loader, show_project = true, show_create = false, default_project = null }) {
		this.loader = loader;
		this.phases = [];
		this.show_project = show_project;
		this.show_create = show_create && frappe.model.can_create("Project Phase");
		this.default_project = default_project;
		this.make_layout(parent);
		this.ready = this.reload();
	}

	reload() {
		this.show_message(__("Loading phases..."));
		return this.loader().then((phases) => {
			this.phases = phases;
			this.refresh_filter_options();
			this.render();
		});
	}

	make_layout(parent) {
		this.$wrapper = $(`
			<div class="cm-tasks-card">
				<div class="cm-tasks-filters">
					<input type="search" class="form-control input-sm cm-phases-search"
						placeholder="${__("Search phase or project")}">
					${this.show_project ? `<select class="form-control input-sm" data-filter="project"></select>` : ""}
					<select class="form-control input-sm" data-filter="name"></select>
					<select class="form-control input-sm" data-filter="status"></select>
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
		this.$wrapper.find(".cm-phases-create").on("click", () => this.create_phase());

		// On the Project Phases page a row opens the project's Phases tab.
		// Inside that tab the row is already in context, so it is not clickable.
		if (this.show_project) {
			this.$wrapper.on("click", "tbody tr[data-phase]", (e) => {
				const phase = this.phases.find((p) => p.id === $(e.currentTarget).attr("data-phase"));
				construction_management.open_phase_project(phase);
			});
		}
	}

	create_phase() {
		const project = this.default_project || this.get_filter("project") || null;
		construction_management.show_phase_create_dialog({ project, on_saved: () => this.reload() });
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

		const projects = new Map(this.phases.map((p) => [p.project, p.project_name]));
		const names = [...new Set(this.phases.map((p) => p.name))].sort();
		set("project", options([...projects].sort((a, b) => a[1].localeCompare(b[1])), __("All Projects")));
		set("name", options(names.map((n) => [n, n]), __("All Phases")));
		set("status", options(construction_management.PHASE_STATUSES.map((s) => [s, __(s)]), __("All Statuses")));
	}

	get_filter(name) {
		return this.$wrapper.find(`select[data-filter="${name}"]`).val() || "";
	}

	// Accepts an ERPNext Project name or a Project Details sample code (for example PRJ-002).
	set_project(value) {
		this.ready.then(() => {
			const $project = this.$wrapper.find('select[data-filter="project"]');
			let match = value && $project.find(`option[value="${value}"]`).length ? value : "";
			const sample = value && construction_management.get_project && construction_management.get_project(value);
			if (!match && sample) {
				match = $project.find("option").filter((_, o) => $(o).text() === sample.name).first().val() || "";
			}
			$project.val(match);
			this.render();
		});
	}

	get_filtered() {
		const search = (this.$search.val() || "").trim().toLowerCase();
		const filters = ["project", "name", "status"]
			.map((name) => [name, this.get_filter(name)])
			.filter(([, value]) => value);

		return this.phases.filter((phase) => {
			const matches_search =
				!search ||
				[phase.name, phase.project_name, phase.project].some((value) => (value || "").toLowerCase().includes(search));
			return matches_search && filters.every(([name, value]) => phase[name] === value);
		});
	}

	show_message(message) {
		const columns = this.show_project ? 8 : 7;
		this.$wrapper.find("tbody").html(`<tr><td colspan="${columns}" class="cm-tasks-empty">${message}</td></tr>`);
	}

	render() {
		const phases = this.get_filtered();

		this.$wrapper
			.find(".cm-tasks-count")
			.text(__("Showing {0} of {1} phases", [phases.length, this.phases.length]));

		if (!phases.length) {
			this.show_message(__("No phases match the selected filters."));
			return;
		}
		this.$wrapper.find("tbody").html(phases.map((phase) => this.phase_row(phase)).join(""));
	}

	phase_row(phase) {
		const esc = frappe.utils.escape_html;
		const clickable = this.show_project;

		return `
			<tr ${clickable ? `data-phase="${esc(phase.id)}" title="${__("Open project phases")}"` : ""}>
				<td><span class="cm-phase-number">${phase.number}</span></td>
				<td class="cm-tasks-name">${esc(phase.name)}</td>
				${this.show_project ? `<td class="cm-tasks-nowrap">${esc(phase.project_name)} <span class="cm-tasks-muted">${esc(phase.project)}</span></td>` : ""}
				<td class="cm-tasks-nowrap">${phase.start ? frappe.datetime.str_to_user(phase.start) : ""}</td>
				<td class="cm-tasks-nowrap">${phase.end ? frappe.datetime.str_to_user(phase.end) : ""}</td>
				<td>${construction_management.status_pill(phase.status)}</td>
				<td class="cm-phase-progress">${construction_management.progress_bar(phase.progress)}</td>
				<td class="cm-tasks-open">${clickable ? frappe.utils.icon("right", "sm") : ""}</td>
			</tr>
		`;
	}
};
