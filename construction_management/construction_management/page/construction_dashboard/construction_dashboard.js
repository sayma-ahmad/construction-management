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
	"On Hold": "orange",
};

frappe.pages["construction-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Construction Dashboard"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));
	page.set_primary_action(__("Refresh"), () => load_dashboard(page));
	if (frappe.user.has_role("System Manager")) {
		page.add_inner_button(__("Load Sample Data"), () => load_sample_data(page));
	}

	wrapper.page = page;
	load_dashboard(page);
};

frappe.pages["construction-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.page) {
		load_dashboard(wrapper.page);
	}
};

function load_sample_data(page) {
	frappe.confirm(
		__("Load sample data for every page (projects, reports, tasks, issues, work orders, purchasing and stock)? Records that already exist are skipped."),
		() => {
			frappe.realtime.off("cm_sample_data_loaded");
			frappe.realtime.on("cm_sample_data_loaded", (data) => {
				frappe.realtime.off("cm_sample_data_loaded");
				if (data && data.ok) {
					frappe.show_alert({ message: __("Sample data loaded"), indicator: "green" }, 7);
					load_dashboard(page);
				} else {
					frappe.msgprint((data && data.message) || __("Loading sample data failed."));
					load_dashboard(page);
				}
			});
			frappe.call({
				method: "construction_management.demo_data.load_sample_data",
				callback: () => {
					frappe.show_alert(
						{
							message: __("Loading sample data in the background. This takes a few minutes; you will be notified when it is done."),
							indicator: "blue",
						},
						10
					);
				},
			});
		}
	);
}

function load_dashboard(page) {
	if (page._is_loading) return;
	page._is_loading = true;

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
			page._is_loading = false;
			$loading.remove();
			if (r.message) {
				render_dashboard(page.main, r.message);
			} else {
				$(page.main).html(`<div class="text-center p-5 text-muted">${__("No dashboard data returned.")}</div>`);
			}
		},
		error: () => {
			page._is_loading = false;
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
					${section_header(__("Project Completion"), __("Historical progress from submitted Daily Progress Reports"))}
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
					${section_header(__("Expense Flow"), __("Monthly project expenditure and financial outflow"))}
					<div class="cm-expense-chart"></div>
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

	// KPI card click handler with permission verification
	$dashboard.find(".cm-kpi-grid").on("click", ".cm-kpi", function () {
		const route = $(this).attr("data-route");
		const doctype = $(this).attr("data-doctype");
		if (doctype && !frappe.model.can_read(doctype)) {
			frappe.msgprint(__("Not permitted to view {0}", [doctype]));
			return;
		}
		if (route) {
			frappe.set_route(route.split("/"));
		} else if (doctype) {
			frappe.set_route("List", doctype);
		}
	});

	// Project row click handler
	$dashboard.find(".cm-project-list").on("click", "tr[data-project]", function () {
		const proj = $(this).attr("data-project");
		if (proj && frappe.model.can_read("Project")) {
			frappe.set_route("Form", "Project", proj);
		}
	});

	// Activity row click handler
	$dashboard.find(".cm-activity-list").on("click", ".cm-activity-clickable", function () {
		const dt = $(this).attr("data-doctype");
		const dn = $(this).attr("data-docname");
		if (dt && dn && frappe.model.can_read(dt)) {
			frappe.set_route("Form", dt, dn);
		}
	});

	// 1. Completion Chart (only render if actual data exists, else show clean empty state)
	if (data.completion && data.completion.labels && data.completion.labels.length && data.completion.actual && data.completion.actual.some((v) => v > 0)) {
		new frappe.Chart($dashboard.find(".cm-completion-chart")[0], {
			type: "line",
			height: 260,
			colors: [COLORS.accent],
			data: {
				labels: data.completion.labels,
				datasets: [
					{ name: __("Actual Progress (%)"), values: data.completion.actual },
				],
			},
			axisOptions: { xIsSeries: 1 },
			lineOptions: { regionFill: 1, dotSize: 4 },
			tooltipOptions: { formatTooltipY: (value) => `${value}%` },
		});
	} else {
		$dashboard.find(".cm-completion-chart").html(`
			<div class="text-center text-muted p-5">
				<div>${__("No historical project progress recorded in Daily Progress Reports yet.")}</div>
			</div>
		`);
	}

	// 2. Task Status Donut Chart (mutually exclusive)
	const taskValues = (data.task_status && data.task_status.values) || [0, 0, 0, 0];
	const hasTasks = taskValues.some((v) => v > 0);
	if (hasTasks) {
		new frappe.Chart($dashboard.find(".cm-task-chart")[0], {
			type: "donut",
			height: 260,
			colors: [COLORS.success, COLORS.accent, COLORS.mid_gray, COLORS.danger],
			data: {
				labels: data.task_status.labels.map((label) => __(label)),
				datasets: [{ values: taskValues }],
			},
		});
	} else {
		$dashboard.find(".cm-task-chart").html(`
			<div class="text-center text-muted p-5">
				<div>${__("No tasks found across projects.")}</div>
			</div>
		`);
	}

	// 3. Inventory Bar Chart (without synthetic fallback materials)
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
	} else {
		$dashboard.find(".cm-inventory-chart").html(`
			<div class="text-center text-muted p-5">
				<div>${__("No stock items found in warehouse inventory.")}</div>
			</div>
		`);
	}

	// 4. Expense Flow Chart (US-03 / TC-06)
	const fin = (data.metrics && data.metrics.financial) || {};
	const expenseData = data.expense_flow || fin.expense_flow;
	const hasExpense = expenseData && expenseData.values && expenseData.values.some((v) => v > 0);
	const expenseCurrency = (expenseData && expenseData.currency) || fin.currency || (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency) || "INR";

	if (hasExpense) {
		new frappe.Chart($dashboard.find(".cm-expense-chart")[0], {
			type: "bar",
			height: 240,
			colors: [COLORS.accent],
			data: {
				labels: expenseData.labels,
				datasets: [
					{ name: __("Monthly Expenses"), values: expenseData.values },
				],
			},
			tooltipOptions: {
				formatTooltipY: (value) => format_currency(value, expenseCurrency, 0),
			},
		});
	} else if (fin.total_expenses && fin.total_expenses > 0) {
		$dashboard.find(".cm-expense-chart").html(`
			<div class="text-center p-4">
				<div class="text-muted mb-1">${__("Total Incurred Expenditure")}</div>
				<div class="h3 font-weight-bold text-dark">${format_currency(fin.total_expenses, expenseCurrency, 0)}</div>
				<div class="text-muted mt-2">${__("Outstanding Payables: {0}", [format_currency(fin.total_payables || 0, expenseCurrency, 0)])}</div>
			</div>
		`);
	} else {
		$dashboard.find(".cm-expense-chart").html(`
			<div class="text-center text-muted p-5">
				<div>${__("No expense records found across projects.")}</div>
			</div>
		`);
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

const FALLBACK_SVGS = {
	project: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>`,
	buying: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>`,
	tool: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>`,
	"list-alt": `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>`,
	stock: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`,
	"solid-warning": `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
	assets: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>`,
	expenses: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect><line x1="1" y1="10" x2="23" y2="10"></line></svg>`,
};

function kpi_card(kpi) {
	const defaultCurrency = (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency) || "INR";
	const formattedVal = kpi.is_currency
		? format_currency(kpi.value || 0, kpi.currency || defaultCurrency, 0)
		: format_number(kpi.value || 0, null, 0);

	const iconMap = {
		project: "project",
		order: "buying",
		buying: "buying",
		tool: "tool",
		"list-alt": "list-alt",
		list: "list-alt",
		stock: "stock",
		alert: "solid-warning",
		warning: "solid-warning",
		"solid-warning": "solid-warning",
		package: "assets",
		box: "assets",
		assets: "assets",
		"credit-card": "expenses",
		expenses: "expenses",
	};
	const iconKey = iconMap[kpi.icon] || kpi.icon || "project";
	let iconHtml = frappe.utils.icon(iconKey, "md");

	if (!iconHtml || !iconHtml.includes("<svg")) {
		iconHtml = FALLBACK_SVGS[iconKey] || FALLBACK_SVGS.project;
	}

	const isClickable = kpi.has_permission !== false && kpi.doctype && frappe.model.can_read(kpi.doctype);
	const clickableClass = isClickable ? "cm-kpi-clickable" : "";

	return `
		<div class="cm-card cm-kpi ${clickableClass}"
			data-route="${frappe.utils.escape_html(kpi.route || "")}"
			data-doctype="${frappe.utils.escape_html(kpi.doctype || "")}"
			title="${isClickable ? __("Click to view {0}", [__(kpi.label)]) : __(kpi.label)}">
			<div class="cm-kpi-icon">${iconHtml}</div>
			<div class="cm-kpi-content">
				<div class="cm-kpi-label">${__(kpi.label)}</div>
				<div class="cm-kpi-value">${formattedVal}</div>
				<div class="cm-kpi-note">${frappe.utils.escape_html(kpi.note || "")}</div>
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
			(project) => {
				const progressPct = Math.min(100, Math.max(0, flt(project.progress) || 0));
				const dueText = project.due ? frappe.datetime.str_to_user(project.due) : "—";
				const siteText = project.site ? frappe.utils.escape_html(project.site) : "—";
				return `
				<tr data-project="${frappe.utils.escape_html(project.id || project.name)}" title="${__("Open Project")}">
					<td>
						<div class="cm-project-name font-weight-bold">${frappe.utils.escape_html(project.name)}</div>
						<div class="cm-project-site text-muted">${siteText}</div>
					</td>
					<td class="cm-nowrap">${dueText}</td>
					<td class="cm-progress-cell">
						<div class="cm-progress">
							<div class="cm-progress-bar" style="width: ${progressPct}%"></div>
						</div>
						<span class="cm-progress-value">${progressPct}%</span>
					</td>
					<td>
						<span class="indicator-pill ${STATUS_INDICATOR[project.status] || "gray"}">${__(project.status)}</span>
					</td>
				</tr>`;
			}
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
	const canNavigate = item.doctype && item.docname && frappe.model.can_read(item.doctype);
	const clickableClass = canNavigate ? "cm-activity-clickable cursor-pointer" : "";
	return `
		<div class="cm-activity ${clickableClass}"
			data-doctype="${frappe.utils.escape_html(item.doctype || "")}"
			data-docname="${frappe.utils.escape_html(item.docname || "")}"
			title="${canNavigate ? __("Open {0}", [item.docname]) : ""}">
			<span class="indicator gray"></span>
			<span class="cm-activity-text">${frappe.utils.escape_html(item.text)}</span>
			<span class="cm-activity-time">${frappe.utils.escape_html(item.time)}</span>
		</div>
	`;
}
