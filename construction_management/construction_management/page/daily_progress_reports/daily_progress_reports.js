const CM_DPR_PAGE_ASSETS = ["/assets/construction_management/css/construction_management.css"];
const CM_DPR_LIST_METHOD =
	"construction_management.construction_management.doctype.daily_progress_report.daily_progress_report.get_dpr_list";
const CM_DPR_PAGE_LENGTH = 20;

frappe.pages["daily-progress-reports"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Daily Progress Reports"),
		single_column: true,
	});

	page.set_primary_action(__("New DPR"), () => frappe.new_doc("Daily Progress Report"), "add");
	page.set_secondary_action(__("Refresh"), () => wrapper.dpr_list?.fetch());

	frappe.require(CM_DPR_PAGE_ASSETS, () => {
		wrapper.dpr_list = new DailyProgressReportList(page);
	});
};

frappe.pages["daily-progress-reports"].on_page_show = function (wrapper) {
	if (wrapper.dpr_list) {
		wrapper.dpr_list.fetch();
	}
};

class DailyProgressReportList {
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
			label: __("Search DPR ID, Project or Engineer"),
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

		this.review_status = this.page.add_field({
			fieldname: "review_status",
			label: __("Review Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Pending Review", "Approved", "Revision Requested", "Cancelled"],
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-dpr-page">
				<div class="cm-dpr-card">
					<div class="cm-dpr-toolbar">
						<span class="cm-dpr-count"></span>
						<button class="btn btn-xs btn-default cm-dpr-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-dpr-table-wrapper">
						<table class="cm-dpr-table">
							<thead>
								<tr>
									<th>${__("DPR ID")}</th>
									<th>${__("Project")}</th>
									<th>${__("Report Date")}</th>
									<th>${__("Site Engineer")}</th>
									<th>${__("Overall Progress")}</th>
									<th>${__("Review Status")}</th>
									<th></th>
								</tr>
							</thead>
							<tbody></tbody>
						</table>
					</div>
					<div class="cm-dpr-pagination">
						<span class="cm-dpr-count cm-dpr-page-info"></span>
						<div class="cm-dpr-pagination-actions">
							<button class="btn btn-xs btn-default cm-dpr-prev">${__("Previous")}</button>
							<button class="btn btn-xs btn-default cm-dpr-next">${__("Next")}</button>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$wrapper.on("click", "tbody tr[data-name]", (e) => {
			const name = $(e.currentTarget).attr("data-name");
			frappe.set_route("Form", "Daily Progress Report", name);
		});

		this.$wrapper.find(".cm-dpr-clear").on("click", () => {
			this.search.set_value("");
			this.project.set_value("");
			this.from_date.set_value("");
			this.to_date.set_value("");
			this.review_status.set_value("");
			this.start = 0;
			this.fetch();
		});

		this.$wrapper.find(".cm-dpr-prev").on("click", () => {
			if (this.start > 0) {
				this.start = Math.max(0, this.start - CM_DPR_PAGE_LENGTH);
				this.fetch();
			}
		});

		this.$wrapper.find(".cm-dpr-next").on("click", () => {
			if (this.start + CM_DPR_PAGE_LENGTH < this.total) {
				this.start += CM_DPR_PAGE_LENGTH;
				this.fetch();
			}
		});
	}

	get_filters() {
		return {
			project: this.project.get_value() || "",
			from_date: this.from_date.get_value() || "",
			to_date: this.to_date.get_value() || "",
			review_status: this.review_status.get_value() || "",
		};
	}

	fetch() {
		this.render_loading();
		frappe.call({
			method: CM_DPR_LIST_METHOD,
			args: {
				filters: this.get_filters(),
				search: this.search.get_value() || "",
				start: this.start,
				page_length: CM_DPR_PAGE_LENGTH,
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
		this.$wrapper.find(".cm-dpr-count").first().text(__("Loading reports..."));
		this.$wrapper
			.find("tbody")
			.html(`<tr><td colspan="7" class="cm-dpr-state">${__("Loading Daily Progress Reports...")}</td></tr>`);
		this.update_pagination(0);
	}

	render_error() {
		this.$wrapper.find(".cm-dpr-count").first().text(__("Unable to load reports"));
		this.$wrapper.find("tbody").html(`
			<tr>
				<td colspan="7" class="cm-dpr-state cm-dpr-state-error">
					<div>${__("Failed to load Daily Progress Reports.")}</div>
					<div class="cm-dpr-state-actions">
						<button class="btn btn-xs btn-default cm-dpr-retry">${__("Retry")}</button>
					</div>
				</td>
			</tr>
		`);
		this.$wrapper.find(".cm-dpr-retry").on("click", () => this.fetch());
		this.update_pagination(0);
	}

	render_records(records) {
		const esc = frappe.utils.escape_html;
		if (!records.length) {
			this.$wrapper.find(".cm-dpr-count").first().text(__("0 reports"));
			this.$wrapper.find("tbody").html(`
				<tr>
					<td colspan="7" class="cm-dpr-state">
						${__("No Daily Progress Reports match the selected filters.")}
					</td>
				</tr>
			`);
			this.update_pagination(0);
			return;
		}

		const end = this.start + records.length;
		this.$wrapper
			.find(".cm-dpr-count")
			.first()
			.text(__("Showing {0}–{1} of {2} reports", [this.start + 1, end, this.total]));

		const rows = records
			.map((row) => {
				const project_label = row.project_name || row.project || "";
				const progress = flt(row.overall_progress || 0);
				const status = row.review_status || "Draft";
				const status_class = status.toLowerCase().replace(/\s+/g, "-");
				const report_date = row.report_date ? frappe.datetime.str_to_user(row.report_date) : "";
				return `
					<tr data-name="${esc(row.name)}" title="${__("Open Daily Progress Report")}">
						<td class="cm-dpr-id">${esc(row.name)}</td>
						<td>${esc(project_label)}</td>
						<td class="cm-dpr-nowrap">${esc(report_date)}</td>
						<td>${esc(row.site_engineer || "")}</td>
						<td class="cm-dpr-nowrap">${progress}%</td>
						<td><span class="cm-status cm-status-${status_class}">${__(status)}</span></td>
						<td class="cm-dpr-open">${frappe.utils.icon("right", "sm")}</td>
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
		this.$wrapper.find(".cm-dpr-prev").prop("disabled", !has_prev);
		this.$wrapper.find(".cm-dpr-next").prop("disabled", !has_next);

		const page_num = Math.floor(this.start / CM_DPR_PAGE_LENGTH) + 1;
		const total_pages = Math.max(1, Math.ceil(this.total / CM_DPR_PAGE_LENGTH));
		this.$wrapper
			.find(".cm-dpr-page-info")
			.text(this.total ? __("Page {0} of {1}", [page_num, total_pages]) : "");
	}
}
