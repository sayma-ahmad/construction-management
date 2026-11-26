import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Construction materials are standard ERPNext Items whose Item Group (shown as
# "Material Category") is a child of this group.
MATERIALS_ITEM_GROUP = "Construction Materials"

MATERIAL_CATEGORIES = [
	"Cement & Concrete",
	"Steel",
	"Aggregates",
	"Masonry",
	"Plumbing",
	"Electrical",
]

MATERIAL_TYPES = ["Civil", "Structural", "MEP", "Finishing", "Consumable"]

ITEM_CUSTOM_FIELDS = {
	"Item": [
		{
			"fieldname": "cm_material_section",
			"fieldtype": "Section Break",
			"label": "Construction Material",
			"insert_after": "image",
		},
		{
			"fieldname": "cm_material_type",
			"fieldtype": "Select",
			"label": "Material Type",
			"options": "\n" + "\n".join(MATERIAL_TYPES),
			"insert_after": "cm_material_section",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "cm_material_grade",
			"fieldtype": "Data",
			"label": "Material Grade",
			"insert_after": "cm_material_type",
		},
		{
			"fieldname": "cm_material_column",
			"fieldtype": "Column Break",
			"insert_after": "cm_material_grade",
		},
		{
			"fieldname": "cm_specifications",
			"fieldtype": "Small Text",
			"label": "Specifications",
			"insert_after": "cm_material_column",
		},
	]
}

SAMPLE_MATERIALS = [
	{
		"item_code": "CM-CEM-001",
		"item_name": "OPC Cement 53 Grade",
		"item_group": "Cement & Concrete",
		"stock_uom": "Bag",
		"cm_material_type": "Civil",
		"cm_material_grade": "OPC 53",
		"cm_specifications": "IS 12269, 50 kg bag",
	},
	{
		"item_code": "CM-STL-001",
		"item_name": "TMT Reinforcement Bar 12 mm",
		"item_group": "Steel",
		"stock_uom": "Kg",
		"cm_material_type": "Structural",
		"cm_material_grade": "Fe 500D",
		"cm_specifications": "IS 1786, 12 m length",
	},
	{
		"item_code": "CM-AGG-001",
		"item_name": "River Sand",
		"item_group": "Aggregates",
		"stock_uom": "Cubic Meter",
		"cm_material_type": "Civil",
		"cm_material_grade": "Zone II",
		"cm_specifications": "IS 383 fine aggregate, washed",
	},
	{
		"item_code": "CM-AGG-002",
		"item_name": "Coarse Aggregate 20 mm",
		"item_group": "Aggregates",
		"stock_uom": "Cubic Meter",
		"cm_material_type": "Civil",
		"cm_material_grade": "20 mm",
		"cm_specifications": "IS 383 crushed stone",
	},
	{
		"item_code": "CM-MAS-001",
		"item_name": "Red Clay Brick",
		"item_group": "Masonry",
		"stock_uom": "Nos",
		"cm_material_type": "Civil",
		"cm_material_grade": "Class A",
		"cm_specifications": "IS 1077, 230 x 110 x 75 mm",
	},
	{
		"item_code": "CM-MAS-002",
		"item_name": "Solid Concrete Block 200 mm",
		"item_group": "Masonry",
		"stock_uom": "Nos",
		"cm_material_type": "Civil",
		"cm_material_grade": "Grade A",
		"cm_specifications": "IS 2185, 400 x 200 x 200 mm",
	},
	{
		"item_code": "CM-PLB-001",
		"item_name": "PVC Pipe 110 mm",
		"item_group": "Plumbing",
		"stock_uom": "Meter",
		"cm_material_type": "MEP",
		"cm_material_grade": "SWR Type B",
		"cm_specifications": "IS 13592, supplied in 6 m lengths",
	},
	{
		"item_code": "CM-ELE-001",
		"item_name": "Copper Cable 2.5 sq mm",
		"item_group": "Electrical",
		"stock_uom": "Meter",
		"cm_material_type": "MEP",
		"cm_material_grade": "FR 1.1 kV",
		"cm_specifications": "IS 694, single core, PVC insulated",
	},
]

# HSN codes for the sample materials, used when India Compliance makes HSN/SAC Code mandatory on Items.
SAMPLE_HSN_CODES = {
	"CM-CEM-001": ("25232910", "Ordinary Portland cement"),
	"CM-STL-001": ("72142090", "Bars and rods of iron or non-alloy steel, with indentations"),
	"CM-AGG-001": ("25059000", "Natural sands"),
	"CM-AGG-002": ("25171010", "Pebbles, gravel and broken stone"),
	"CM-MAS-001": ("69041000", "Building bricks"),
	"CM-MAS-002": ("68101190", "Building blocks of cement or concrete"),
	"CM-PLB-001": ("39172390", "Tubes, pipes and hoses of polymers of vinyl chloride"),
	"CM-ELE-001": ("85444999", "Other electric conductors"),
}


def ensure_custom_fields():
	"""Install Item custom fields (schema DDL) when not yet present."""
	create_custom_fields(ITEM_CUSTOM_FIELDS)


def setup():
	"""Run after install and migrate: Item custom fields and material Item Groups."""
	ensure_custom_fields()
	create_material_categories()


def create_material_categories():
	# The root Item Group only exists after the ERPNext setup wizard has run.
	if not frappe.db.exists("Item Group", "All Item Groups"):
		return

	if not frappe.db.exists("Item Group", MATERIALS_ITEM_GROUP):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": MATERIALS_ITEM_GROUP,
				"parent_item_group": "All Item Groups",
				"is_group": 1,
			}
		).insert(ignore_permissions=True)

	for category in MATERIAL_CATEGORIES:
		if not frappe.db.exists("Item Group", category):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": category,
					"parent_item_group": MATERIALS_ITEM_GROUP,
				}
			).insert(ignore_permissions=True)


def create_sample_materials(run_setup=True):
	"""Insert the sample construction materials. Run manually:
	bench --site <site> execute construction_management.materials.create_sample_materials
	"""
	if run_setup:
		setup()
	else:
		create_material_categories()
	if not frappe.db.exists("UOM", "Bag"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Bag", "must_be_whole_number": 1}).insert(
			ignore_permissions=True
		)

	use_hsn = frappe.get_meta("Item").has_field("gst_hsn_code")
	for material in SAMPLE_MATERIALS:
		hsn_code = get_sample_hsn_code(material["item_code"]) if use_hsn else None
		if not frappe.db.exists("Item", material["item_code"]):
			item = {"doctype": "Item", "is_stock_item": 1, **material}
			if hsn_code:
				item["gst_hsn_code"] = hsn_code
			frappe.get_doc(item).insert(ignore_permissions=True)
		elif hsn_code and not frappe.db.get_value("Item", material["item_code"], "gst_hsn_code"):
			frappe.db.set_value("Item", material["item_code"], "gst_hsn_code", hsn_code)


def get_sample_hsn_code(item_code):
	"""Return the sample material's HSN code, creating the GST HSN Code record if the site lacks it."""
	code, description = SAMPLE_HSN_CODES[item_code]
	if frappe.db.exists("DocType", "GST HSN Code") and not frappe.db.exists("GST HSN Code", code):
		frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": code, "description": description}).insert(
			ignore_permissions=True
		)
	return code


def is_material_category(item_group):
	return bool(item_group) and frappe.db.get_value("Item Group", item_group, "parent_item_group") == MATERIALS_ITEM_GROUP


def validate_item(doc, method=None):
	"""Item validate hook: construction materials need a Material Type."""
	if is_material_category(doc.item_group) and not doc.get("cm_material_type"):
		frappe.throw(_("Material Type is required for construction materials."))
