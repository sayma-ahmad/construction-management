// Sample data only. Real projects will be loaded from the Project DocType in a later story.
const SAMPLE_PROJECTS = [
	{
		name: "Riverside Apartments",
		code: "PRJ-001",
		client: "Riverside Housing Ltd",
		location: "Pune",
		status: "In Progress",
		start: "2025-08-01",
		end: "2027-02-15",
		manager: "Anil Mehta",
		description: "Two residential towers with 180 apartments and basement parking.",
	},
	{
		name: "Metro Office Tower",
		code: "PRJ-002",
		client: "Metro Realty Group",
		location: "Mumbai",
		status: "In Progress",
		start: "2025-11-10",
		end: "2027-06-30",
		manager: "Priya Nair",
		description: "22-floor commercial office tower with retail on the ground floor.",
	},
	{
		name: "Green Valley Villas",
		code: "PRJ-003",
		client: "Green Valley Estates",
		location: "Bengaluru",
		status: "On Hold",
		start: "2025-06-15",
		end: "2027-01-20",
		manager: "Rahul Verma",
		description: "Gated community of 40 independent villas. Paused for permit revision.",
	},
	{
		name: "City Mall Renovation",
		code: "PRJ-004",
		client: "City Centre Malls",
		location: "Delhi",
		status: "In Progress",
		start: "2026-01-05",
		end: "2026-12-10",
		manager: "Sneha Kapoor",
		description: "Facade upgrade, new food court and HVAC replacement.",
	},
	{
		name: "Harbor Bridge Repair",
		code: "PRJ-005",
		client: "State Public Works Dept",
		location: "Chennai",
		status: "In Progress",
		start: "2026-03-01",
		end: "2027-03-05",
		manager: "Karthik Iyer",
		description: "Structural repair and resurfacing of the east harbor bridge.",
	},
	{
		name: "Sunrise School Block",
		code: "PRJ-006",
		client: "Sunrise Education Trust",
		location: "Pune",
		status: "Completed",
		start: "2025-02-01",
		end: "2026-06-30",
		manager: "Anil Mehta",
		description: "Three-storey academic block with labs and an auditorium.",
	},
	{
		name: "Lakeview Hospital Wing",
		code: "PRJ-007",
		client: "Lakeview Healthcare",
		location: "Hyderabad",
		status: "Planning",
		start: "2027-01-15",
		end: "2028-04-30",
		manager: "Fatima Shaikh",
		description: "New 120-bed wing with operating theatres and ICU.",
	},
	{
		name: "Tech Park Phase 2",
		code: "PRJ-008",
		client: "Nexus Tech Parks",
		location: "Bengaluru",
		status: "Planning",
		start: "2027-03-01",
		end: "2028-09-30",
		manager: "Rahul Verma",
		description: "Two IT office blocks and a multi-level car park.",
	},
	{
		name: "Highway Toll Plaza",
		code: "PRJ-009",
		client: "National Highways Authority",
		location: "Ahmedabad",
		status: "Completed",
		start: "2025-04-10",
		end: "2026-05-20",
		manager: "Vikram Desai",
		description: "Eight-lane toll plaza with control room and staff quarters.",
	},
	{
		name: "Coastal Resort",
		code: "PRJ-010",
		client: "Blue Bay Hospitality",
		location: "Goa",
		status: "On Hold",
		start: "2026-02-01",
		end: "2027-08-31",
		manager: "Priya Nair",
		description: "60-room beach resort with spa and conference centre.",
	},
];

const PROJECT_STATUSES = ["Planning", "In Progress", "On Hold", "Completed"];

frappe.pages["construction-projects"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Projects"),
		single_column: true,
	});

	page.set_primary_action(__("New Project"), show_create_placeholder, "add");
	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	new ProjectList(page, SAMPLE_PROJECTS);
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
			options: ["", ...PROJECT_STATUSES],
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
			const project = this.projects.find((p) => p.code === $(e.currentTarget).attr("data-code"));
			show_project_details(project);
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
			<td>${status_pill(project.status)}</td>
			<td class="cm-projects-nowrap">${frappe.datetime.str_to_user(project.start)}</td>
			<td class="cm-projects-nowrap">${frappe.datetime.str_to_user(project.end)}</td>
			<td class="cm-projects-open">${frappe.utils.icon("right", "sm")}</td>
		</tr>
	`;
}

function status_pill(status) {
	const css_class = status.toLowerCase().replace(/\s+/g, "-");
	return `<span class="cm-status cm-status-${css_class}">${__(status)}</span>`;
}

function show_project_details(project) {
	const esc = frappe.utils.escape_html;
	const fields = [
		[__("Project Code"), esc(project.code)],
		[__("Client"), esc(project.client)],
		[__("Location"), esc(project.location)],
		[__("Status"), status_pill(project.status)],
		[__("Project Manager"), esc(project.manager)],
		[__("Start Date"), frappe.datetime.str_to_user(project.start)],
		[__("End Date"), frappe.datetime.str_to_user(project.end)],
	];

	const dialog = new frappe.ui.Dialog({
		title: project.name,
		fields: [{ fieldtype: "HTML", fieldname: "details" }],
	});

	dialog.fields_dict.details.$wrapper.html(`
		<div class="cm-project-details">
			${fields
				.map(
					([label, value]) => `
				<div class="cm-project-detail">
					<div class="cm-project-detail-label">${label}</div>
					<div class="cm-project-detail-value">${value}</div>
				</div>`
				)
				.join("")}
			<div class="cm-project-detail cm-project-detail-full">
				<div class="cm-project-detail-label">${__("Description")}</div>
				<div class="cm-project-detail-value">${esc(project.description)}</div>
			</div>
		</div>
	`);
	dialog.show();
}

function show_create_placeholder() {
	frappe.msgprint({
		title: __("New Project"),
		message: __("Project creation will be available in a later release."),
		indicator: "blue",
	});
}
