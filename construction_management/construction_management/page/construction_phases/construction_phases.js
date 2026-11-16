const CM_PHASE_ASSETS = [
	"/assets/construction_management/js/sample_projects.js",
	"/assets/construction_management/js/project_tasks.js",
	"/assets/construction_management/js/project_phases.js",
	"/assets/construction_management/css/construction_management.css",
];

frappe.pages["construction-phases"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Project Phases"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	const $container = $(`<div class="cm-phases-page"></div>`).appendTo(page.main);
	wrapper.phase_list_ready = frappe.require(CM_PHASE_ASSETS).then(() => {
		page.set_primary_action(__("New Phase"), construction_management.show_phase_create_placeholder, "add");
		wrapper.phase_list = new construction_management.PhaseList({
			parent: $container,
			phases: construction_management.get_all_phases(),
		});
	});
};

// /app/construction-phases/PRJ-001 opens the list filtered to that project.
frappe.pages["construction-phases"].on_page_show = function (wrapper) {
	wrapper.phase_list_ready.then(() => wrapper.phase_list.set_project(frappe.get_route()[1] || ""));
};
