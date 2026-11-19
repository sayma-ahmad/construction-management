const CM_GRN_METHOD = "construction_management.grn";
const CM_GRN_STATUSES = [
	"Draft",
	"To Bill",
	"Partly Billed",
	"Completed",
	"Return",
	"Return Issued",
	"Cancelled",
	"Closed",
];
const CM_RECEIVABLE_PO_STATUSES = ["To Receive and Bill", "To Receive"];

frappe.pages["construction-grn"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Goods Receipt Notes"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	frappe.require("/assets/construction_management/css/construction_management.css", () => {
		wrapper.grn_list = new GRNList(page);
	});
};

frappe.pages["construction-grn"].on_page_show = function (wrapper) {
	wrapper.grn_list?.refresh();
};

class GRNList {
	constructor(page) {
		this.page = page;
		this.grns = [];

		if (frappe.model.can_create("Purchase Receipt")) {
			page.set_primary_action(__("New GRN"), () => this.show_new_grn_dialog(), "add");
		}

		this.make_filters();
		this.make_layout();
		this.refresh();
	}

	make_filters() {
		this.search = this.page.add_field({
			fieldname: "search",
			label: __("Search GRN, supplier or delivery note"),
			fieldtype: "Data",
		});
		this.search.$input.on("input", frappe.utils.debounce(() => this.render(), 200));
		$(this.search.wrapper).removeClass("col-md-2").addClass("col-md-4");

		this.purchase_order = this.page.add_field({
			fieldname: "purchase_order",
			label: __("Purchase Order"),
			fieldtype: "Link",
			options: "Purchase Order",
			change: () => this.render(),
		});

		this.supplier = this.page.add_field({
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
			change: () => this.render(),
		});

		this.warehouse = this.page.add_field({
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			change: () => this.render(),
		});

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", ...CM_GRN_STATUSES],
			change: () => this.render(),
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-grn">
				<div class="cm-tasks-card">
					<div class="cm-tasks-toolbar">
						<span class="cm-tasks-count"></span>
						<button class="btn btn-xs btn-default cm-grn-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-tasks-table-wrapper">
						<table class="cm-tasks-table">
							<thead>
								<tr>
									<th>${__("GRN No")}</th>
									<th>${__("Supplier")}</th>
									<th>${__("Purchase Order")}</th>
									<th>${__("Project")}</th>
									<th>${__("Received On")}</th>
									<th>${__("Warehouse")}</th>
									<th class="cm-grn-qty">${__("Items")}</th>
									<th class="cm-grn-qty">${__("Received Qty")}</th>
									<th class="cm-grn-qty">${__("Accepted Qty")}</th>
									<th>${__("Status")}</th>
									<th></th>
								</tr>
							</thead>
							<tbody></tbody>
						</table>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$wrapper.on("click", "tbody tr[data-grn]", (e) => {
			frappe.set_route("Form", "Purchase Receipt", $(e.currentTarget).attr("data-grn"));
		});

		this.$wrapper.find(".cm-grn-clear").on("click", () => {
			this.search.set_value("");
			this.purchase_order.set_value("");
			this.supplier.set_value("");
			this.warehouse.set_value("");
			this.status.set_value("");
			this.render();
		});
	}

	async refresh() {
		this.show_message(__("Loading goods receipt notes..."));
		const { message } = await frappe.call(`${CM_GRN_METHOD}.get_grns`);
		this.grns = (message || []).map((grn) => ({ ...grn, display_status: grn_status(grn) }));
		this.render();
	}

	get_filtered() {
		const search = (this.search.get_value() || "").trim().toLowerCase();
		const purchase_order = this.purchase_order.get_value();
		const supplier = this.supplier.get_value();
		const warehouse = this.warehouse.get_value();
		const status = this.status.get_value();

		return this.grns.filter((grn) => {
			const matches_search =
				!search ||
				[grn.name, grn.supplier, grn.supplier_name, grn.supplier_delivery_note].some((value) =>
					(value || "").toLowerCase().includes(search)
				);
			return (
				matches_search &&
				(!purchase_order || grn.purchase_orders.includes(purchase_order)) &&
				(!supplier || grn.supplier === supplier) &&
				(!warehouse || grn.warehouses.includes(warehouse)) &&
				(!status || grn.display_status === status)
			);
		});
	}

	render() {
		const grns = this.get_filtered();

		this.$wrapper
			.find(".cm-tasks-count")
			.text(__("Showing {0} of {1} goods receipt notes", [grns.length, this.grns.length]));

		if (!grns.length) {
			this.show_message(
				this.grns.length
					? __("No goods receipt notes match the selected filters.")
					: __("No goods receipt notes found.")
			);
			return;
		}

		this.$wrapper.find("tbody").html(grns.map(grn_row).join(""));
	}

	show_message(message) {
		this.$wrapper.find("tbody").html(`<tr><td colspan="11" class="cm-tasks-empty">${message}</td></tr>`);
	}

	show_new_grn_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: __("New GRN"),
			size: "extra-large",
			fields: [
				{
					fieldname: "purchase_order",
					fieldtype: "Link",
					options: "Purchase Order",
					label: __("Purchase Order"),
					reqd: 1,
					get_query: () => ({
						filters: { docstatus: 1, status: ["in", CM_RECEIVABLE_PO_STATUSES] },
					}),
					onchange: () => this.load_purchase_order(dialog),
				},
				{ fieldname: "supplier_name", fieldtype: "Data", label: __("Supplier"), read_only: 1 },
				{ fieldtype: "Column Break" },
				{
					fieldname: "warehouse",
					fieldtype: "Link",
					options: "Warehouse",
					label: __("Receiving Warehouse"),
					reqd: 1,
					get_query: () => ({
						filters: { is_group: 0, company: dialog.company || undefined },
					}),
				},
				{
					fieldname: "posting_date",
					fieldtype: "Date",
					label: __("Received On"),
					default: frappe.datetime.get_today(),
					reqd: 1,
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "supplier_delivery_note",
					fieldtype: "Data",
					label: __("Supplier Delivery Note / Challan No"),
				},
				{ fieldtype: "Section Break", label: __("Materials Received") },
				{
					fieldname: "items",
					fieldtype: "Table",
					cannot_add_rows: true,
					in_place_edit: true,
					data: [],
					fields: [
						{ fieldname: "purchase_order_item", fieldtype: "Data", hidden: 1 },
						{
							fieldname: "item_code",
							fieldtype: "Link",
							options: "Item",
							label: __("Material"),
							read_only: 1,
							in_list_view: 1,
							columns: 3,
						},
						{ fieldname: "uom", fieldtype: "Data", label: __("UOM"), read_only: 1, in_list_view: 1, columns: 1 },
						{
							fieldname: "ordered_qty",
							fieldtype: "Float",
							label: __("Ordered Qty"),
							read_only: 1,
							in_list_view: 1,
							columns: 2,
						},
						{
							fieldname: "received_qty",
							fieldtype: "Float",
							label: __("Already Received"),
							read_only: 1,
							in_list_view: 1,
							columns: 2,
						},
						{
							fieldname: "qty",
							fieldtype: "Float",
							label: __("Receiving Now"),
							in_list_view: 1,
							columns: 2,
						},
					],
				},
			],
			primary_action_label: __("Create GRN"),
			primary_action: (values) => this.create_grn(dialog, values),
		});
		dialog.show();
	}

	async load_purchase_order(dialog) {
		const purchase_order = dialog.get_value("purchase_order");
		const items_field = dialog.fields_dict.items;
		dialog.company = null;
		items_field.df.data = [];

		if (purchase_order) {
			const { message } = await frappe.call({
				method: `${CM_GRN_METHOD}.get_purchase_order_items`,
				args: { purchase_order },
			});
			dialog.company = message.company;
			dialog.set_value("supplier_name", message.supplier_name || message.supplier);
			const warehouse = message.set_warehouse || message.items.find((row) => row.warehouse)?.warehouse;
			if (warehouse) dialog.set_value("warehouse", warehouse);
			items_field.df.data = message.items
				.filter((row) => row.pending_qty > 0)
				.map((row) => ({ ...row, qty: row.pending_qty }));
		} else {
			dialog.set_value("supplier_name", "");
		}

		items_field.grid.refresh();
	}

	async create_grn(dialog, values) {
		const items = (dialog.fields_dict.items.df.data || [])
			.filter((row) => flt(row.qty) > 0)
			.map((row) => ({ purchase_order_item: row.purchase_order_item, qty: row.qty }));

		if (!items.length) {
			frappe.msgprint(__("Enter a received quantity for at least one material."));
			return;
		}

		const { message: name } = await frappe.call({
			method: `${CM_GRN_METHOD}.make_grn`,
			args: {
				purchase_order: values.purchase_order,
				items,
				warehouse: values.warehouse,
				posting_date: values.posting_date,
				supplier_delivery_note: values.supplier_delivery_note,
			},
			freeze: true,
			freeze_message: __("Creating GRN..."),
		});

		dialog.hide();
		frappe.show_alert({
			message: __("Draft GRN {0} created. Review and submit it to update stock.", [name]),
			indicator: "green",
		});
		frappe.set_route("Form", "Purchase Receipt", name);
	}
}

function grn_status(grn) {
	if (grn.docstatus === 0) return "Draft";
	if (grn.docstatus === 2) return "Cancelled";
	return grn.status;
}

function format_qty(value) {
	return frappe.format(value, { fieldtype: "Float" }, { inline: true });
}

function grn_row(grn) {
	const esc = frappe.utils.escape_html;
	const status_class = grn.display_status.toLowerCase().replace(/\s+/g, "-");
	return `
		<tr data-grn="${esc(grn.name)}" title="${__("Open GRN")}">
			<td class="cm-tasks-name">${esc(grn.name)}</td>
			<td class="cm-tasks-nowrap">${esc(grn.supplier_name || grn.supplier)}</td>
			<td class="cm-tasks-nowrap">${esc(grn.purchase_orders.join(", "))}</td>
			<td class="cm-tasks-nowrap">${esc(grn.project || "")}</td>
			<td class="cm-tasks-muted">${esc(frappe.datetime.str_to_user(grn.posting_date))}</td>
			<td class="cm-tasks-nowrap">${esc(grn.warehouses.join(", "))}</td>
			<td class="cm-grn-qty">${grn.item_count}</td>
			<td class="cm-grn-qty">${format_qty(grn.received_qty)}</td>
			<td class="cm-grn-qty">${format_qty(grn.accepted_qty)}</td>
			<td><span class="cm-status cm-status-${status_class}">${__(grn.display_status)}</span></td>
			<td class="cm-tasks-open">${frappe.utils.icon("right", "sm")}</td>
		</tr>
	`;
}
