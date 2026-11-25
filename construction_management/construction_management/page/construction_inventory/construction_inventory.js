// Copyright (c) 2026, TechnoTribes and contributors
// See license.txt

const CM_INVENTORY_ASSETS = ["/assets/construction_management/css/construction_management.css"];

frappe.pages["construction-inventory"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Construction Inventory"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));
	page.add_inner_button(__("Refresh"), () => wrapper.inventory_view?.refresh());

	if (frappe.model.can_create("Stock Entry")) {
		page.set_primary_action(
			__("Transfer Stock"),
			() => wrapper.inventory_view?.show_stock_transfer_dialog(),
			"add"
		);
	}

	frappe.require(CM_INVENTORY_ASSETS, () => {
		wrapper.inventory_view = new ConstructionInventoryView(page);
	});
};

frappe.pages["construction-inventory"].on_page_show = function (wrapper) {
	if (wrapper.inventory_view) {
		wrapper.inventory_view.refresh();
	}
};

class ConstructionInventoryView {
	constructor(page) {
		this.page = page;
		this.current_tab = "summary";
		this.warehouses = [];
		this.categories = [];
		this.make_layout();
		this.load_warehouses();
		this.refresh();
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-inventory">
				<!-- KPI Cards -->
				<div class="cm-inventory-kpis">
					<div class="cm-inv-kpi-card">
						<div class="cm-inv-kpi-icon blue">${frappe.utils.icon("assets", "md")}</div>
						<div class="cm-inv-kpi-content">
							<span class="cm-inv-kpi-label">${__("Total Materials")}</span>
							<span class="cm-inv-kpi-value" data-kpi="total_items">-</span>
							<span class="cm-inv-kpi-note" data-kpi="in_stock_note">-</span>
						</div>
					</div>
					<div class="cm-inv-kpi-card">
						<div class="cm-inv-kpi-icon green">${frappe.utils.icon("solid-success", "md")}</div>
						<div class="cm-inv-kpi-content">
							<span class="cm-inv-kpi-label">${__("Total Valuation")}</span>
							<span class="cm-inv-kpi-value" data-kpi="total_valuation">-</span>
							<span class="cm-inv-kpi-note" data-kpi="valuation_note">${__("Base Currency")}</span>
						</div>
					</div>
					<div class="cm-inv-kpi-card">
						<div class="cm-inv-kpi-icon yellow">${frappe.utils.icon("solid-warning", "md")}</div>
						<div class="cm-inv-kpi-content">
							<span class="cm-inv-kpi-label">${__("Low Stock Items")}</span>
							<span class="cm-inv-kpi-value" data-kpi="low_stock_items">-</span>
							<span class="cm-inv-kpi-note" data-kpi="low_stock_note">${__("Below reorder level")}</span>
						</div>
					</div>
					<div class="cm-inv-kpi-card">
						<div class="cm-inv-kpi-icon purple">${frappe.utils.icon("warehouse", "md") || frappe.utils.icon("folder", "md")}</div>
						<div class="cm-inv-kpi-content">
							<span class="cm-inv-kpi-label">${__("Active Stores")}</span>
							<span class="cm-inv-kpi-value" data-kpi="warehouse_count">-</span>
							<span class="cm-inv-kpi-note">${__("Central & Site Stores")}</span>
						</div>
					</div>
				</div>

				<!-- Navigation Tabs -->
				<div class="cm-inventory-tabs">
					<div class="cm-inventory-tab active" data-tab="summary">${__("Material Stock Summary")}</div>
					<div class="cm-inventory-tab" data-tab="breakdown">${__("Warehouse Breakdown")}</div>
					<div class="cm-inventory-tab" data-tab="transfers">${__("Transfer History")}</div>
				</div>

				<!-- Toolbar / Filters -->
				<div class="cm-tasks-card">
					<div class="cm-tasks-toolbar cm-inv-toolbar">
						<div class="row w-100 m-0" id="cm-inv-filters">
							<div class="col-md-4 p-1">
								<input type="text" class="form-control input-sm cm-inv-search" placeholder="${__("Search item code or material name...")}">
							</div>
							<div class="col-md-3 p-1">
								<select class="form-control input-sm cm-inv-warehouse-filter">
									<option value="">${__("All Warehouses")}</option>
								</select>
							</div>
							<div class="col-md-3 p-1">
								<select class="form-control input-sm cm-inv-status-filter">
									<option value="All">${__("All Statuses")}</option>
									<option value="In Stock">${__("In Stock")}</option>
									<option value="Low Stock">${__("Low Stock")}</option>
									<option value="Out of Stock">${__("Out of Stock")}</option>
								</select>
							</div>
							<div class="col-md-2 p-1 text-right">
								<button class="btn btn-xs btn-default cm-inv-clear mt-1">${__("Clear")}</button>
							</div>
						</div>
					</div>

					<!-- Table Content Area -->
					<div class="cm-tasks-table-wrapper">
						<div id="cm-inv-table-container">
							<div class="text-center p-4 text-muted">${__("Loading inventory data...")}</div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		// Event handlers
		this.$wrapper.find(".cm-inventory-tab").on("click", (e) => {
			this.$wrapper.find(".cm-inventory-tab").removeClass("active");
			const $tab = $(e.currentTarget);
			$tab.addClass("active");
			this.current_tab = $tab.data("tab");
			this.render_current_tab();
		});

		this.$wrapper.find(".cm-inv-search").on(
			"input",
			frappe.utils.debounce(() => this.refresh(), 300)
		);
		this.$wrapper.find(".cm-inv-warehouse-filter, .cm-inv-status-filter").on("change", () => {
			this.refresh();
		});
		this.$wrapper.find(".cm-inv-clear").on("click", () => {
			this.$wrapper.find(".cm-inv-search").val("");
			this.$wrapper.find(".cm-inv-warehouse-filter").val("");
			this.$wrapper.find(".cm-inv-status-filter").val("All");
			this.refresh();
		});
	}

	load_warehouses() {
		frappe.call({
			method: "construction_management.inventory.get_warehouses",
			callback: (r) => {
				if (r.message) {
					this.warehouses = r.message;
					const $select = this.$wrapper.find(".cm-inv-warehouse-filter");
					$select.empty().append(`<option value="">${__("All Warehouses")}</option>`);
					this.warehouses.forEach((wh) => {
						const tag = wh.cm_is_site_warehouse ? ` [${__("Site")}]` : "";
						$("<option>")
							.val(wh.name)
							.text(`${wh.warehouse_name || wh.name}${tag}`)
							.appendTo($select);
					});
				}
			},
		});
	}

	refresh() {
		this._req_seq = (this._req_seq || 0) + 1;
		const current_seq = this._req_seq;

		const warehouse = this.$wrapper.find(".cm-inv-warehouse-filter").val();
		const status = this.$wrapper.find(".cm-inv-status-filter").val();
		const search = this.$wrapper.find(".cm-inv-search").val();

		frappe.call({
			method: "construction_management.inventory.get_inventory_summary",
			args: { warehouse, status, search },
			callback: (r) => {
				if (current_seq !== this._req_seq) return;
				if (r.message) {
					this.data = r.message;
					this.update_kpis(r.message.kpis);
					this.render_current_tab();
				}
			},
		});
	}

	update_kpis(kpis) {
		if (!kpis) return;
		this.$wrapper.find('[data-kpi="total_items"]').text(kpis.total_items);
		this.$wrapper
			.find('[data-kpi="in_stock_note"]')
			.text(`${kpis.in_stock_items} in stock, ${kpis.out_of_stock_items} out`);

		const currency = kpis.currency || frappe.boot.sysdefaults.currency || "INR";
		this.$wrapper.find('[data-kpi="total_valuation"]').text(
			format_currency(kpis.total_valuation, currency)
		);
		this.$wrapper.find('[data-kpi="low_stock_items"]').text(kpis.low_stock_items);
		this.$wrapper.find('[data-kpi="warehouse_count"]').text(kpis.warehouse_count);
	}

	render_current_tab() {
		if (this.current_tab === "summary") {
			this.render_summary_table();
		} else if (this.current_tab === "breakdown") {
			this.render_breakdown_table();
		} else if (this.current_tab === "transfers") {
			this.render_transfers_table();
		}
	}

	render_summary_table() {
		const items = this.data?.items || [];
		const currency = this.data?.kpis?.currency || "INR";

		if (items.length === 0) {
			this.$wrapper.find("#cm-inv-table-container").html(`
				<div class="text-center p-5 text-muted">
					<p>${__("No stock records match the selected filters.")}</p>
				</div>
			`);
			return;
		}

		let html = `
			<table class="cm-tasks-table table table-hover">
				<thead>
					<tr>
						<th>${__("Material Name")}</th>
						<th>${__("Item Code")}</th>
						<th>${__("Category")}</th>
						<th>${__("UOM")}</th>
						<th class="text-right">${__("Actual Stock")}</th>
						<th class="text-right">${__("Available Qty")}</th>
						<th class="text-right">${__("Reserved")}</th>
						<th class="text-right">${__("Valuation Rate")}</th>
						<th class="text-right">${__("Stock Value")}</th>
						<th class="text-center">${__("Status")}</th>
					</tr>
				</thead>
				<tbody>
		`;

		items.forEach((item) => {
			const badgeClass = `cm-status cm-status-${item.status.toLowerCase().replace(/\s+/g, "-")}`;

			html += `
				<tr data-item="${frappe.utils.escape_html(item.item_code)}">
					<td class="cm-tasks-name">
						<b>${frappe.utils.escape_html(item.item_name)}</b>
						${item.material_grade ? `<small class="text-muted d-block">${frappe.utils.escape_html(item.material_grade)}</small>` : ""}
					</td>
					<td class="cm-tasks-muted"><a href="/app/item/${encodeURIComponent(item.item_code)}">${frappe.utils.escape_html(item.item_code)}</a></td>
					<td>${frappe.utils.escape_html(item.item_group || "")}</td>
					<td>${frappe.utils.escape_html(item.stock_uom || "")}</td>
					<td class="text-right font-weight-bold">${format_number(item.actual_qty, null, 2)}</td>
					<td class="text-right text-success font-weight-bold">${format_number(item.available_qty, null, 2)}</td>
					<td class="text-right text-muted">${format_number(item.reserved_qty, null, 2)}</td>
					<td class="text-right">${format_currency(item.valuation_rate, currency)}</td>
					<td class="text-right font-weight-bold">${format_currency(item.stock_value, currency)}</td>
					<td class="text-center"><span class="${badgeClass}">${__(item.status)}</span></td>
				</tr>
			`;
		});

		html += `</tbody></table>`;
		this.$wrapper.find("#cm-inv-table-container").html(html);
	}

	render_breakdown_table() {
		this._breakdown_seq = (this._breakdown_seq || 0) + 1;
		const current_seq = this._breakdown_seq;

		const warehouse = this.$wrapper.find(".cm-inv-warehouse-filter").val();
		this.$wrapper.find("#cm-inv-table-container").html(`
			<div class="text-center p-4 text-muted">${__("Loading warehouse breakdown...")}</div>
		`);

		frappe.call({
			method: "construction_management.inventory.get_warehouse_stock_breakdown",
			args: { warehouse },
			callback: (r) => {
				if (current_seq !== this._breakdown_seq) return;
				const rows = r.message || [];
				if (rows.length === 0) {
					this.$wrapper.find("#cm-inv-table-container").html(`
						<div class="text-center p-5 text-muted">
							<p>${__("No stock balances in selected warehouse.")}</p>
						</div>
					`);
					return;
				}

				let html = `
					<table class="cm-tasks-table table table-hover">
						<thead>
							<tr>
								<th>${__("Warehouse")}</th>
								<th>${__("Type / Site")}</th>
								<th>${__("Material Name")}</th>
								<th>${__("Item Code")}</th>
								<th>${__("UOM")}</th>
								<th class="text-right">${__("Actual Qty")}</th>
								<th class="text-right">${__("Available Qty")}</th>
								<th class="text-right">${__("Reserved Qty")}</th>
								<th class="text-right">${__("Valuation Rate")}</th>
								<th class="text-right">${__("Total Value")}</th>
							</tr>
						</thead>
						<tbody>
				`;

				const currency = frappe.boot.sysdefaults.currency || "INR";
				rows.forEach((row) => {
					const siteInfo = row.is_site_warehouse
						? `<span class="badge badge-primary">${__("Site")}</span> ${row.project ? frappe.utils.escape_html(row.project) : ""}`
						: `<span class="badge badge-secondary">${__("Store")}</span>`;

					html += `
						<tr>
							<td class="font-weight-bold"><a href="/app/warehouse/${encodeURIComponent(row.warehouse)}">${frappe.utils.escape_html(row.warehouse_name || row.warehouse)}</a></td>
							<td>${siteInfo}</td>
							<td>${frappe.utils.escape_html(row.item_name)}</td>
							<td class="cm-tasks-muted">${frappe.utils.escape_html(row.item_code)}</td>
							<td>${frappe.utils.escape_html(row.stock_uom)}</td>
							<td class="text-right font-weight-bold">${format_number(row.actual_qty, null, 2)}</td>
							<td class="text-right text-success font-weight-bold">${format_number(row.available_qty, null, 2)}</td>
							<td class="text-right text-muted">${format_number(row.reserved_qty, null, 2)}</td>
							<td class="text-right">${format_currency(row.valuation_rate, currency)}</td>
							<td class="text-right font-weight-bold">${format_currency(row.stock_value, currency)}</td>
						</tr>
					`;
				});

				html += `</tbody></table>`;
				this.$wrapper.find("#cm-inv-table-container").html(html);
			},
		});
	}

	render_transfers_table() {
		this._transfers_seq = (this._transfers_seq || 0) + 1;
		const current_seq = this._transfers_seq;

		this.$wrapper.find("#cm-inv-table-container").html(`
			<div class="text-center p-4 text-muted">${__("Loading stock transfers...")}</div>
		`);

		frappe.call({
			method: "construction_management.inventory.get_stock_transfers",
			callback: (r) => {
				if (current_seq !== this._transfers_seq) return;
				const transfers = r.message || [];
				if (transfers.length === 0) {
					this.$wrapper.find("#cm-inv-table-container").html(`
						<div class="text-center p-5 text-muted">
							<p>${__("No stock transfer entries recorded yet.")}</p>
						</div>
					`);
					return;
				}

				let html = `
					<table class="cm-tasks-table table table-hover">
						<thead>
							<tr>
								<th>${__("Transfer Entry")}</th>
								<th>${__("Date")}</th>
								<th>${__("Source Warehouse")}</th>
								<th>${__("Destination Warehouse")}</th>
								<th>${__("Project")}</th>
								<th class="text-right">${__("Items")}</th>
								<th class="text-right">${__("Total Qty")}</th>
								<th class="text-center">${__("Status")}</th>
							</tr>
						</thead>
						<tbody>
				`;

				transfers.forEach((t) => {
					html += `
						<tr>
							<td class="font-weight-bold"><a href="/app/stock-entry/${encodeURIComponent(t.name)}">${frappe.utils.escape_html(t.name)}</a></td>
							<td>${frappe.datetime.str_to_user(t.posting_date)}</td>
							<td>${frappe.utils.escape_html(t.from_warehouse || "-")}</td>
							<td>${frappe.utils.escape_html(t.to_warehouse || "-")}</td>
							<td>${t.project ? frappe.utils.escape_html(t.project) : '<span class="text-muted">—</span>'}</td>
							<td class="text-right">${t.item_count}</td>
							<td class="text-right font-weight-bold">${format_number(t.total_qty, null, 2)}</td>
							<td class="text-center"><span class="badge ${t.status === 'Submitted' ? 'badge-success' : 'badge-warning'}">${__(t.status)}</span></td>
						</tr>
					`;
				});

				html += `</tbody></table>`;
				this.$wrapper.find("#cm-inv-table-container").html(html);
			},
		});
	}

	show_stock_transfer_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: __("New Material Stock Transfer"),
			size: "large",
			fields: [
				{
					fieldname: "from_warehouse",
					fieldtype: "Link",
					options: "Warehouse",
					label: __("Source Warehouse (From)"),
					reqd: 1,
					get_query: () => ({ filters: { is_group: 0 } }),
					change: () => this.update_dialog_availability(dialog),
				},
				{
					fieldname: "to_warehouse",
					fieldtype: "Link",
					options: "Warehouse",
					label: __("Target Warehouse (To)"),
					reqd: 1,
					get_query: () => ({ filters: { is_group: 0 } }),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "project",
					fieldtype: "Link",
					options: "Project",
					label: __("Associated Construction Project"),
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Remarks / Transfer Reason"),
				},
				{ fieldtype: "Section Break", label: __("Transfer Material Details") },
				{
					fieldname: "item_code",
					fieldtype: "Link",
					options: "Item",
					label: __("Material Item"),
					reqd: 1,
					get_query: () => ({ filters: { is_stock_item: 1, disabled: 0 } }),
					change: () => this.update_dialog_availability(dialog),
				},
				{
					fieldname: "available_info",
					fieldtype: "HTML",
					label: __("Available Stock"),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "qty",
					fieldtype: "Float",
					label: __("Transfer Quantity"),
					reqd: 1,
				},
				{
					fieldname: "submit_entry",
					fieldtype: "Check",
					label: __("Submit Transfer Immediately"),
					default: 1,
				},
			],
			primary_action_label: __("Execute Transfer"),
			primary_action: (values) => {
				if (!values.from_warehouse || !values.to_warehouse) {
					frappe.msgprint(__("Please select both source and target warehouses."));
					return;
				}
				if (values.from_warehouse === values.to_warehouse) {
					frappe.msgprint(__("Source and target warehouse cannot be the same."));
					return;
				}
				if (flt(values.qty) <= 0) {
					frappe.msgprint(__("Transfer quantity must be greater than zero."));
					return;
				}

				const items = [
					{
						item_code: values.item_code,
						qty: flt(values.qty),
					},
				];

				dialog.get_primary_btn().prop("disabled", true).text(__("Transferring..."));

				frappe.call({
					method: "construction_management.inventory.create_stock_transfer",
					args: {
						from_warehouse: values.from_warehouse,
						to_warehouse: values.to_warehouse,
						items: JSON.stringify(items),
						project: values.project,
						remarks: values.remarks,
						submit: values.submit_entry ? 1 : 0,
					},
					callback: (r) => {
						dialog.get_primary_btn().prop("disabled", false).text(__("Execute Transfer"));
						if (r.message) {
							dialog.hide();
							frappe.show_alert({
								message: __("Stock Transfer {0} created successfully", [r.message.name]),
								indicator: "green",
							});
							this.refresh();
						}
					},
					error: () => {
						dialog.get_primary_btn().prop("disabled", false).text(__("Execute Transfer"));
					},
				});
			},
		});

		dialog.show();
	}

	update_dialog_availability(dialog) {
		const item_code = dialog.get_value("item_code");
		const from_warehouse = dialog.get_value("from_warehouse");

		if (!item_code || !from_warehouse) {
			dialog.fields_dict.available_info.$wrapper.html("");
			return;
		}

		frappe.call({
			method: "construction_management.inventory.get_item_availability",
			args: { item_code, warehouse: from_warehouse },
			callback: (r) => {
				if (r.message) {
					const avail = r.message.available_qty;
					const uom = r.message.stock_uom || "";
					const color = avail > 0 ? "text-success font-weight-bold" : "text-danger font-weight-bold";
					dialog.fields_dict.available_info.$wrapper.html(`
						<div class="mt-2 small ${color}">
							${__("Available in source warehouse")}: ${format_number(avail, null, 2)} ${uom}
						</div>
					`);
				}
			},
		});
	}
}
