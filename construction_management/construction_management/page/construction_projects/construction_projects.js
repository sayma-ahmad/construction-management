const CM_SHARED_ASSETS = [
	"/assets/construction_management/js/sample_projects.js",
	"/assets/construction_management/css/construction_management.css",
];
const CM_PROJECTS_METHOD = "construction_management.construction_management.project.get_construction_projects";

frappe.pages["construction-projects"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Projects"),
		single_column: true,
	});

	if (frappe.model.can_create("Project")) {
		page.set_primary_action(__("New Project"), () => frappe.set_route("Form", "Project", "new"), "add");
	}
	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	frappe.require(CM_SHARED_ASSETS, () => {
		wrapper.project_list = new ProjectList(page);
	});
};

frappe.pages["construction-projects"].on_page_show = function (wrapper) {
	if (wrapper.project_list) {
		wrapper.project_list.reload();
	}
};

class ProjectList {
	constructor(page) {
		this.page = page;
		this.projects = [];
		this.make_filters();
		this.make_layout();
		this.reload();
	}

	reload() {
		this.show_message(__("Loading projects..."));
		return frappe.call({ method: CM_PROJECTS_METHOD }).then((r) => {
			this.projects = r.message || [];
			this.refresh_location_options();
			this.render();
		});
	}

	make_filters() {
		this.search = this.page.add_field({
			fieldname: "search",
			label: __("Search name, code, client or location"),
			fieldtype: "Data",
		});
		this.search.$input.on("input", frappe.utils.debounce(() => this.render(), 200));
		$(this.search.wrapper).removeClass("col-md-2").addClass("col-md-4");

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", ...construction_management.PROJECT_STATUSES],
			change: () => this.render(),
		});

		this.location = this.page.add_field({
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Select",
			options: [""],
			change: () => this.render(),
		});
	}

	refresh_location_options() {
		const current = (this.location.get_value() || "").trim();
		const locations = [
			...new Set(this.projects.map((p) => (p.location || "").trim()).filter(Boolean)),
		].sort();
		this.location.df.options = ["", ...locations];
		this.location.refresh();
		this.location.set_input(locations.includes(current) ? current : "");
		if (this.location.$input) {
			this.location.$input.off("change.cm_loc").on("change.cm_loc", () => this.render());
		}
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-projects">
				<div class="cm-projects-card">
					<div class="cm-projects-toolbar">
						<span class="cm-projects-count"></span>
						<button class="btn btn-xs btn-default cm-projects-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-projects-table-wrapper">
						<table class="cm-projects-table">
							<thead>
								<tr>
									<th>${__("Project Name")}</th>
									<th>${__("Project Code")}</th>
									<th>${__("Client")}</th>
									<th>${__("Location")}</th>
									<th>${__("Status")}</th>
									<th>${__("Progress")}</th>
									<th>${__("Start Date")}</th>
									<th>${__("End Date")}</th>
									<th></th>
								</tr>
							</thead>
							<tbody></tbody>
						</table>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$wrapper.on("click", "tbody tr[data-code]", (e) => {
			frappe.set_route("construction-project-details", $(e.currentTarget).attr("data-code"));
		});

		this.$wrapper.find(".cm-projects-clear").on("click", () => {
			this.search.set_value("");
			this.status.set_value("");
			this.location.set_value("");
			this.render();
		});
	}

	get_filtered() {
		const search = (this.search.get_value() || "").trim().toLowerCase();
		const status = (this.status.get_value() || "").trim();
		const location = (this.location.get_value() || "").trim();

		return this.projects.filter((p) => {
			const projectLocation = (p.location || "").trim();
			const matches_search =
				!search ||
				[p.name, p.code, p.client, projectLocation].some((value) =>
					(value || "").toLowerCase().includes(search)
				);
			return (
				matches_search &&
				(!status || p.status === status) &&
				(!location || projectLocation === location)
			);
		});
	}

	show_message(message) {
		this.$wrapper.find("tbody").html(`<tr><td colspan="9" class="cm-projects-empty">${message}</td></tr>`);
	}

	render() {
		const projects = this.get_filtered();

		this.$wrapper
			.find(".cm-projects-count")
			.text(__("Showing {0} of {1} projects", [projects.length, this.projects.length]));

		if (!projects.length) {
			this.show_message(__("No projects match the selected filters."));
			return;
		}
		this.$wrapper.find("tbody").html(projects.map(project_row).join(""));
	}
}

function project_row(project) {
	const esc = frappe.utils.escape_html;
	const date = (value) => (value ? frappe.datetime.str_to_user(value) : "");
	return `
		<tr data-code="${esc(project.code)}" title="${__("Open project details")}">
			<td class="cm-projects-name">${esc(project.name)}</td>
			<td class="cm-projects-muted">${esc(project.code)}</td>
			<td>${esc(project.client)}</td>
			<td>${esc(project.location)}</td>
			<td>${construction_management.status_pill(project.status)}</td>
			<td>${progress_cell(project.progress)}</td>
			<td class="cm-projects-nowrap">${date(project.start)}</td>
			<td class="cm-projects-nowrap">${date(project.end)}</td>
			<td class="cm-projects-open">${frappe.utils.icon("right", "sm")}</td>
		</tr>
	`;
}

function progress_cell(progress) {
	if (progress === null || progress === undefined) {
		return `<span class="cm-projects-muted">${__("Not set")}</span>`;
	}
	const percent = Math.round(progress);
	return `
		<div class="cm-progress">
			<div class="cm-progress-bar"><div class="cm-progress-fill" style="width: ${percent}%"></div></div>
			<span class="cm-progress-value">${percent}%</span>
		</div>
	`;
}
