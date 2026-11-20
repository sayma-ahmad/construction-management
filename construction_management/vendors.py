import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Construction vendors are standard ERPNext Suppliers whose Supplier Group (shown as
# "Vendor Type") is a child of this group.
VENDORS_SUPPLIER_GROUP = "Construction Vendors"

VENDOR_TYPES = [
	"Material Supplier",
	"Equipment Supplier",
	"Subcontractor",
	"Service Provider",
]

SPECIALIZATIONS = [
	"Cement & Concrete",
	"Steel",
	"Sand & Aggregates",
	"Masonry",
	"Electrical",
	"Plumbing",
	"Construction Equipment",
	"Civil Works",
]

SUPPLIER_CUSTOM_FIELDS = {
	"Supplier": [
		{
			"fieldname": "cm_specialization",
			"fieldtype": "Select",
			"label": "Specialization",
			"options": "\n" + "\n".join(SPECIALIZATIONS),
			"insert_after": "supplier_group",
			"in_standard_filter": 1,
		},
	]
}

# Contact and address keys are the standard Supplier quick-entry values: ERPNext creates
# the primary Contact and Address from them when the Supplier is inserted.
SAMPLE_VENDORS = [
	{
		"supplier_name": "Apex Cement Traders",
		"supplier_group": "Material Supplier",
		"cm_specialization": "Cement & Concrete",
		"first_name": "Rajesh",
		"last_name": "Sharma",
		"mobile_no": "+91 98220 11001",
		"email_id": "sales@apexcement.example.com",
		"address_line1": "Plot 14, Market Yard Road",
		"city": "Pune",
		"state": "Maharashtra",
		"pincode": "411037",
	},
	{
		"supplier_name": "Ironclad Steel Suppliers",
		"supplier_group": "Material Supplier",
		"cm_specialization": "Steel",
		"first_name": "Anil",
		"last_name": "Mehta",
		"mobile_no": "+91 98220 11002",
		"email_id": "orders@ironcladsteel.example.com",
		"address_line1": "Shed 7, MIDC Bhosari",
		"city": "Pune",
		"state": "Maharashtra",
		"pincode": "411026",
	},
	{
		"supplier_name": "Riverstone Sand & Aggregates",
		"supplier_group": "Material Supplier",
		"cm_specialization": "Sand & Aggregates",
		"first_name": "Suresh",
		"last_name": "Patil",
		"mobile_no": "+91 98220 11003",
		"email_id": "dispatch@riverstone.example.com",
		"address_line1": "Survey No. 52, Quarry Road",
		"city": "Nashik",
		"state": "Maharashtra",
		"pincode": "422010",
	},
	{
		"supplier_name": "Brightline Electricals",
		"supplier_group": "Material Supplier",
		"cm_specialization": "Electrical",
		"first_name": "Priya",
		"last_name": "Nair",
		"mobile_no": "+91 98220 11004",
		"email_id": "contact@brightline.example.com",
		"address_line1": "22, Lamington Road",
		"city": "Mumbai",
		"state": "Maharashtra",
		"pincode": "400007",
	},
	{
		"supplier_name": "FlowRight Plumbing Supplies",
		"supplier_group": "Material Supplier",
		"cm_specialization": "Plumbing",
		"first_name": "Imran",
		"last_name": "Shaikh",
		"mobile_no": "+91 98220 11005",
		"email_id": "sales@flowright.example.com",
		"address_line1": "Shop 3, Station Road",
		"city": "Thane",
		"state": "Maharashtra",
		"pincode": "400601",
	},
	{
		"supplier_name": "Heavylift Equipment Rentals",
		"supplier_group": "Equipment Supplier",
		"cm_specialization": "Construction Equipment",
		"first_name": "Vikram",
		"last_name": "Singh",
		"mobile_no": "+91 98220 11006",
		"email_id": "rentals@heavylift.example.com",
		"address_line1": "Yard 9, Chakan Industrial Area",
		"city": "Pune",
		"state": "Maharashtra",
		"pincode": "410501",
	},
]


def ensure_custom_fields():
	"""Install Supplier custom fields (schema DDL) when not yet present."""
	create_custom_fields(SUPPLIER_CUSTOM_FIELDS)


def setup():
	"""Run after install and migrate: Supplier custom fields and vendor Supplier Groups."""
	ensure_custom_fields()
	create_vendor_types()


def create_vendor_types():
	# The root Supplier Group only exists after the ERPNext setup wizard has run.
	if not frappe.db.exists("Supplier Group", "All Supplier Groups"):
		return

	if not frappe.db.exists("Supplier Group", VENDORS_SUPPLIER_GROUP):
		frappe.get_doc(
			{
				"doctype": "Supplier Group",
				"supplier_group_name": VENDORS_SUPPLIER_GROUP,
				"parent_supplier_group": "All Supplier Groups",
				"is_group": 1,
			}
		).insert(ignore_permissions=True)

	for vendor_type in VENDOR_TYPES:
		if not frappe.db.exists("Supplier Group", vendor_type):
			frappe.get_doc(
				{
					"doctype": "Supplier Group",
					"supplier_group_name": vendor_type,
					"parent_supplier_group": VENDORS_SUPPLIER_GROUP,
				}
			).insert(ignore_permissions=True)


def create_sample_vendors(run_setup=True):
	"""Insert the sample construction vendors. Run manually:
	bench --site <site> execute construction_management.vendors.create_sample_vendors
	"""
	if run_setup:
		setup()
	else:
		create_vendor_types()
	country = frappe.db.get_default("country") or "India"

	for vendor in SAMPLE_VENDORS:
		if not frappe.db.exists("Supplier", {"supplier_name": vendor["supplier_name"]}):
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_type": "Company", "country": country, **vendor}
			).insert(ignore_permissions=True)


def is_vendor_type(supplier_group):
	return (
		bool(supplier_group)
		and frappe.db.get_value("Supplier Group", supplier_group, "parent_supplier_group")
		== VENDORS_SUPPLIER_GROUP
	)


def validate_supplier(doc, method=None):
	"""Supplier validate hook: construction vendors need a Specialization."""
	if is_vendor_type(doc.supplier_group) and not doc.get("cm_specialization"):
		frappe.throw(_("Specialization is required for construction vendors."))
