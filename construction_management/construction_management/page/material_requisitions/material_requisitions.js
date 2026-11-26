const CM_MR_PAGE_ASSETS = ["/assets/construction_management/css/construction_management.css"];
const CM_MR_LIST_METHOD =
	"construction_management.construction_management.material_request.get_material_requisition_list";
const CM_MR_PAGE_LENGTH = 20;

frappe.pages["material-requisitions"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Material Requisitions"),
		single_column: true,
	});

	sync_mr_primary_action(page);
	page.set_secondary_action(__("Refresh"), () => wrapper.mr_list?.fetch());
	page.add_inner_button(__("Workspace"), () => frappe.set_route("construction-management"));

	frappe.require(CM_MR_PAGE_ASSETS, () => {
		wrapper.mr_list = new MaterialRequisitionList(page);
	});
};

frappe.pages["material-requisitions"].on_page_show = function (wrapper) {
	if (wrapper.mr_list) {
		sync_mr_primary_action(wrapper.mr_list.page);
		wrapper.mr_list.fetch();
	}
};

function sync_mr_primary_action(page) {
	if (frappe.model.can_create("Material Request")) {
		page.set_primary_action(
			__("New Material Request"),
			() => frappe.new_doc("Material Request"),
			"add"
		);
	} else {
		page.clear_primary_action();
	}
}

class MaterialRequisitionList {
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
			label: __("Search ID, Project or Site Location"),
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

		this.material_request_type = this.page.add_field({
			fieldname: "material_request_type",
			label: __("Request Type"),
			fieldtype: "Select",
			options: ["", "Purchase", "Material Transfer", "Material Issue", "Manufacture", "Customer Provided"],
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Draft",
				"Submitted",
				"Pending",
				"Partially Ordered",
				"Partially Received",
				"Ordered",
				"Issued",
				"Transferred",
				"Received",
				"Stopped",
				"Cancelled",
			],
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.priority = this.page.add_field({
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: ["", "Low", "Medium", "High", "Urgent"],
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.from_date = this.page.add_field({
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.to_date = this.page.add_field({
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-mr-page">
				<div class="cm-mr-card">
					<div class="cm-mr-toolbar">
						<span class="cm-mr-count"></span>
						<button class="btn btn-xs btn-default cm-mr-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-mr-table-wrapper">
						<table class="cm-mr-table">
							<thead>
								<tr>
									<th>${__("Material Request ID")}</th>
									<th>${__("Project")}</th>
									<th>${__("Request Type")}</th>
									<th>${__("Transaction Date")}</th>
									<th>${__("Schedule Date")}</th>
									<th>${__("Priority")}</th>
									<th>${__("Status")}</th>
									<th>${__("% Ordered")}</th>
									<th>${__("% Received")}</th>
									<th></th>
								</tr>
							</thead>
							<tbody></tbody>
						</table>
					</div>
					<div class="cm-mr-pagination">
						<span class="cm-mr-count cm-mr-page-info"></span>
						<div class="cm-mr-pagination-actions">
							<button class="btn btn-xs btn-default cm-mr-prev">${__("Previous")}</button>
							<button class="btn btn-xs btn-default cm-mr-next">${__("Next")}</button>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$wrapper.on("click", "tbody tr[data-name]", (e) => {
			const name = $(e.currentTarget).attr("data-name");
			frappe.set_route("Form", "Material Request", name);
		});

		this.$wrapper.find(".cm-mr-clear").on("click", () => {
			this.search.set_value("");
			this.project.set_value("");
			this.material_request_type.set_value("");
			this.status.set_value("");
			this.priority.set_value("");
			this.from_date.set_value("");
			this.to_date.set_value("");
			this.start = 0;
			this.fetch();
		});

		this.$wrapper.find(".cm-mr-prev").on("click", () => {
			if (this.start > 0) {
				this.start = Math.max(0, this.start - CM_MR_PAGE_LENGTH);
				this.fetch();
			}
		});

		this.$wrapper.find(".cm-mr-next").on("click", () => {
			if (this.start + CM_MR_PAGE_LENGTH < this.total) {
				this.start += CM_MR_PAGE_LENGTH;
				this.fetch();
			}
		});
	}

	get_filters() {
		return {
			project: this.project.get_value() || "",
			material_request_type: this.material_request_type.get_value() || "",
			status: this.status.get_value() || "",
			priority: this.priority.get_value() || "",
			from_date: this.from_date.get_value() || "",
			to_date: this.to_date.get_value() || "",
		};
	}

	fetch() {
		this.render_loading();
		frappe.call({
			method: CM_MR_LIST_METHOD,
			args: {
				filters: this.get_filters(),
				search: this.search.get_value() || "",
				start: this.start,
				page_length: CM_MR_PAGE_LENGTH,
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
		this.$wrapper.find(".cm-mr-count").first().text(__("Loading material requisitions..."));
		this.$wrapper
			.find("tbody")
			.html(`<tr><td colspan="10" class="cm-mr-state">${__("Loading Material Requisitions...")}</td></tr>`);
		this.update_pagination(0);
	}

	render_error() {
		this.$wrapper.find(".cm-mr-count").first().text(__("Unable to load material requisitions"));
		this.$wrapper.find("tbody").html(`
			<tr>
				<td colspan="10" class="cm-mr-state cm-mr-state-error">
					<div>${__("Failed to load Material Requisitions.")}</div>
					<div class="cm-mr-state-actions">
						<button class="btn btn-xs btn-default cm-mr-retry">${__("Retry")}</button>
					</div>
				</td>
			</tr>
		`);
		this.$wrapper.find(".cm-mr-retry").on("click", () => this.fetch());
		this.update_pagination(0);
	}

	render_records(records) {
		const esc = frappe.utils.escape_html;
		if (!records.length) {
			this.$wrapper.find(".cm-mr-count").first().text(__("0 requisitions"));
			this.$wrapper.find("tbody").html(`
				<tr>
					<td colspan="10" class="cm-mr-state">
						${__("No Material Requisitions match the selected filters.")}
					</td>
				</tr>
			`);
			this.update_pagination(0);
			return;
		}

		const end = this.start + records.length;
		this.$wrapper
			.find(".cm-mr-count")
			.first()
			.text(__("Showing {0}–{1} of {2} requisitions", [this.start + 1, end, this.total]));

		const rows = records
			.map((row) => {
				const project_label = row.project || row.cm_project || "";
				const status = row.status || "Draft";
				const status_class = status.toLowerCase().replace(/\s+/g, "-");
				const tx_date = row.transaction_date ? frappe.datetime.str_to_user(row.transaction_date) : "";
				const sched_date = row.schedule_date ? frappe.datetime.str_to_user(row.schedule_date) : "";
				const per_ordered = flt(row.per_ordered || 0);
				const per_received = flt(row.per_received || 0);

				return `
					<tr data-name="${esc(row.name)}" title="${__("Open Material Request")}">
						<td class="cm-mr-id">${esc(row.name)}</td>
						<td>${esc(project_label)}</td>
						<td class="cm-mr-nowrap">${esc(row.material_request_type || "")}</td>
						<td class="cm-mr-nowrap">${esc(tx_date)}</td>
						<td class="cm-mr-nowrap">${esc(sched_date)}</td>
						<td>${esc(row.custom_priority || "")}</td>
						<td><span class="cm-status cm-status-${status_class}">${__(status)}</span></td>
						<td class="cm-mr-nowrap">${per_ordered}%</td>
						<td class="cm-mr-nowrap">${per_received}%</td>
						<td class="cm-mr-open">${frappe.utils.icon("right", "sm")}</td>
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
		this.$wrapper.find(".cm-mr-prev").prop("disabled", !has_prev);
		this.$wrapper.find(".cm-mr-next").prop("disabled", !has_next);

		const page_num = Math.floor(this.start / CM_MR_PAGE_LENGTH) + 1;
		const total_pages = Math.max(1, Math.ceil(this.total / CM_MR_PAGE_LENGTH));
		this.$wrapper
			.find(".cm-mr-page-info")
			.text(this.total ? __("Page {0} of {1}", [page_num, total_pages]) : "");
	}
}
