const CM_MATERIALS_ITEM_GROUP = "Construction Materials";
const CM_MATERIAL_TYPES = ["Civil", "Structural", "MEP", "Finishing", "Consumable"];

frappe.pages["construction-materials"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Material Master"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	frappe.require("/assets/construction_management/css/construction_management.css", () => {
		wrapper.material_list = new MaterialList(page);
	});
};

frappe.pages["construction-materials"].on_page_show = function (wrapper) {
	wrapper.material_list?.refresh();
};

class MaterialList {
	constructor(page) {
		this.page = page;
		this.materials = [];
		this.categories = [];

		if (frappe.model.can_create("Item")) {
			page.set_primary_action(__("New Material"), () => this.show_new_material_dialog(), "add");
		}

		this.make_filters();
		this.make_layout();
		this.refresh();
	}

	make_filters() {
		this.search = this.page.add_field({
			fieldname: "search",
			label: __("Search material name or item code"),
			fieldtype: "Data",
		});
		this.search.$input.on("input", frappe.utils.debounce(() => this.render(), 200));
		$(this.search.wrapper).removeClass("col-md-2").addClass("col-md-4");

		this.category = this.page.add_field({
			fieldname: "category",
			label: __("Material Category"),
			fieldtype: "Select",
			options: [""],
			change: () => this.render(),
		});

		this.material_type = this.page.add_field({
			fieldname: "material_type",
			label: __("Material Type"),
			fieldtype: "Select",
			options: ["", ...CM_MATERIAL_TYPES],
			change: () => this.render(),
		});

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Active", "Disabled"],
			change: () => this.render(),
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-materials">
				<div class="cm-tasks-card">
					<div class="cm-tasks-toolbar">
						<span class="cm-tasks-count"></span>
						<button class="btn btn-xs btn-default cm-materials-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-tasks-table-wrapper">
						<table class="cm-tasks-table">
							<thead>
								<tr>
									<th>${__("Material Name")}</th>
									<th>${__("Item Code")}</th>
									<th>${__("Material Category")}</th>
									<th>${__("Material Type")}</th>
									<th>${__("Unit of Measurement")}</th>
									<th>${__("Material Grade")}</th>
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

		this.$wrapper.on("click", "tbody tr[data-item]", (e) => {
			frappe.set_route("Form", "Item", $(e.currentTarget).attr("data-item"));
		});

		this.$wrapper.find(".cm-materials-clear").on("click", () => {
			this.search.set_value("");
			this.category.set_value("");
			this.material_type.set_value("");
			this.status.set_value("");
			this.render();
		});
	}

	async refresh() {
		this.show_message(__("Loading materials..."));

		const groups = await frappe.db.get_list("Item Group", {
			filters: { parent_item_group: CM_MATERIALS_ITEM_GROUP },
			order_by: "name asc",
			limit: 100,
		});
		this.categories = groups.map((group) => group.name);

		this.category.df.options = ["", ...this.categories];
		this.category.refresh();

		this.materials = this.categories.length
			? await frappe.db.get_list("Item", {
					filters: { item_group: ["in", this.categories] },
					fields: [
						"name",
						"item_name",
						"item_group",
						"stock_uom",
						"cm_material_type",
						"cm_material_grade",
						"disabled",
					],
					order_by: "item_name asc",
					limit: 1000,
			  })
			: [];

		this.render();
	}

	get_filtered() {
		const search = (this.search.get_value() || "").trim().toLowerCase();
		const category = this.category.get_value();
		const material_type = this.material_type.get_value();
		const status = this.status.get_value();

		return this.materials.filter((m) => {
			const matches_search =
				!search || [m.item_name, m.name].some((value) => (value || "").toLowerCase().includes(search));
			return (
				matches_search &&
				(!category || m.item_group === category) &&
				(!material_type || m.cm_material_type === material_type) &&
				(!status || material_status(m) === status)
			);
		});
	}

	render() {
		const materials = this.get_filtered();

		this.$wrapper
			.find(".cm-tasks-count")
			.text(__("Showing {0} of {1} materials", [materials.length, this.materials.length]));

		if (!materials.length) {
			this.show_message(
				this.materials.length
					? __("No materials match the selected filters.")
					: __("No construction materials found.")
			);
			return;
		}

		this.$wrapper.find("tbody").html(materials.map(material_row).join(""));
	}

	show_message(message) {
		this.$wrapper.find("tbody").html(`<tr><td colspan="8" class="cm-tasks-empty">${message}</td></tr>`);
	}

	show_new_material_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: __("New Material"),
			size: "large",
			fields: [
				{ fieldtype: "Section Break", label: __("Material Details") },
				{ fieldname: "item_name", fieldtype: "Data", label: __("Material Name"), reqd: 1 },
				{ fieldname: "item_code", fieldtype: "Data", label: __("Item Code"), reqd: 1 },
				{ fieldtype: "Column Break" },
				{
					fieldname: "item_group",
					fieldtype: "Link",
					options: "Item Group",
					label: __("Material Category"),
					reqd: 1,
					get_query: () => ({ filters: { parent_item_group: CM_MATERIALS_ITEM_GROUP } }),
				},
				{
					fieldname: "stock_uom",
					fieldtype: "Link",
					options: "UOM",
					label: __("Unit of Measurement"),
					reqd: 1,
				},
				{ fieldtype: "Section Break", label: __("Construction Details") },
				{
					fieldname: "cm_material_type",
					fieldtype: "Select",
					options: ["", ...CM_MATERIAL_TYPES],
					label: __("Material Type"),
					reqd: 1,
				},
				{ fieldname: "cm_material_grade", fieldtype: "Data", label: __("Material Grade") },
				{ fieldtype: "Column Break" },
				{ fieldname: "cm_specifications", fieldtype: "Small Text", label: __("Specifications") },
			],
			primary_action_label: __("Create"),
			primary_action: (values) => {
				frappe.db
					.insert({ doctype: "Item", is_stock_item: 1, ...values })
					.then((doc) => {
						dialog.hide();
						frappe.show_alert({
							message: __("Material {0} created", [doc.item_name]),
							indicator: "green",
						});
						this.refresh();
					});
			},
		});
		dialog.show();
	}
}

function material_status(material) {
	return material.disabled ? "Disabled" : "Active";
}

function material_row(material) {
	const esc = frappe.utils.escape_html;
	const status = material_status(material);
	return `
		<tr data-item="${esc(material.name)}" title="${__("Open material")}">
			<td class="cm-tasks-name">${esc(material.item_name)}</td>
			<td class="cm-tasks-muted">${esc(material.name)}</td>
			<td class="cm-tasks-nowrap">${esc(__(material.item_group))}</td>
			<td>${esc(material.cm_material_type ? __(material.cm_material_type) : "")}</td>
			<td class="cm-tasks-nowrap">${esc(__(material.stock_uom))}</td>
			<td class="cm-tasks-nowrap">${esc(material.cm_material_grade || "")}</td>
			<td><span class="cm-status cm-status-${status.toLowerCase()}">${__(status)}</span></td>
			<td class="cm-tasks-open">${frappe.utils.icon("right", "sm")}</td>
		</tr>
	`;
}
