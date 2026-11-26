const CM_ISSUES_PAGE_ASSETS = ["/assets/construction_management/css/construction_management.css"];
const CM_ISSUES_LIST_METHOD =
	"construction_management.construction_management.issue.get_issue_list";
const CM_ISSUES_PAGE_LENGTH = 20;

frappe.pages["construction-issues"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Construction Issues"),
		single_column: true,
	});

	sync_issue_primary_action(page);
	page.set_secondary_action(__("Refresh"), () => wrapper.issue_list?.fetch());
	page.add_inner_button(__("Workspace"), () => frappe.set_route("construction-management"));

	frappe.require(CM_ISSUES_PAGE_ASSETS, () => {
		wrapper.issue_list = new ConstructionIssueList(page);
	});
};

frappe.pages["construction-issues"].on_page_show = function (wrapper) {
	if (wrapper.issue_list) {
		sync_issue_primary_action(wrapper.issue_list.page);
		wrapper.issue_list.fetch();
	}
};

function sync_issue_primary_action(page) {
	if (frappe.model.can_create("Issue")) {
		page.set_primary_action(__("New Issue"), () => frappe.new_doc("Issue"), "add");
	} else {
		page.clear_primary_action();
	}
}

class ConstructionIssueList {
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
			label: __("Search Issue ID, Subject or Project"),
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

		this.issue_type = this.page.add_field({
			fieldname: "issue_type",
			label: __("Issue Type"),
			fieldtype: "Link",
			options: "Issue Type",
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.priority = this.page.add_field({
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Link",
			options: "Issue Priority",
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Replied", "On Hold", "Resolved", "Closed"],
			change: () => {
				this.start = 0;
				this.fetch();
			},
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-issues-page">
				<div class="cm-issues-card">
					<div class="cm-issues-toolbar">
						<span class="cm-issues-count"></span>
						<button class="btn btn-xs btn-default cm-issues-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-issues-table-wrapper">
						<table class="cm-issues-table">
							<thead>
								<tr>
									<th>${__("Issue ID")}</th>
									<th>${__("Subject")}</th>
									<th>${__("Project")}</th>
									<th>${__("Issue Type")}</th>
									<th>${__("Priority")}</th>
									<th>${__("Status")}</th>
									<th>${__("Assigned To")}</th>
									<th>${__("Created On")}</th>
									<th></th>
								</tr>
							</thead>
							<tbody></tbody>
						</table>
					</div>
					<div class="cm-issues-pagination">
						<span class="cm-issues-count cm-issues-page-info"></span>
						<div class="cm-issues-pagination-actions">
							<button class="btn btn-xs btn-default cm-issues-prev">${__("Previous")}</button>
							<button class="btn btn-xs btn-default cm-issues-next">${__("Next")}</button>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$wrapper.on("click", "tbody tr[data-name]", (e) => {
			const name = $(e.currentTarget).attr("data-name");
			frappe.set_route("Form", "Issue", name);
		});

		this.$wrapper.find(".cm-issues-clear").on("click", () => {
			this.search.set_value("");
			this.project.set_value("");
			this.issue_type.set_value("");
			this.priority.set_value("");
			this.status.set_value("");
			this.start = 0;
			this.fetch();
		});

		this.$wrapper.find(".cm-issues-prev").on("click", () => {
			if (this.start > 0) {
				this.start = Math.max(0, this.start - CM_ISSUES_PAGE_LENGTH);
				this.fetch();
			}
		});

		this.$wrapper.find(".cm-issues-next").on("click", () => {
			if (this.start + CM_ISSUES_PAGE_LENGTH < this.total) {
				this.start += CM_ISSUES_PAGE_LENGTH;
				this.fetch();
			}
		});
	}

	get_filters() {
		return {
			project: this.project.get_value() || "",
			issue_type: this.issue_type.get_value() || "",
			priority: this.priority.get_value() || "",
			status: this.status.get_value() || "",
		};
	}

	fetch() {
		this.render_loading();
		frappe.call({
			method: CM_ISSUES_LIST_METHOD,
			args: {
				filters: this.get_filters(),
				search: this.search.get_value() || "",
				start: this.start,
				page_length: CM_ISSUES_PAGE_LENGTH,
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
		this.$wrapper.find(".cm-issues-count").first().text(__("Loading issues..."));
		this.$wrapper
			.find("tbody")
			.html(`<tr><td colspan="9" class="cm-issues-state">${__("Loading Construction Issues...")}</td></tr>`);
		this.update_pagination(0);
	}

	render_error() {
		this.$wrapper.find(".cm-issues-count").first().text(__("Unable to load issues"));
		this.$wrapper.find("tbody").html(`
			<tr>
				<td colspan="9" class="cm-issues-state cm-issues-state-error">
					<div>${__("Failed to load Construction Issues.")}</div>
					<div class="cm-issues-state-actions">
						<button class="btn btn-xs btn-default cm-issues-retry">${__("Retry")}</button>
					</div>
				</td>
			</tr>
		`);
		this.$wrapper.find(".cm-issues-retry").on("click", () => this.fetch());
		this.update_pagination(0);
	}

	render_records(records) {
		const esc = frappe.utils.escape_html;
		if (!records.length) {
			this.$wrapper.find(".cm-issues-count").first().text(__("0 issues"));
			this.$wrapper.find("tbody").html(`
				<tr>
					<td colspan="9" class="cm-issues-state">
						${__("No Construction Issues match the selected filters.")}
					</td>
				</tr>
			`);
			this.update_pagination(0);
			return;
		}

		const end = this.start + records.length;
		this.$wrapper
			.find(".cm-issues-count")
			.first()
			.text(__("Showing {0}–{1} of {2} issues", [this.start + 1, end, this.total]));

		const rows = records
			.map((row) => {
				const status = row.status || "Open";
				const status_class = status.toLowerCase().replace(/\s+/g, "-");
				const priority = row.priority || "";
				const priority_class = priority.toLowerCase().replace(/\s+/g, "-");
				const assigned = (row.assigned_to || []).length
					? row.assigned_to.join(", ")
					: __("Unassigned");
				const opening_date = row.opening_date
					? frappe.datetime.str_to_user(row.opening_date)
					: "";

				return `
					<tr data-name="${esc(row.name)}" title="${__("Open Issue")}">
						<td class="cm-issues-id">${esc(row.name)}</td>
						<td>${esc(row.subject || "")}</td>
						<td>${esc(row.project || "")}</td>
						<td>${esc(row.issue_type || "")}</td>
						<td>${
							priority
								? `<span class="cm-issue-priority cm-issue-priority-${esc(priority_class)}">${esc(priority)}</span>`
								: ""
						}</td>
						<td><span class="cm-status cm-status-${status_class}">${__(status)}</span></td>
						<td>${esc(assigned)}</td>
						<td class="cm-issues-nowrap">${esc(opening_date)}</td>
						<td class="cm-issues-open">${frappe.utils.icon("right", "sm")}</td>
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
		this.$wrapper.find(".cm-issues-prev").prop("disabled", !has_prev);
		this.$wrapper.find(".cm-issues-next").prop("disabled", !has_next);

		const page_num = Math.floor(this.start / CM_ISSUES_PAGE_LENGTH) + 1;
		const total_pages = Math.max(1, Math.ceil(this.total / CM_ISSUES_PAGE_LENGTH));
		this.$wrapper
			.find(".cm-issues-page-info")
			.text(this.total ? __("Page {0} of {1}", [page_num, total_pages]) : "");
	}
}
