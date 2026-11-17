const CM_PO_STATUSES = [
	"Draft",
	"To Receive and Bill",
	"To Receive",
	"To Bill",
	"Completed",
	"Cancelled",
];

frappe.pages["construction-purchase-orders"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Purchase Orders"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));
	page.add_inner_button(__("Standard PO List"), () => frappe.set_route("List", "Purchase Order"));

	frappe.require(
		[
			"/assets/construction_management/css/construction_management.css",
			"/assets/construction_management/js/sample_projects.js",
		],
		() => {
			wrapper.po_list = new PurchaseOrderList(page);
		}
	);
};

frappe.pages["construction-purchase-orders"].on_page_show = function (wrapper) {
	wrapper.po_list?.refresh();
};

class PurchaseOrderList {
	constructor(page) {
		this.page = page;
		this.orders = [];
		this.projects = [];
		this.suppliers = [];

		if (frappe.model.can_create("Purchase Order")) {
			page.set_primary_action(
				__("New Purchase Order"),
				() => this.show_new_po_dialog(),
				"add"
			);
		}

		this.make_filters();
		this.make_layout();
		this.refresh();
	}

	make_filters() {
		this.search = this.page.add_field({
			fieldname: "search",
			label: __("Search PO ID, vendor or project"),
			fieldtype: "Data",
		});
		this.search.$input.on("input", frappe.utils.debounce(() => this.render(), 200));
		$(this.search.wrapper).removeClass("col-md-2").addClass("col-md-3");

		this.project = this.page.add_field({
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Select",
			options: [""],
			change: () => this.render(),
		});

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", ...CM_PO_STATUSES],
			change: () => this.render(),
		});

		this.supplier = this.page.add_field({
			fieldname: "supplier",
			label: __("Vendor / Supplier"),
			fieldtype: "Select",
			options: [""],
			change: () => this.render(),
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-purchase-orders">
				<div class="cm-tasks-card">
					<div class="cm-tasks-toolbar">
						<div>
							<span class="cm-tasks-count font-weight-bold"></span>
							<span class="cm-po-total-val text-muted ml-3"></span>
						</div>
						<button class="btn btn-xs btn-default cm-po-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-tasks-table-wrapper">
						<table class="cm-tasks-table">
							<thead>
								<tr>
									<th>${__("PO Number")}</th>
									<th>${__("Project")}</th>
									<th>${__("Vendor")}</th>
									<th>${__("Material Request")}</th>
									<th>${__("Required Date")}</th>
									<th>${__("Items Summary")}</th>
									<th class="text-right">${__("Total Amount")}</th>
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

		this.$wrapper.on("click", "tbody tr[data-po]", (e) => {
			frappe.set_route("Form", "Purchase Order", $(e.currentTarget).attr("data-po"));
		});

		this.$wrapper.find(".cm-po-clear").on("click", () => {
			this.search.set_value("");
			this.project.set_value("");
			this.status.set_value("");
			this.supplier.set_value("");
			this.render();
		});
	}

	async refresh() {
		this.show_message(__("Loading purchase orders..."));

		try {
			const res = await frappe.call({
				method: "construction_management.purchase_orders.get_purchase_orders",
			});
			this.orders = res.message || [];

			// Populate filter dropdowns dynamically
			const projects = [...new Set(this.orders.map((po) => po.project).filter(Boolean))].sort();
			this.project.df.options = ["", ...projects];
			this.project.refresh();

			const suppliers = [...new Set(this.orders.map((po) => po.supplier_name).filter(Boolean))].sort();
			this.supplier.df.options = ["", ...suppliers];
			this.supplier.refresh();

			this.render();
		} catch (err) {
			this.show_message(__("Unable to load purchase orders."));
		}
	}

	get_filtered() {
		const search = (this.search.get_value() || "").toLowerCase().trim();
		const project = this.project.get_value();
		const status = this.status.get_value();
		const supplier = this.supplier.get_value();

		return this.orders.filter((po) => {
			if (project && po.project !== project) return false;
			if (status && po.status !== status) return false;
			if (supplier && po.supplier_name !== supplier) return false;
			if (search) {
				const target = `${po.name} ${po.supplier_name} ${po.project} ${po.project_name} ${po.items_summary}`.toLowerCase();
				if (!target.includes(search)) return false;
			}
			return true;
		});
	}

	render() {
		const filtered = this.get_filtered();
		const totalVal = filtered.reduce((acc, po) => acc + (po.grand_total || 0), 0);
		const currency = filtered[0]?.currency || "INR";

		this.$wrapper
			.find(".cm-tasks-count")
			.text(__("Showing {0} of {1} Purchase Orders", [filtered.length, this.orders.length]));

		this.$wrapper
			.find(".cm-po-total-val")
			.text(
				totalVal > 0
					? __("Total Value: {0}", [format_currency(totalVal, currency)])
					: ""
			);

		if (!filtered.length) {
			this.show_message(
				this.orders.length
					? __("No purchase orders match the selected filters.")
					: __("No purchase orders found. Click 'New Purchase Order' to create one.")
			);
			return;
		}

		this.$wrapper.find("tbody").html(filtered.map(po_row).join(""));
	}

	show_message(message) {
		this.$wrapper
			.find("tbody")
			.html(`<tr><td colspan="9" class="cm-tasks-empty text-center p-4 text-muted">${message}</td></tr>`);
	}

	show_new_po_dialog() {
		let items = [];

		const dialog = new frappe.ui.Dialog({
			title: __("New Construction Purchase Order"),
			size: "large",
			fields: [
				{ fieldtype: "Section Break", label: __("Project & Procurement Details") },
				{
					fieldname: "project",
					fieldtype: "Link",
					options: "Project",
					label: __("Project"),
					reqd: 1,
					change: () => {
						const proj = dialog.get_value("project");
						dialog.set_df_property("material_request", "get_query", () => {
							return {
								filters: {
									project: proj,
									material_request_type: "Purchase",
									docstatus: ["<", 2],
								},
							};
						});
					},
				},
				{
					fieldname: "supplier",
					fieldtype: "Link",
					options: "Supplier",
					label: __("Vendor / Supplier"),
					reqd: 1,
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "material_request",
					fieldtype: "Link",
					options: "Material Request",
					label: __("Link Material Request"),
					change: async () => {
						const mr_name = dialog.get_value("material_request");
						if (!mr_name) return;

						frappe.call({
							method: "construction_management.purchase_orders.get_material_request_details",
							args: { material_request: mr_name },
							callback: (r) => {
								if (r.message) {
									if (r.message.project && !dialog.get_value("project")) {
										dialog.set_value("project", r.message.project);
									}
									if (r.message.schedule_date) {
										dialog.set_value("required_date", r.message.schedule_date);
									}
									items = r.message.items.map((it) => ({
										item_code: it.item_code,
										item_name: it.item_name,
										qty: it.qty || 1,
										rate: it.rate || 0,
										stock_uom: it.stock_uom,
										material_request: mr_name,
										material_request_item: it.material_request_item,
									}));
									render_dialog_items();
								}
							},
						});
					},
				},
				{
					fieldname: "required_date",
					fieldtype: "Date",
					label: __("Required Delivery Date"),
					default: frappe.datetime.add_days(frappe.datetime.nowdate(), 7),
					reqd: 1,
				},
				{ fieldtype: "Section Break", label: __("Site Delivery Information") },
				{
					fieldname: "delivery_site",
					fieldtype: "Data",
					label: __("Site / Delivery Location"),
					placeholder: __("e.g. Block A, North Site, Pune"),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "delivery_contact",
					fieldtype: "Data",
					label: __("Site Contact Person"),
					placeholder: __("e.g. Site Supervisor / Engineer Phone"),
				},
				{ fieldtype: "Section Break", label: __("Order Items") },
				{
					fieldname: "items_html",
					fieldtype: "HTML",
				},
			],
			primary_action_label: __("Create Purchase Order"),
			primary_action: (values) => {
				if (!items.length) {
					frappe.msgprint(__("Please add at least one material item to the Purchase Order."));
					return;
				}

				for (let it of items) {
					if (!it.item_code) {
						frappe.msgprint(__("Item Code is required for all rows."));
						return;
					}
					if (flt(it.qty) <= 0) {
						frappe.msgprint(__("Quantity must be greater than zero for {0}", [it.item_code]));
						return;
					}
				}

				frappe.call({
					method: "construction_management.purchase_orders.create_construction_purchase_order",
					args: {
						project: values.project,
						supplier: values.supplier,
						required_date: values.required_date,
						material_request: values.material_request,
						delivery_site: values.delivery_site,
						delivery_contact: values.delivery_contact,
						items: items,
						submit: 0,
					},
					freeze: true,
					freeze_message: __("Creating Purchase Order..."),
					callback: (r) => {
						if (r.message) {
							dialog.hide();
							frappe.show_alert({
								message: __("Purchase Order {0} created successfully", [r.message.name]),
								indicator: "green",
							});
							this.refresh();
							frappe.set_route("Form", "Purchase Order", r.message.name);
						}
					},
				});
			},
		});

		function render_dialog_items() {
			const $container = dialog.get_field("items_html").$wrapper;
			let rowsHtml = items
				.map(
					(it, idx) => `
				<tr>
					<td><input type="text" class="form-control input-sm cm-po-item-code" data-idx="${idx}" value="${frappe.utils.escape_html(it.item_code || "")}" placeholder="${__("Item Code / Material")}"></td>
					<td><input type="number" class="form-control input-sm cm-po-item-qty text-right" data-idx="${idx}" value="${it.qty || 1}" min="1" step="any"></td>
					<td><input type="text" class="form-control input-sm cm-po-item-uom" data-idx="${idx}" value="${frappe.utils.escape_html(it.stock_uom || "")}" placeholder="${__("UOM")}"></td>
					<td><input type="number" class="form-control input-sm cm-po-item-rate text-right" data-idx="${idx}" value="${it.rate || 0}" min="0" step="any"></td>
					<td class="text-right font-weight-bold align-middle cm-po-item-amount">${format_currency((it.qty || 1) * (it.rate || 0))}</td>
					<td class="text-center align-middle">
						<button class="btn btn-xs btn-danger cm-po-remove-row" data-idx="${idx}">✕</button>
					</td>
				</tr>
			`
				)
				.join("");

			if (!items.length) {
				rowsHtml = `<tr><td colspan="6" class="text-center text-muted p-3">${__("No items added yet. Click '+ Add Material Item' below.")}</td></tr>`;
			}

			$container.html(`
				<table class="cm-po-items-table">
					<thead>
						<tr>
							<th style="width: 35%;">${__("Material / Item")}</th>
							<th style="width: 15%;">${__("Quantity")}</th>
							<th style="width: 15%;">${__("Unit (UOM)")}</th>
							<th style="width: 15%;">${__("Rate (₹)")}</th>
							<th style="width: 15%; text-align: right;">${__("Amount")}</th>
							<th style="width: 5%;"></th>
						</tr>
					</thead>
					<tbody>
						${rowsHtml}
					</tbody>
				</table>
				<div class="mt-2">
					<button class="btn btn-xs btn-default cm-po-add-row">+ ${__("Add Material Item")}</button>
				</div>
			`);

			// Bind table interactions
			$container.find(".cm-po-add-row").on("click", (e) => {
				e.preventDefault();
				items.push({ item_code: "", qty: 1, rate: 0, stock_uom: "" });
				render_dialog_items();
			});

			$container.find(".cm-po-remove-row").on("click", function (e) {
				e.preventDefault();
				const idx = $(this).attr("data-idx");
				items.splice(idx, 1);
				render_dialog_items();
			});

			$container.find(".cm-po-item-code").on("change", function () {
				const idx = $(this).attr("data-idx");
				items[idx].item_code = $(this).val();
			});

			$container.find(".cm-po-item-qty").on("input", function () {
				const idx = $(this).attr("data-idx");
				items[idx].qty = flt($(this).val()) || 0;
				update_row_amount($container, idx, items[idx]);
			});

			$container.find(".cm-po-item-rate").on("input", function () {
				const idx = $(this).attr("data-idx");
				items[idx].rate = flt($(this).val()) || 0;
				update_row_amount($container, idx, items[idx]);
			});

			$container.find(".cm-po-item-uom").on("change", function () {
				const idx = $(this).attr("data-idx");
				items[idx].stock_uom = $(this).val();
			});
		}

		function update_row_amount($c, idx, it) {
			const amt = (it.qty || 0) * (it.rate || 0);
			$c.find(`tr:eq(${parseInt(idx) + 1}) .cm-po-item-amount`).text(format_currency(amt));
		}

		// Initialize with one default item row
		items = [{ item_code: "CM-CEM-001", qty: 100, rate: 380, stock_uom: "Bag" }];
		dialog.show();
		render_dialog_items();
	}
}

function po_status_pill(status) {
	const map = {
		Draft: "draft",
		"To Receive and Bill": "in-progress",
		"To Receive": "in-progress",
		"To Bill": "warning",
		Completed: "completed",
		Cancelled: "delayed",
	};
	const css_class = map[status] || "default";
	return `<span class="cm-status cm-status-${css_class}">${__(status)}</span>`;
}

function po_row(po) {
	const esc = frappe.utils.escape_html;
	const mrBadge = po.material_request
		? `<span class="cm-po-mr-tag">${esc(po.material_request)}</span>`
		: `<span class="text-muted">—</span>`;

	return `
		<tr data-po="${esc(po.name)}" title="${__("Open Purchase Order")}">
			<td class="cm-tasks-name">${esc(po.name)}</td>
			<td>
				<div class="font-weight-bold">${esc(po.project_name || po.project)}</div>
				<div class="small text-muted">${esc(po.project)}</div>
			</td>
			<td>${esc(po.supplier_name)}</td>
			<td>${mrBadge}</td>
			<td class="cm-tasks-nowrap">${esc(po.schedule_date || po.transaction_date)}</td>
			<td><div class="cm-po-items-preview" title="${esc(po.items_summary)}">${esc(po.items_summary)}</div></td>
			<td class="text-right font-weight-bold cm-tasks-nowrap">${format_currency(po.grand_total, po.currency)}</td>
			<td>${po_status_pill(po.status)}</td>
			<td class="cm-tasks-open">${frappe.utils.icon("right", "sm")}</td>
		</tr>
	`;
}
