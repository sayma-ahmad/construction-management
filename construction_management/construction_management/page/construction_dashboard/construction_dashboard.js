// Copyright (c) 2026, TechnoTribes and contributors
// See license.txt

const COLORS = {
	charcoal: "#383838",
	mid_gray: "#7c7c7c",
	light_gray: "#c7c7c7",
	accent: "#0070cc",
	success: "#28a745",
	warning: "#ffc107",
	danger: "#dc3545",
};

const STATUS_INDICATOR = {
	"On Track": "blue",
	"At Risk": "orange",
	"Delayed": "red",
	"Completed": "green",
};

frappe.pages["construction-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Construction Dashboard"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));
	page.set_primary_action(__("Refresh"), () => load_dashboard(page));

	load_dashboard(page);
};

function load_dashboard(page) {
	$(page.main).empty();
	const $loading = $(`
		<div class="text-center p-5 text-muted">
			<div class="spinner-border spinner-border-sm text-primary mb-2" role="status"></div>
			<div>${__("Loading construction dashboard data...")}</div>
		</div>
	`).appendTo(page.main);

	frappe.call({
		method: "construction_management.dashboard.get_dashboard_data",
		callback: (r) => {
			$loading.remove();
			if (r.message) {
				render_dashboard(page.main, r.message);
			} else {
				$(page.main).html(`<div class="text-center p-5 text-muted">${__("No dashboard data returned.")}</div>`);
			}
		},
		error: () => {
			$loading.remove();
			$(page.main).html(`<div class="text-center p-5 text-danger">${__("Failed to load dashboard data.")}</div>`);
		},
	});
}

function render_dashboard(container, data) {
	const $dashboard = $(`
		<div class="cm-dashboard">
			<div class="cm-kpi-grid"></div>
			<div class="cm-row">
				<div class="cm-card cm-span-8">
					${section_header(__("Project Completion"), __("Planned vs actual progress across sites"))}
					<div class="cm-completion-chart"></div>
				</div>
				<div class="cm-card cm-span-4">
					${section_header(__("Task Status"), __("Tasks distribution across all projects"))}
					<div class="cm-task-chart"></div>
				</div>
			</div>
			<div class="cm-row">
				<div class="cm-card cm-span-7">
					${section_header(__("Project Progress"), __("Active construction projects"))}
					<div class="cm-project-list"></div>
				</div>
				<div class="cm-card cm-span-5">
					${section_header(__("Inventory Levels"), __("Stock vs reorder level for key materials"))}
					<div class="cm-inventory-chart"></div>
				</div>
			</div>
			<div class="cm-row">
				<div class="cm-card cm-span-12">
					${section_header(__("Recent Site Activity"), __("Latest updates across site reports and operations"))}
					<div class="cm-activity-list"></div>
				</div>
			</div>
		</div>
	`).appendTo(container);

	// Populate KPI grid, project table, and activity feed
	$dashboard.find(".cm-kpi-grid").html((data.kpis || []).map(kpi_card).join(""));
	$dashboard.find(".cm-project-list").html(project_table(data.projects || []));
	$dashboard.find(".cm-activity-list").html((data.activity || []).map(activity_item).join(""));

	// KPI card click handler to open underlying object / list
	$dashboard.find(".cm-kpi-grid").on("click", ".cm-kpi-clickable", function () {
		const route = $(this).attr("data-route");
		const doctype = $(this).attr("data-doctype");
		if (route) {
			frappe.set_route(route.split("/"));
		} else if (doctype) {
			frappe.set_route("List", doctype);
		}
	});

	// Project row click handler
	$dashboard.find(".cm-project-list").on("click", "tr[data-project]", function () {
		const proj = $(this).attr("data-project");
		if (proj) frappe.set_route("Form", "Project", proj);
	});

	// Render Charts
	if (data.completion && data.completion.labels && data.completion.labels.length) {
		new frappe.Chart($dashboard.find(".cm-completion-chart")[0], {
			type: "line",
			height: 260,
			colors: [COLORS.light_gray, COLORS.accent],
			data: {
				labels: data.completion.labels,
				datasets: [
					{ name: __("Planned"), values: data.completion.planned },
					{ name: __("Actual"), values: data.completion.actual },
				],
			},
			axisOptions: { xIsSeries: 1 },
			lineOptions: { regionFill: 1, dotSize: 4 },
			tooltipOptions: { formatTooltipY: (value) => `${value}%` },
		});
	}

	if (data.task_status && data.task_status.labels && data.task_status.labels.length) {
		new frappe.Chart($dashboard.find(".cm-task-chart")[0], {
			type: "donut",
			height: 260,
			colors: [COLORS.success, COLORS.accent, COLORS.mid_gray, COLORS.danger],
			data: {
				labels: data.task_status.labels.map((label) => __(label)),
				datasets: [{ values: data.task_status.values }],
			},
		});
	}

	if (data.inventory && data.inventory.labels && data.inventory.labels.length) {
		new frappe.Chart($dashboard.find(".cm-inventory-chart")[0], {
			type: "bar",
			height: 260,
			colors: [COLORS.charcoal, COLORS.light_gray],
			data: {
				labels: data.inventory.labels,
				datasets: [
					{ name: __("In Stock"), values: data.inventory.in_stock },
					{ name: __("Reorder Level"), values: data.inventory.reorder_level },
				],
			},
			barOptions: { spaceRatio: 0.4 },
		});
	}
}

function section_header(title, subtitle) {
	return `
		<div class="cm-card-header">
			<div class="cm-card-title">${title}</div>
			<div class="cm-card-subtitle">${subtitle}</div>
		</div>
	`;
}

function kpi_card(kpi) {
	const formattedVal = kpi.is_currency
		? format_currency(kpi.value || 0, kpi.currency || "INR", 0)
		: format_number(kpi.value || 0, null, 0);

	// Ensure every KPI has an icon with robust fallbacks
	const iconMap = {
		project: "project",
		order: "order",
		tool: "tool",
		"list-alt": "list",
		stock: "stock",
		alert: "alert",
		package: "box",
		box: "box",
		"credit-card": "credit-card",
	};
	const iconName = iconMap[kpi.icon] || kpi.icon || "folder";
	const iconHtml = frappe.utils.icon(iconName, "md") || frappe.utils.icon("folder", "md") || "📊";

	return `
		<div class="cm-card cm-kpi cm-kpi-clickable"
			data-route="${frappe.utils.escape_html(kpi.route || "")}"
			data-doctype="${frappe.utils.escape_html(kpi.doctype || "")}"
			title="${__("Click to view {0}", [__(kpi.label)])}">
			<div class="cm-kpi-icon">${iconHtml}</div>
			<div class="cm-kpi-content">
				<div class="cm-kpi-label">${__(kpi.label)}</div>
				<div class="cm-kpi-value">${formattedVal}</div>
				<div class="cm-kpi-note">${__(kpi.note)}</div>
			</div>
		</div>
	`;
}

function project_table(projects) {
	if (!projects || !projects.length) {
		return `
			<div class="text-center text-muted p-4">
				${__("No active construction projects found.")}
			</div>
		`;
	}

	const rows = projects
		.map(
			(project) => `
			<tr data-project="${frappe.utils.escape_html(project.id || project.name)}" title="${__("Open Project")}">
				<td>
					<div class="cm-project-name font-weight-bold">${frappe.utils.escape_html(project.name)}</div>
					<div class="cm-project-site text-muted">${frappe.utils.escape_html(project.site)}</div>
				</td>
				<td class="cm-nowrap">${frappe.datetime.str_to_user(project.due)}</td>
				<td class="cm-progress-cell">
					<div class="cm-progress">
						<div class="cm-progress-bar" style="width: ${project.progress}%"></div>
					</div>
					<span class="cm-progress-value">${project.progress}%</span>
				</td>
				<td>
					<span class="indicator-pill ${STATUS_INDICATOR[project.status] || "gray"}">${__(project.status)}</span>
				</td>
			</tr>`
		)
		.join("");

	return `
		<div class="cm-table-wrapper">
			<table class="cm-table">
				<thead>
					<tr>
						<th>${__("Project")}</th>
						<th>${__("Due Date")}</th>
						<th>${__("Progress")}</th>
						<th>${__("Status")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
	`;
}

function activity_item(item) {
	return `
		<div class="cm-activity">
			<span class="indicator gray"></span>
			<span class="cm-activity-text">${frappe.utils.escape_html(item.text)}</span>
			<span class="cm-activity-time">${frappe.utils.escape_html(item.time)}</span>
		</div>
	`;
}
