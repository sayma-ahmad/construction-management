// Copyright (c) 2026, TechnoTribes and contributors
// For license information, please see license.txt

const CWO_CONTRACTOR_QUERY =
	"construction_management.construction_management.doctype.construction_work_order.construction_work_order.get_contractor_options";
const CWO_CONTRACTOR_DETAILS_METHOD =
	"construction_management.construction_management.doctype.construction_work_order.construction_work_order.get_contractor_details";

const CWO_STATUS_COLORS = {
	Open: "light-blue",
	"In Progress": "blue",
	"On Hold": "orange",
	Completed: "green",
	Cancelled: "gray",
};

const CWO_STATUS_ACTIONS = {
	Open: [
		{ label: __("Start Work"), status: "In Progress", primary: true },
		{ label: __("Cancel"), status: "Cancelled" },
	],
	"In Progress": [
		{ label: __("Mark Completed"), status: "Completed", primary: true },
		{ label: __("Put On Hold"), status: "On Hold" },
		{ label: __("Cancel"), status: "Cancelled" },
	],
	"On Hold": [
		{ label: __("Resume Work"), status: "In Progress", primary: true },
		{ label: __("Cancel"), status: "Cancelled" },
	],
};

frappe.ui.form.on("Construction Work Order", {
	setup(frm) {
		frm.set_query("task", () => {
			if (!frm.doc.project) {
				return { filters: { name: "" } };
			}
			return { filters: { project: frm.doc.project } };
		});

		frm.set_query("contractor", () => ({
			query: CWO_CONTRACTOR_QUERY,
		}));
	},

	refresh(frm) {
		const status = frm.doc.status || "Open";
		const color = CWO_STATUS_COLORS[status] || "gray";
		frm.page.set_indicator(__(status), color);
		frm.set_df_property(
			"status",
			"read_only",
			!frm.is_new() && ["Completed", "Cancelled"].includes(status) ? 1 : 0
		);

		if (frm.is_new()) {
			return;
		}

		const actions = CWO_STATUS_ACTIONS[status] || [];
		for (const action of actions) {
			const btn = frm.add_custom_button(
				action.label,
				() => change_work_order_status(frm, action.status),
				__("Status")
			);
			if (action.primary) {
				btn.addClass("btn-primary");
			}
		}
	},

	async project(frm) {
		if (!frm.doc.project) {
			frm.set_value("project_name", "");
			if (frm.doc.task) {
				await frm.set_value("task", "");
				frappe.msgprint(__("Cleared Related Task because Project was removed."));
			}
			return;
		}

		if (!frm.doc.task) {
			return;
		}

		const { message: task } = await frappe.db.get_value("Task", frm.doc.task, "project");
		if (task && task.project !== frm.doc.project) {
			await frm.set_value("task", "");
			frappe.msgprint(
				__("Cleared Related Task because it does not belong to Project {0}.", [
					frm.doc.project,
				])
			);
		}
	},

	async contractor(frm) {
		if (!frm.doc.contractor) {
			frm.set_value("contractor_name", "");
			frm.set_value("specialization", "");
			return;
		}

		const { message: details } = await frappe.call({
			method: CWO_CONTRACTOR_DETAILS_METHOD,
			args: { contractor: frm.doc.contractor },
		});
		if (!details || !details.valid) {
			frappe.msgprint({
				title: __("Invalid Contractor"),
				message: __(
					"Contractor {0} must be an enabled Construction Vendor.",
					[frm.doc.contractor]
				),
				indicator: "red",
			});
			await frm.set_value("contractor", "");
			return;
		}

		frm.set_value("contractor_name", details.contractor_name || "");
		if (!frm.doc.specialization && details.specialization) {
			frm.set_value("specialization", details.specialization);
		}
	},

	validate(frm) {
		if (
			frm.doc.planned_start_date &&
			frm.doc.planned_end_date &&
			frm.doc.planned_end_date < frm.doc.planned_start_date
		) {
			frappe.throw(__("Planned End Date cannot be earlier than Planned Start Date."));
		}

		if (
			frm.doc.actual_start_date &&
			frm.doc.actual_completion_date &&
			frm.doc.actual_completion_date < frm.doc.actual_start_date
		) {
			frappe.throw(__("Actual Completion Date cannot be earlier than Actual Start Date."));
		}

		if (frm.doc.estimated_cost != null && flt(frm.doc.estimated_cost) < 0) {
			frappe.throw(__("Estimated Cost cannot be negative."));
		}
	},
});

function change_work_order_status(frm, next_status) {
	const apply_change = () => {
		frm.set_value("status", next_status);
		if (next_status === "Completed" && !frm.doc.actual_completion_date) {
			frm.set_value("actual_completion_date", frappe.datetime.get_today());
		}
		frm.save();
	};

	if (next_status === "Cancelled") {
		frappe.confirm(
			__("Cancel Work Order {0}?", [frm.doc.name]),
			apply_change
		);
		return;
	}

	apply_change();
}
