const CM_WO_PAGE_ASSETS = ["/assets/construction_management/css/construction_management.css"];
const CM_WO_LIST_METHOD =
	"construction_management.construction_management.doctype.construction_work_order.construction_work_order.get_work_order_list";
const CM_WO_CONTRACTOR_QUERY =
	"construction_management.construction_management.doctype.construction_work_order.construction_work_order.get_contractor_options";
const CM_WO_PRIORITIES = ["Low", "Medium", "High", "Urgent"];
const CM_WO_PAGE_LENGTH = 20;

frappe.pages["construction-work-orders"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Work Orders"),
		single_column: true,
	});

	page.set_primary_action(
		__("New Work Order"),
		() => frappe.new_doc("Construction Work Order"),
		"add"
	);
	page.set_secondary_action(__("Refresh"), () => wrapper.work_order_list?.fetch());

	frappe.require(CM_WO_PAGE_ASSETS, () => {
		wrapper.work_order_list = new ConstructionWorkOrderList(page);
	});
};

frappe.pages["construction-work-orders"].on_page_show = function (wrapper) {
	if (wrapper.work_order_list) {
		wrapper.work_order_list.fetch();
	}
};

class ConstructionWorkOrderList {
	constructor(page) {
		this.page = page;
		this.start = 0;
		this.total = 0;
		this.make_filters();
		this.make_layout();
		this.fetch();
	}

	make_filters() {
		this.search = this.page.add_field({
			fieldname: "search",
			label: __("Search ID or Work Order Title"),
			fieldtype: "Data",
		});
		this.search.$input.on(
			"input",
			frappe.utils.debounce(() => {
				this.start = 0;
				this.fetch();
			}, 250)
		);
		$(this.search.wrapper).removeClass("col-md-2").addClass("col-md-3");

		this.project = this.page.add_field({
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.contractor = this.page.add_field({
			fieldname: "contractor",
			label: __("Contractor"),
			fieldtype: "Link",
			options: "Supplier",
			ignore_link_validation: 1,
			get_query: () => ({ query: CM_WO_CONTRACTOR_QUERY }),
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "In Progress", "On Hold", "Completed", "Cancelled"],
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.priority = this.page.add_field({
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: ["", ...CM_WO_PRIORITIES],
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-wo-page">
				<div class="cm-tasks-card">
					<div class="cm-tasks-toolbar">
						<span class="cm-tasks-count cm-wo-count"></span>
						<button class="btn btn-xs btn-default cm-wo-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-tasks-table-wrapper">
						<table class="cm-tasks-table cm-wo-table">
							<thead>
								<tr>
									<th>${__("Work Order ID")}</th>
									<th>${__("Title")}</th>
									<th>${__("Project")}</th>
									<th>${__("Contractor")}</th>
									<th>${__("Priority")}</th>
									<th>${__("Planned End")}</th>
									<th>${__("Status")}</th>
									<th></th>
								</tr>
							</thead>
							<tbody></tbody>
						</table>
					</div>
					<div class="cm-wo-pagination">
						<span class="cm-tasks-count cm-wo-page-info"></span>
						<div class="cm-wo-pagination-actions">
							<button class="btn btn-xs btn-default cm-wo-prev">${__("Previous")}</button>
							<button class="btn btn-xs btn-default cm-wo-next">${__("Next")}</button>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$wrapper.on("click", "tbody tr[data-name]", (e) => {
			const name = $(e.currentTarget).attr("data-name");
			frappe.set_route("Form", "Construction Work Order", name);
		});

		this.$wrapper.on("click", ".cm-wo-retry", () => this.fetch());

		this.$wrapper.find(".cm-wo-clear").on("click", () => {
			this.search.set_value("");
			this.project.set_value("");
			this.contractor.set_value("");
			this.status.set_value("");
			this.priority.set_value("");
			this.start = 0;
			this.fetch();
		});

		this.$wrapper.find(".cm-wo-prev").on("click", () => {
			if (this.start > 0) {
				this.start = Math.max(0, this.start - CM_WO_PAGE_LENGTH);
				this.fetch();
			}
		});

		this.$wrapper.find(".cm-wo-next").on("click", () => {
			if (this.start + CM_WO_PAGE_LENGTH < this.total) {
				this.start += CM_WO_PAGE_LENGTH;
				this.fetch();
			}
		});
	}

	get_filters() {
		return {
			project: this.project.get_value() || "",
			contractor: this.contractor.get_value() || "",
			status: this.status.get_value() || "",
			priority: this.priority.get_value() || "",
		};
	}

	fetch() {
		this.render_loading();
		frappe.call({
			method: CM_WO_LIST_METHOD,
			args: {
				filters: this.get_filters(),
				search: this.search.get_value() || "",
				start: this.start,
				page_length: CM_WO_PAGE_LENGTH,
			},
			callback: (r) => {
				const data = r.message || {};
				this.total = data.total || 0;
				this.render_records(data.records || []);
			},
			error: () => {
				this.render_error();
			},
		});
	}

	render_loading() {
		this.$wrapper.find(".cm-wo-count").text(__("Loading work orders..."));
		this.$wrapper
			.find("tbody")
			.html(`<tr><td colspan="8" class="cm-tasks-empty">${__("Loading Work Orders...")}</td></tr>`);
		this.update_pagination(0);
	}

	render_error() {
		this.$wrapper.find(".cm-wo-count").text(__("Unable to load work orders"));
		this.$wrapper.find("tbody").html(`
			<tr>
				<td colspan="8" class="cm-tasks-empty cm-wo-error">
					<div>${__("Failed to load Work Orders.")}</div>
					<div class="cm-wo-error-actions">
						<button class="btn btn-xs btn-default cm-wo-retry">${__("Retry")}</button>
					</div>
				</td>
			</tr>
		`);
		this.update_pagination(0);
	}

	render_records(records) {
		const esc = frappe.utils.escape_html;
		if (!records.length) {
			this.$wrapper.find(".cm-wo-count").text(__("0 work orders"));
			this.$wrapper.find("tbody").html(`
				<tr>
					<td colspan="8" class="cm-tasks-empty">
						${__("No Work Orders match the selected filters.")}
					</td>
				</tr>
			`);
			this.update_pagination(0);
			return;
		}

		const end = this.start + records.length;
		this.$wrapper
			.find(".cm-wo-count")
			.text(__("Showing {0}–{1} of {2} work orders", [this.start + 1, end, this.total]));

		const rows = records
			.map((row) => {
				const project_label = row.project_name || row.project || "";
				const contractor_label = row.contractor_name || row.contractor || "";
				const status = row.status || "Open";
				const status_class = status.toLowerCase().replace(/\s+/g, "-");
				const planned_end = row.planned_end_date
					? frappe.datetime.str_to_user(row.planned_end_date)
					: "";
				return `
					<tr data-name="${esc(row.name)}" title="${__("Open Work Order")}">
						<td class="cm-wo-id">${esc(row.name)}</td>
						<td class="cm-tasks-name">${esc(row.title || "")}</td>
						<td>${esc(project_label)}</td>
						<td>${esc(contractor_label)}</td>
						<td class="cm-tasks-nowrap">${render_priority_badge(row.priority || "Medium")}</td>
						<td class="cm-tasks-muted">${esc(planned_end)}</td>
						<td><span class="cm-status cm-status-${status_class}">${__(status)}</span></td>
						<td class="cm-tasks-open">${frappe.utils.icon("right", "sm")}</td>
					</tr>
				`;
			})
			.join("");

		this.$wrapper.find("tbody").html(rows);
		this.update_pagination(records.length);
	}

	update_pagination(count) {
		const has_prev = this.start > 0;
		const has_next = this.start + count < this.total;
		this.$wrapper.find(".cm-wo-prev").prop("disabled", !has_prev);
		this.$wrapper.find(".cm-wo-next").prop("disabled", !has_next);

		const page_num = Math.floor(this.start / CM_WO_PAGE_LENGTH) + 1;
		const total_pages = Math.max(1, Math.ceil(this.total / CM_WO_PAGE_LENGTH));
		this.$wrapper
			.find(".cm-wo-page-info")
			.text(this.total ? __("Page {0} of {1}", [page_num, total_pages]) : "");
	}
}

function render_priority_badge(priority) {
	const level = CM_WO_PRIORITIES.indexOf(priority) + 1;
	const bars = CM_WO_PRIORITIES.map(
		(_, index) => `<span class="cm-priority-bar${index < level ? " filled" : ""}"></span>`
	).join("");
	const css_class = (priority || "Medium").toLowerCase();
	return `<span class="cm-priority cm-priority-${css_class}"><span class="cm-priority-bars">${bars}</span>${__(priority)}</span>`;
}
