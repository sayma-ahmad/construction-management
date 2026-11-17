const CM_VENDORS_SUPPLIER_GROUP = "Construction Vendors";
const CM_SPECIALIZATIONS = [
	"Cement & Concrete",
	"Steel",
	"Sand & Aggregates",
	"Masonry",
	"Electrical",
	"Plumbing",
	"Construction Equipment",
	"Civil Works",
];
const CM_VENDOR_STATUSES = ["Active", "On Hold", "Disabled"];

frappe.pages["construction-vendors"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Vendors"),
		single_column: true,
	});

	page.set_secondary_action(__("Workspace"), () => frappe.set_route("construction-management"));

	frappe.require("/assets/construction_management/css/construction_management.css", () => {
		wrapper.vendor_list = new VendorList(page);
	});
};

frappe.pages["construction-vendors"].on_page_show = function (wrapper) {
	wrapper.vendor_list?.refresh();
};

class VendorList {
	constructor(page) {
		this.page = page;
		this.vendors = [];
		this.vendor_types = [];

		if (frappe.model.can_create("Supplier")) {
			page.set_primary_action(__("New Vendor"), () => this.show_new_vendor_dialog(), "add");
		}

		this.make_filters();
		this.make_layout();
		this.refresh();
	}

	make_filters() {
		this.search = this.page.add_field({
			fieldname: "search",
			label: __("Search vendor name or supplier ID"),
			fieldtype: "Data",
		});
		this.search.$input.on("input", frappe.utils.debounce(() => this.render(), 200));
		$(this.search.wrapper).removeClass("col-md-2").addClass("col-md-4");

		this.vendor_type = this.page.add_field({
			fieldname: "vendor_type",
			label: __("Vendor Type"),
			fieldtype: "Select",
			options: [""],
			change: () => this.render(),
		});

		this.specialization = this.page.add_field({
			fieldname: "specialization",
			label: __("Specialization"),
			fieldtype: "Select",
			options: ["", ...CM_SPECIALIZATIONS],
			change: () => this.render(),
		});

		this.status = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", ...CM_VENDOR_STATUSES],
			change: () => this.render(),
		});
	}

	make_layout() {
		this.$wrapper = $(`
			<div class="cm-vendors">
				<div class="cm-tasks-card">
					<div class="cm-tasks-toolbar">
						<span class="cm-tasks-count"></span>
						<button class="btn btn-xs btn-default cm-vendors-clear">${__("Clear Filters")}</button>
					</div>
					<div class="cm-tasks-table-wrapper">
						<table class="cm-tasks-table">
							<thead>
								<tr>
									<th>${__("Vendor Name")}</th>
									<th>${__("Supplier ID")}</th>
									<th>${__("Vendor Type")}</th>
									<th>${__("Specialization")}</th>
									<th>${__("Contact Person")}</th>
									<th>${__("Phone Number")}</th>
									<th>${__("Email Address")}</th>
									<th>${__("Location")}</th>
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

		this.$wrapper.on("click", "tbody tr[data-supplier]", (e) => {
			frappe.set_route("Form", "Supplier", $(e.currentTarget).attr("data-supplier"));
		});

		this.$wrapper.find(".cm-vendors-clear").on("click", () => {
			this.search.set_value("");
			this.vendor_type.set_value("");
			this.specialization.set_value("");
			this.status.set_value("");
			this.render();
		});
	}

	async refresh() {
		this.show_message(__("Loading vendors..."));

		const groups = await frappe.db.get_list("Supplier Group", {
			filters: { parent_supplier_group: CM_VENDORS_SUPPLIER_GROUP },
			order_by: "name asc",
			limit: 100,
		});
		this.vendor_types = groups.map((group) => group.name);

		this.vendor_type.df.options = ["", ...this.vendor_types];
		this.vendor_type.refresh();

		const suppliers = this.vendor_types.length
			? await frappe.db.get_list("Supplier", {
					filters: { supplier_group: ["in", this.vendor_types] },
					fields: [
						"name",
						"supplier_name",
						"supplier_group",
						"cm_specialization",
						"supplier_primary_contact",
						"supplier_primary_address",
						"mobile_no",
						"email_id",
						"disabled",
						"on_hold",
					],
					order_by: "supplier_name asc",
					limit: 1000,
			  })
			: [];

		const [contacts, addresses] = await Promise.all([
			get_records_by_name("Contact", suppliers, "supplier_primary_contact", [
				"name",
				"full_name",
				"mobile_no",
				"phone",
				"email_id",
			]),
			get_records_by_name("Address", suppliers, "supplier_primary_address", [
				"name",
				"city",
				"state",
			]),
		]);

		this.vendors = suppliers.map((supplier) => to_vendor(supplier, contacts, addresses));
		this.render();
	}

	get_filtered() {
		const search = (this.search.get_value() || "").trim().toLowerCase();
		const vendor_type = this.vendor_type.get_value();
		const specialization = this.specialization.get_value();
		const status = this.status.get_value();

		return this.vendors.filter((v) => {
			const matches_search =
				!search || [v.supplier_name, v.name].some((value) => (value || "").toLowerCase().includes(search));
			return (
				matches_search &&
				(!vendor_type || v.supplier_group === vendor_type) &&
				(!specialization || v.cm_specialization === specialization) &&
				(!status || v.status === status)
			);
		});
	}

	render() {
		const vendors = this.get_filtered();

		this.$wrapper
			.find(".cm-tasks-count")
			.text(__("Showing {0} of {1} vendors", [vendors.length, this.vendors.length]));

		if (!vendors.length) {
			this.show_message(
				this.vendors.length
					? __("No vendors match the selected filters.")
					: __("No construction vendors found.")
			);
			return;
		}

		this.$wrapper.find("tbody").html(vendors.map(vendor_row).join(""));
	}

	show_message(message) {
		this.$wrapper.find("tbody").html(`<tr><td colspan="10" class="cm-tasks-empty">${message}</td></tr>`);
	}

	show_new_vendor_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: __("New Vendor"),
			size: "large",
			fields: [
				{ fieldtype: "Section Break", label: __("Basic Information") },
				{ fieldname: "supplier_name", fieldtype: "Data", label: __("Vendor Name"), reqd: 1 },
				{ fieldtype: "Column Break" },
				{
					fieldname: "supplier_type",
					fieldtype: "Select",
					options: ["Company", "Individual", "Partnership"],
					default: "Company",
					label: __("Supplier Type"),
					reqd: 1,
				},
				{ fieldtype: "Section Break", label: __("Vendor Classification") },
				{
					fieldname: "supplier_group",
					fieldtype: "Link",
					options: "Supplier Group",
					label: __("Vendor Type"),
					reqd: 1,
					get_query: () => ({ filters: { parent_supplier_group: CM_VENDORS_SUPPLIER_GROUP } }),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "cm_specialization",
					fieldtype: "Select",
					options: ["", ...CM_SPECIALIZATIONS],
					label: __("Specialization"),
					reqd: 1,
				},
				{ fieldtype: "Section Break", label: __("Contact Information") },
				{ fieldname: "contact_person", fieldtype: "Data", label: __("Contact Person"), reqd: 1 },
				{ fieldname: "mobile_no", fieldtype: "Data", options: "Phone", label: __("Phone Number"), reqd: 1 },
				{ fieldtype: "Column Break" },
				{ fieldname: "email_id", fieldtype: "Data", options: "Email", label: __("Email Address") },
				{ fieldtype: "Section Break", label: __("Address Details") },
				{ fieldname: "address_line1", fieldtype: "Data", label: __("Address Line 1"), reqd: 1 },
				{ fieldname: "city", fieldtype: "Data", label: __("City"), reqd: 1 },
				{ fieldname: "state", fieldtype: "Data", label: __("State") },
				{ fieldtype: "Column Break" },
				{ fieldname: "pincode", fieldtype: "Data", label: __("Postal Code") },
				{
					fieldname: "country",
					fieldtype: "Link",
					options: "Country",
					label: __("Country"),
					default: frappe.defaults.get_default("country"),
					reqd: 1,
				},
			],
			primary_action_label: __("Create"),
			primary_action: (values) => {
				frappe.db.insert(new_supplier_doc(values)).then((doc) => {
					dialog.hide();
					frappe.show_alert({
						message: __("Vendor {0} created", [doc.supplier_name]),
						indicator: "green",
					});
					this.refresh();
				});
			},
		});
		dialog.show();
	}
}

// The contact and address keys are the standard Supplier quick-entry values:
// ERPNext creates the primary Contact and Address from them on insert.
function new_supplier_doc(values) {
	const { contact_person, ...supplier } = values;
	const [first_name, ...rest] = contact_person.trim().split(/\s+/);
	return {
		doctype: "Supplier",
		...supplier,
		first_name,
		last_name: rest.join(" "),
	};
}

async function get_records_by_name(doctype, suppliers, link_field, fields) {
	const names = [...new Set(suppliers.map((s) => s[link_field]).filter(Boolean))];
	if (!names.length) return {};

	const records = await frappe.db.get_list(doctype, {
		filters: { name: ["in", names] },
		fields,
		limit: names.length,
	});
	return Object.fromEntries(records.map((record) => [record.name, record]));
}

function to_vendor(supplier, contacts, addresses) {
	const contact = contacts[supplier.supplier_primary_contact] || {};
	const address = addresses[supplier.supplier_primary_address] || {};
	return {
		...supplier,
		contact_person: contact.full_name || "",
		phone: contact.mobile_no || contact.phone || supplier.mobile_no || "",
		email: contact.email_id || supplier.email_id || "",
		location: [address.city, address.state].filter(Boolean).join(", "),
		status: vendor_status(supplier),
	};
}

function vendor_status(supplier) {
	if (supplier.disabled) return "Disabled";
	if (supplier.on_hold) return "On Hold";
	return "Active";
}

function vendor_row(vendor) {
	const esc = frappe.utils.escape_html;
	const status_class = vendor.status.toLowerCase().replace(/\s+/g, "-");
	return `
		<tr data-supplier="${esc(vendor.name)}" title="${__("Open vendor")}">
			<td class="cm-tasks-name">${esc(vendor.supplier_name)}</td>
			<td class="cm-tasks-muted">${esc(vendor.name)}</td>
			<td class="cm-tasks-nowrap">${esc(__(vendor.supplier_group))}</td>
			<td class="cm-tasks-nowrap">${esc(vendor.cm_specialization ? __(vendor.cm_specialization) : "")}</td>
			<td class="cm-tasks-nowrap">${esc(vendor.contact_person)}</td>
			<td class="cm-tasks-nowrap">${esc(vendor.phone)}</td>
			<td>${esc(vendor.email)}</td>
			<td class="cm-tasks-nowrap">${esc(vendor.location)}</td>
			<td><span class="cm-status cm-status-${status_class}">${__(vendor.status)}</span></td>
			<td class="cm-tasks-open">${frappe.utils.icon("right", "sm")}</td>
		</tr>
	`;
}
