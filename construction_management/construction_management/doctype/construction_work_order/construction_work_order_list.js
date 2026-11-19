// Copyright (c) 2026, TechnoTribes and contributors
// For license information, please see license.txt

const CWO_LIST_STATUS_COLORS = {
	Open: "light-blue",
	"In Progress": "blue",
	"On Hold": "orange",
	Completed: "green",
	Cancelled: "gray",
};

frappe.listview_settings["Construction Work Order"] = {
	add_fields: ["status", "priority", "project", "contractor"],

	get_indicator(doc) {
		const status = doc.status || "Open";
		const color = CWO_LIST_STATUS_COLORS[status] || "gray";
		return [__(status), color, `status,=,${status}`];
	},
};
