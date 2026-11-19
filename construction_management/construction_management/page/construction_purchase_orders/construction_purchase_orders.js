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
		this.current_page = 1;
		this.page_length = 20;

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
		this.search.$input.on("input", frappe.utils.debounce(() => {
			this.current_page = 1;
			this.render();
		}, 200));
		$(this.search.wrapper).removeClass("col-md-2").addClass("col-md-3");

		this.project = this.page.add_field({
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Select",
			options: [""],
			change: () => {
				this.current_page = 1;
				this.render();
			},
		});

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", ...CM_PO_STATUSES],
			change: () => {
				this.current_page = 1;
				this.render();
			},
		});

		this.supplier = this.page.add_field({
			fieldname: "supplier",
			label: __("Vendor / Supplier"),
			fieldtype: "Select",
			options: [""],
			change: () => {
				this.current_page = 1;
				this.render();
			},
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-purchase-orders">
				<!-- KPI Cards Grid -->
				<div class="cm-po-kpi-grid">
					<div class="cm-po-kpi-card">
						<div class="cm-po-kpi-icon primary">${frappe.utils.icon("order", "md") || "📋"}</div>
						<div class="cm-po-kpi-body">
							<div class="cm-po-kpi-label">${__("Total Orders")}</div>
							<div class="cm-po-kpi-value cm-kpi-total">0</div>
							<div class="cm-po-kpi-note">${__("All purchase orders")}</div>
						</div>
					</div>
					<div class="cm-po-kpi-card">
						<div class="cm-po-kpi-icon success">${frappe.utils.icon("tool", "md") || "⚡"}</div>
						<div class="cm-po-kpi-body">
							<div class="cm-po-kpi-label">${__("Active Orders")}</div>
							<div class="cm-po-kpi-value cm-kpi-active">0</div>
							<div class="cm-po-kpi-note">${__("Draft & In Fulfillment")}</div>
						</div>
					</div>
					<div class="cm-po-kpi-card">
						<div class="cm-po-kpi-icon warning">${frappe.utils.icon("credit-card", "md") || "💰"}</div>
						<div class="cm-po-kpi-body">
							<div class="cm-po-kpi-label">${__("Total Spend")}</div>
							<div class="cm-po-kpi-value cm-kpi-spend">₹0</div>
							<div class="cm-po-kpi-note">${__("Total procurement value")}</div>
						</div>
					</div>
					<div class="cm-po-kpi-card">
						<div class="cm-po-kpi-icon info">${frappe.utils.icon("stock", "md") || "📦"}</div>
						<div class="cm-po-kpi-body">
							<div class="cm-po-kpi-label">${__("Pending Receipts")}</div>
							<div class="cm-po-kpi-value cm-kpi-receipts">0</div>
							<div class="cm-po-kpi-note">${__("Awaiting site delivery")}</div>
						</div>
					</div>
				</div>

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
					<div class="cm-po-pagination d-flex align-items-center justify-content-between p-3 border-top">
						<div class="text-muted small cm-po-pagination-info"></div>
						<div class="btn-group">
							<button class="btn btn-xs btn-default cm-po-prev">${__("Previous")}</button>
							<button class="btn btn-xs btn-default cm-po-next">${__("Next")}</button>
						</div>
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
			this.current_page = 1;
			this.render();
		});

		this.$wrapper.find(".cm-po-prev").on("click", () => {
			if (this.current_page > 1) {
				this.current_page--;
				this.render();
			}
		});

		this.$wrapper.find(".cm-po-next").on("click", () => {
			const filtered = this.get_filtered();
			const total_pages = Math.ceil(filtered.length / this.page_length) || 1;
			if (this.current_page < total_pages) {
				this.current_page++;
				this.render();
			}
		});
	}

	async refresh() {
		this.show_message(__("Loading purchase orders..."));

		try {
			const res = await frappe.call({
				method: "construction_management.purchase_orders.get_purchase_orders",
				args: {
					start: 0,
					page_length: 500,
				},
			});
			const data = res.message;
			if (Array.isArray(data)) {
				this.orders = data;
			} else if (data && data.orders) {
				this.orders = data.orders;
			} else {
				this.orders = [];
			}

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

		// Update KPI cards
		const activeCount = filtered.filter((po) =>
			["Draft", "To Receive and Bill", "To Receive", "To Bill"].includes(po.status)
		).length;
		const pendingReceipts = filtered.filter((po) =>
			["To Receive and Bill", "To Receive"].includes(po.status)
		).length;

		this.$wrapper.find(".cm-kpi-total").text(filtered.length);
		this.$wrapper.find(".cm-kpi-active").text(activeCount);
		this.$wrapper.find(".cm-kpi-spend").text(format_currency(totalVal, currency, 0));
		this.$wrapper.find(".cm-kpi-receipts").text(pendingReceipts);

		const total_records = filtered.length;
		const total_pages = Math.ceil(total_records / this.page_length) || 1;
		if (this.current_page > total_pages) this.current_page = total_pages;
		if (this.current_page < 1) this.current_page = 1;

		const start_idx = (this.current_page - 1) * this.page_length;
		const page_records = filtered.slice(start_idx, start_idx + this.page_length);

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
			this.$wrapper.find(".cm-po-pagination").hide();
			return;
		}

		this.$wrapper.find(".cm-po-pagination").show();
		this.$wrapper
			.find(".cm-po-pagination-info")
			.text(
				__("Showing {0}-{1} of {2} (Page {3} of {4})", [
					start_idx + 1,
					Math.min(start_idx + this.page_length, total_records),
					total_records,
					this.current_page,
					total_pages,
				])
			);

		this.$wrapper.find(".cm-po-prev").prop("disabled", this.current_page <= 1);
		this.$wrapper.find(".cm-po-next").prop("disabled", this.current_page >= total_pages);

		this.$wrapper.find("tbody").html(page_records.map(po_row).join(""));
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
						dialog.set_value("material_request", "");
						dialog.set_df_property("material_request", "get_query", () => {
							return {
								query: "construction_management.purchase_orders.material_request_query",
								filters: {
									project: proj || "",
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
					get_query: () => {
						const proj = dialog ? dialog.get_value("project") : "";
						return {
							query: "construction_management.purchase_orders.material_request_query",
							filters: {
								project: proj || "",
							},
						};
					},
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
									items = (r.message.items || []).map((it) => ({
										item_code: it.item_code,
										item_name: it.item_name,
										qty: it.remaining_qty || it.qty || 1,
										rate: it.rate || 0,
										stock_uom: it.stock_uom,
										remaining_qty: it.remaining_qty,
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
			primary_action_label: __("Save as Draft"),
			primary_action: () => save_po(0),
		});

		dialog.add_custom_action(__("Save & Submit"), () => save_po(1), "btn-primary");

		const save_po = (submit) => {
			const values = dialog.get_values();
			if (!values) return;

			if (!items.length) {
				frappe.msgprint(__("Please add at least one material item to the Purchase Order."));
				return;
			}

			for (let it of items) {
				if (!it.item_code) {
					frappe.msgprint(__("Item Code is required for all rows."));
					return;
				}
				if (!it.qty || it.qty <= 0) {
					frappe.msgprint(__("Quantity must be greater than zero for {0}.").format(it.item_code));
					return;
				}
				if (it.remaining_qty && it.qty > it.remaining_qty) {
					frappe.msgprint(
						__("Quantity {0} for item {1} cannot exceed remaining requested quantity of {2}.").format(
							it.qty,
							it.item_code,
							it.remaining_qty
						)
					);
					return;
				}
			}

			frappe.call({
				method: "construction_management.purchase_orders.create_construction_purchase_order",
				args: {
					project: values.project,
					supplier: values.supplier,
					required_date: values.required_date,
					material_request: values.material_request || "",
					delivery_site: values.delivery_site || "",
					delivery_contact: values.delivery_contact || "",
					items: JSON.stringify(items),
					submit: submit,
				},
				freeze: true,
				freeze_message: submit ? __("Submitting Purchase Order...") : __("Saving Purchase Order..."),
				callback: (r) => {
					if (!r.exc && r.message) {
						dialog.hide();
						frappe.show_alert({
							message: __(submit ? "Purchase Order {0} submitted" : "Purchase Order {0} saved as Draft", [r.message.name]),
							indicator: "green",
						});
						this.refresh();
					}
				},
			});
		};

		const render_dialog_items = () => {
			const $container = dialog.fields_dict.items_html.$wrapper;
			$container.empty();

			let rows = items.map((it, idx) => `
				<tr>
					<td>
						<input type="text" class="form-control input-sm cm-po-item-code" data-idx="${idx}" value="${frappe.utils.escape_html(it.item_code || "")}" placeholder="Item Code" />
					</td>
					<td>
						<input type="text" class="form-control input-sm cm-po-item-name" data-idx="${idx}" value="${frappe.utils.escape_html(it.item_name || "")}" placeholder="Item Description" />
					</td>
					<td style="width: 100px;">
						<input type="number" step="any" class="form-control input-sm cm-po-item-qty text-right" data-idx="${idx}" value="${it.qty || 1}" />
					</td>
					<td style="width: 100px;">
						<input type="text" class="form-control input-sm cm-po-item-uom" data-idx="${idx}" value="${frappe.utils.escape_html(it.stock_uom || "Unit")}" />
					</td>
					<td style="width: 110px;">
						<input type="number" step="any" class="form-control input-sm cm-po-item-rate text-right" data-idx="${idx}" value="${it.rate || 0}" />
					</td>
					<td class="text-right font-weight-bold cm-po-item-amount" style="width: 120px;">
						${format_currency((it.qty || 0) * (it.rate || 0))}
					</td>
					<td style="width: 40px; text-align: center;">
						<button class="btn btn-xs btn-default text-danger cm-po-item-del" data-idx="${idx}">×</button>
					</td>
				</tr>
			`).join("");

			$container.html(`
				<table class="cm-po-items-table table table-bordered">
					<thead>
						<tr>
							<th>${__("Item Code")}</th>
							<th>${__("Item Name")}</th>
							<th class="text-right">${__("Qty")}</th>
							<th>${__("UOM")}</th>
							<th class="text-right">${__("Rate (₹)")}</th>
							<th class="text-right">${__("Amount (₹)")}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						${rows || `<tr><td colspan="7" class="text-center text-muted p-3">${__("No items added yet.")}</td></tr>`}
					</tbody>
				</table>
				<div class="mt-2">
					<button class="btn btn-xs btn-default cm-po-add-row">+ ${__("Add Item")}</button>
				</div>
			`);

			// Bind row events
			$container.find(".cm-po-add-row").on("click", (e) => {
				e.preventDefault();
				items.push({ item_code: "", item_name: "", qty: 1, rate: 0, stock_uom: "Unit" });
				render_dialog_items();
			});

			$container.find(".cm-po-item-del").on("click", function (e) {
				e.preventDefault();
				const idx = parseInt($(this).attr("data-idx"));
				items.splice(idx, 1);
				render_dialog_items();
			});

			$container.find(".cm-po-item-code").on("change", function () {
				const idx = $(this).attr("data-idx");
				items[idx].item_code = $(this).val();
			});

			$container.find(".cm-po-item-name").on("change", function () {
				const idx = $(this).attr("data-idx");
				items[idx].item_name = $(this).val();
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
		};

		function update_row_amount($c, idx, it) {
			const amt = (it.qty || 0) * (it.rate || 0);
			$c.find(`tbody tr:eq(${idx}) .cm-po-item-amount`).text(format_currency(amt));
		}

		// Start with empty items list; user selects from Material Request or adds items manually
		items = [];
		dialog.show();
		render_dialog_items();
	}
}

function po_status_pill(status) {
	if (!status) return "";
	const map = {
		"Draft": "draft",
		"To Receive and Bill": "to-receive-and-bill",
		"To Receive": "to-receive",
		"To Bill": "to-bill",
		"Completed": "completed",
		"Cancelled": "cancelled",
		"Closed": "closed",
	};
	const css_class = map[status] || status.toLowerCase().replace(/\s+/g, "-");
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
