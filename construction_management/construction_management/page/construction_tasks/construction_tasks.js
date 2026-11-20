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
		wrapper.task_list = new construction_management.TaskList({
			parent: $container,
			loader: () => construction_management.load_tasks().then((data) => data.tasks),
		});
		if (frappe.model.can_create("Task")) {
			page.set_primary_action(__("New Task"), () => wrapper.task_list.create_task(), "add");
		}
	});
};

// /app/construction-tasks/PRJ-001 opens the list filtered to that project.
frappe.pages["construction-tasks"].on_page_show = function (wrapper) {
	wrapper.task_list_ready.then(() => {
		if (wrapper.task_list_shown) {
			wrapper.task_list.reload().then(() => wrapper.task_list.set_project(frappe.get_route()[1] || ""));
		} else {
			wrapper.task_list_shown = true;
			wrapper.task_list.set_project(frappe.get_route()[1] || "");
		}
	});
};
