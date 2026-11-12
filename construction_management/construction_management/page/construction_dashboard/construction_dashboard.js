// Sample data only. Real values will come from project, task and stock records in a later story.
const SAMPLE_DATA = {
	kpis: [
		{ label: "Total Projects", value: 24, note: "Across all sites", icon: "project" },
		{ label: "Active Projects", value: 14, note: "Currently in execution", icon: "tool" },
		{ label: "Completed Projects", value: 8, note: "Handed over this year", icon: "tick" },
		{ label: "Pending Tasks", value: 57, note: "12 overdue", icon: "list-alt" },
	],
	completion: {
		labels: ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"],
		planned: [20, 32, 45, 58, 70, 82],
		actual: [18, 29, 40, 51, 64, 74],
	},
	task_status: {
		labels: ["Completed", "In Progress", "Open", "Overdue"],
		values: [112, 38, 45, 12],
	},
	projects: [
		{ name: "Riverside Apartments", site: "Block A, North Site", due: "2027-02-15", progress: 78, status: "On Track" },
		{ name: "Metro Office Tower", site: "Downtown Plot 7", due: "2027-06-30", progress: 54, status: "On Track" },
		{ name: "Green Valley Villas", site: "Green Valley Phase 2", due: "2027-01-20", progress: 32, status: "Delayed" },
		{ name: "City Mall Renovation", site: "City Centre", due: "2026-12-10", progress: 91, status: "On Track" },
		{ name: "Harbor Bridge Repair", site: "East Harbor", due: "2027-03-05", progress: 45, status: "At Risk" },
	],
	inventory: {
		labels: ["Cement (bags)", "Steel Rebar (t)", "Bricks (x1000)", "Sand (m³)", "Paint (L)"],
		in_stock: [420, 18, 65, 120, 90],
		reorder_level: [300, 25, 40, 80, 120],
	},
	activity: [
		{ text: "Daily progress report submitted for Riverside Apartments", time: "10 minutes ago" },
		{ text: "Site issue raised: water seepage at Green Valley Villas", time: "1 hour ago" },
		{ text: "Goods received: 200 bags of cement at Metro Office Tower", time: "3 hours ago" },
		{ text: "Material request created for steel rebar (12 t)", time: "Yesterday" },
		{ text: "Purchase order approved for electrical fittings", time: "Yesterday" },
	],
};

const COLORS = { charcoal: "#383838", mid_gray: "#7c7c7c", light_gray: "#c7c7c7", accent: "#0070cc" };
const STATUS_INDICATOR = { "On Track": "blue", "At Risk": "gray", Delayed: "gray" };

frappe.pages["construction-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Construction Dashboard"),
		single_column: true,
	});
	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	render_dashboard(page.main, SAMPLE_DATA);
};

function render_dashboard(container, data) {
	const $dashboard = $(`
		<div class="cm-dashboard">
			<div class="cm-kpi-grid"></div>
			<div class="cm-row">
				<div class="cm-card cm-span-8">
					${section_header(__("Project Completion"), __("Planned vs actual, % complete"))}
					<div class="cm-completion-chart"></div>
				</div>
				<div class="cm-card cm-span-4">
					${section_header(__("Task Status"), __("All open projects"))}
					<div class="cm-task-chart"></div>
				</div>
			</div>
			<div class="cm-row">
				<div class="cm-card cm-span-7">
					${section_header(__("Project Progress"), __("Active projects"))}
					<div class="cm-project-list"></div>
				</div>
				<div class="cm-card cm-span-5">
					${section_header(__("Inventory Levels"), __("Stock vs reorder level"))}
					<div class="cm-inventory-chart"></div>
				</div>
			</div>
			<div class="cm-row">
				<div class="cm-card cm-span-12">
					${section_header(__("Recent Site Activity"), __("Latest updates across sites"))}
					<div class="cm-activity-list"></div>
				</div>
			</div>
		</div>
	`).appendTo(container);

	$dashboard.find(".cm-kpi-grid").html(data.kpis.map(kpi_card).join(""));
	$dashboard.find(".cm-project-list").html(project_table(data.projects));
	$dashboard.find(".cm-activity-list").html(data.activity.map(activity_item).join(""));

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

	new frappe.Chart($dashboard.find(".cm-task-chart")[0], {
		type: "donut",
		height: 260,
		colors: [COLORS.charcoal, COLORS.accent, COLORS.mid_gray, COLORS.light_gray],
		data: {
			labels: data.task_status.labels.map((label) => __(label)),
			datasets: [{ values: data.task_status.values }],
		},
	});

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

function section_header(title, subtitle) {
	return `
		<div class="cm-card-header">
			<div class="cm-card-title">${title}</div>
			<div class="cm-card-subtitle">${subtitle}</div>
		</div>
	`;
}

function kpi_card(kpi) {
	return `
		<div class="cm-card cm-kpi">
			<div class="cm-kpi-icon">${frappe.utils.icon(kpi.icon, "md")}</div>
			<div>
				<div class="cm-kpi-label">${__(kpi.label)}</div>
				<div class="cm-kpi-value">${format_number(kpi.value, null, 0)}</div>
				<div class="cm-kpi-note">${__(kpi.note)}</div>
			</div>
		</div>
	`;
}

function project_table(projects) {
	const rows = projects
		.map(
			(project) => `
			<tr>
				<td>
					<div class="cm-project-name">${project.name}</div>
					<div class="cm-project-site">${project.site}</div>
				</td>
				<td class="cm-nowrap">${frappe.datetime.str_to_user(project.due)}</td>
				<td class="cm-progress-cell">
					<div class="cm-progress">
						<div class="cm-progress-bar" style="width: ${project.progress}%"></div>
					</div>
					<span class="cm-progress-value">${project.progress}%</span>
				</td>
				<td>
					<span class="indicator-pill ${STATUS_INDICATOR[project.status]}">${__(project.status)}</span>
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
			<span class="cm-activity-text">${__(item.text)}</span>
			<span class="cm-activity-time">${__(item.time)}</span>
		</div>
	`;
}
