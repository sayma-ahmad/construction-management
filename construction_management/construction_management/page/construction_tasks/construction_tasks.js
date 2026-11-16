const CM_TASK_ASSETS = [
	"/assets/construction_management/js/sample_projects.js",
	"/assets/construction_management/js/project_tasks.js",
	"/assets/construction_management/css/construction_management.css",
];

frappe.pages["construction-tasks"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Project Tasks"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	const $container = $(`<div class="cm-tasks-page"></div>`).appendTo(page.main);
	wrapper.task_list_ready = frappe.require(CM_TASK_ASSETS).then(() => {
		page.set_primary_action(__("New Task"), construction_management.show_task_create_placeholder, "add");
		wrapper.task_list = new construction_management.TaskList({
			parent: $container,
			tasks: construction_management.SAMPLE_TASKS,
		});
	});
};

// /app/construction-tasks/PRJ-001 opens the list filtered to that project.
frappe.pages["construction-tasks"].on_page_show = function (wrapper) {
	wrapper.task_list_ready.then(() => wrapper.task_list.set_project(frappe.get_route()[1] || ""));
};
