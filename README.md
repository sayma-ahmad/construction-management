# Construction Management ERP App

Construction management features built on Frappe v15 / ERPNext v15.

## Generating Sample Construction Data (Development / Demo Sites)

To populate a development or demo site with an idempotent, linked set of sample construction records (materials, reorder levels, vendors, projects, phase/leaf tasks, daily progress reports, issues, material requests, purchase orders, purchase receipts, stock transactions, and unpaid purchase invoices):

```bash
bench --site <site> execute construction_management.demo_data.create_sample_data
```

Optionally pass an explicit `company` or `warehouse`:

```bash
bench --site <site> execute construction_management.demo_data.create_sample_data --kwargs '{"company": "My Company", "warehouse": "Stores - MC"}'
```

Individual master-data sample commands are also available:

```bash
bench --site <site> execute construction_management.materials.create_sample_materials
bench --site <site> execute construction_management.vendors.create_sample_vendors
```
