// Copyright (c) 2026, TechnoTribes and contributors
// For license information, please see license.txt

frappe.ui.form.on("Material Request", {
	setup(frm) {
		frm.set_query("project", "items", () => {
			if (!frm.doc.cm_project) {
				return {};
			}
			return {
				filters: {
					name: frm.doc.cm_project,
				},
			};
		});
	},

	cm_project(frm) {
		if (!frm.doc.cm_project) {
			return;
		}

		let mismatched_updated = false;
		for (const row of frm.doc.items || []) {
			if (row.project && row.project !== frm.doc.cm_project) {
				mismatched_updated = true;
			}
			if (row.project !== frm.doc.cm_project) {
				frappe.model.set_value(row.doctype, row.name, "project", frm.doc.cm_project);
			}
		}

		if (mismatched_updated) {
			frappe.show_alert({
				message: __("Updated item row projects to match {0}.", [frm.doc.cm_project]),
				indicator: "blue",
			});
		}
	},
});

frappe.ui.form.on("Material Request Item", {
	items_add(frm, cdt, cdn) {
		if (frm.doc.cm_project) {
			frappe.model.set_value(cdt, cdn, "project", frm.doc.cm_project);
		}
	},
});
