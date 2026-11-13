const CM_SHARED_ASSETS = [
	"/assets/construction_management/js/sample_projects.js",
	"/assets/construction_management/css/construction_management.css",
];

frappe.pages["construction-projects"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Projects"),
		single_column: true,
	});

	page.set_primary_action(__("New Project"), show_create_placeholder, "add");
	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	frappe.require(CM_SHARED_ASSETS, () => {
		new ProjectList(page, construction_management.SAMPLE_PROJECTS);
	});
};

class ProjectList {
	constructor(page, projects) {
		this.page = page;
		this.projects = projects;
		this.make_filters();
		this.make_layout();
		this.render();
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

		const locations = [...new Set(this.projects.map((p) => p.location))].sort();
		this.location = this.page.add_field({
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Select",
			options: ["", ...locations],
			change: () => this.render(),
		});
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
		const status = this.status.get_value();
		const location = this.location.get_value();

		return this.projects.filter((p) => {
			const matches_search =
				!search ||
				[p.name, p.code, p.client, p.location].some((value) => value.toLowerCase().includes(search));
			return matches_search && (!status || p.status === status) && (!location || p.location === location);
		});
	}

	render() {
		const projects = this.get_filtered();

		this.$wrapper
			.find(".cm-projects-count")
			.text(__("Showing {0} of {1} projects", [projects.length, this.projects.length]));

		const rows = projects.length
			? projects.map(project_row).join("")
			: `<tr><td colspan="8" class="cm-projects-empty">${__("No projects match the selected filters.")}</td></tr>`;

		this.$wrapper.find("tbody").html(rows);
	}
}

function project_row(project) {
	const esc = frappe.utils.escape_html;
	return `
		<tr data-code="${esc(project.code)}" title="${__("Open project details")}">
			<td class="cm-projects-name">${esc(project.name)}</td>
			<td class="cm-projects-muted">${esc(project.code)}</td>
			<td>${esc(project.client)}</td>
			<td>${esc(project.location)}</td>
			<td>${construction_management.status_pill(project.status)}</td>
			<td class="cm-projects-nowrap">${frappe.datetime.str_to_user(project.start)}</td>
			<td class="cm-projects-nowrap">${frappe.datetime.str_to_user(project.end)}</td>
			<td class="cm-projects-open">${frappe.utils.icon("right", "sm")}</td>
		</tr>
	`;
}

function show_create_placeholder() {
	frappe.msgprint({
		title: __("New Project"),
		message: __("Project creation will be available in a later release."),
		indicator: "blue",
	});
}
