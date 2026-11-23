// Copyright (c) 2026, TechnoTribes and contributors
// For license information, please see license.txt

const DPR_APPROVE_METHOD =
	"construction_management.construction_management.doctype.daily_progress_report.daily_progress_report.approve_dpr";
const DPR_REVISION_METHOD =
	"construction_management.construction_management.doctype.daily_progress_report.daily_progress_report.request_dpr_revision";

frappe.ui.form.on("Daily Progress Report", {
	setup(frm) {
		frm.set_query("task", "task_progress", () => {
			if (!frm.doc.project) {
				return {
					filters: {
						name: "",
					},
				};
			}
			return {
				filters: {
					project: frm.doc.project,
					is_group: 0,
				},
			};
		});
	},

	refresh(frm) {
		frm.set_df_property("review_remarks", "read_only", frm.doc.docstatus !== 0 ? 1 : 0);

		if (
			frm.doc.docstatus === 1 &&
			frm.doc.review_status === "Pending Review" &&
			frappe.user.has_role(["System Manager", "Projects Manager"])
		) {
			frm.add_custom_button(__("Approve"), () => handle_approve_dpr(frm), __("Review"));
			frm.add_custom_button(
				__("Request Revision"),
				() => handle_request_revision(frm),
				__("Review")
			);
		}
	},

	async project(frm) {
		const rows = frm.doc.task_progress || [];
		if (!rows.length) {
			return;
		}

		if (!frm.doc.project) {
			frm.clear_table("task_progress");
			frm.refresh_field("task_progress");
			frappe.msgprint(__("Cleared Task Progress rows because Project was removed."));
			return;
		}

		const task_names = [...new Set(rows.map((row) => row.task).filter(Boolean))];
		if (!task_names.length) {
			return;
		}

		const tasks = await frappe.db.get_list("Task", {
			filters: { name: ["in", task_names] },
			fields: ["name", "project"],
			limit: task_names.length,
		});
		const task_project_map = Object.fromEntries(tasks.map((t) => [t.name, t.project]));

		const invalid_rows = rows.filter(
			(row) => row.task && task_project_map[row.task] !== frm.doc.project
		);

		if (invalid_rows.length) {
			const grid = frm.get_field("task_progress")?.grid;
			for (const row of [...invalid_rows].reverse()) {
				const grid_row = grid?.grid_rows_by_docname?.[row.name];
				if (grid_row) {
					grid_row.remove();
				} else {
					frappe.model.clear_doc(row.doctype, row.name);
				}
			}
			frm.refresh_field("task_progress");
			frappe.msgprint(
				__("Removed Task Progress rows that do not belong to Project {0}.", [
					frm.doc.project,
				])
			);
		}
	},
});

function handle_approve_dpr(frm) {
	frappe.prompt(
		[
			{
				fieldname: "review_remarks",
				fieldtype: "Small Text",
				label: __("Review Remarks (Optional)"),
			},
		],
		(values) => {
			frappe.confirm(
				__("Approve Daily Progress Report {0}?", [frm.doc.name]),
				() => {
					frappe.call({
						method: DPR_APPROVE_METHOD,
						args: {
							dpr_name: frm.doc.name,
							review_remarks: values.review_remarks || "",
						},
						freeze: true,
						freeze_message: __("Approving Daily Progress Report..."),
						callback() {
							frappe.show_alert({
								message: __("Daily Progress Report approved."),
								indicator: "green",
							});
							frm.reload_doc();
						},
					});
				}
			);
		},
		__("Approve Daily Progress Report"),
		__("Continue")
	);
}

function handle_request_revision(frm) {
	frappe.prompt(
		[
			{
				fieldname: "review_remarks",
				fieldtype: "Small Text",
				label: __("Review Remarks"),
				reqd: 1,
			},
		],
		(values) => {
			frappe.confirm(
				__("Request revision for Daily Progress Report {0}?", [frm.doc.name]),
				() => {
					frappe.call({
						method: DPR_REVISION_METHOD,
						args: {
							dpr_name: frm.doc.name,
							review_remarks: values.review_remarks,
						},
						freeze: true,
						freeze_message: __("Requesting revision..."),
						callback() {
							frappe.show_alert({
								message: __("Revision requested for Daily Progress Report."),
								indicator: "orange",
							});
							frm.reload_doc();
						},
					});
				}
			);
		},
		__("Request Revision"),
		__("Continue")
	);
}
