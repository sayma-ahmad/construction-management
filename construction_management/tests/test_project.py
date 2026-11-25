# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from construction_management.construction_management import project


class TestConstructionProjects(FrappeTestCase):
	"""Tests for Construction Projects listing and location/status/search filters (TUS-04 TC-06)."""

	def setUp(self):
		self.company = self._create_isolated_company()
		patcher = patch.object(frappe.defaults, "get_user_default", return_value=self.company)
		patcher.start()
		self.addCleanup(patcher.stop)

		today = nowdate()
		self.p_blr_active = self._create_project(
			"Metro Hub",
			code="PRJ-BLR-01",
			location="Bengaluru",
			status="Open",
			start=add_days(today, -5),
		)
		self.p_blr_hold = self._create_project(
			"Tech Park",
			code="PRJ-BLR-02",
			location="Bengaluru",
			status="On hold",
			start=add_days(today, -10),
		)
		self.p_mum_active = self._create_project(
			"Harbor Tower",
			code="PRJ-MUM-01",
			location="Mumbai",
			status="Open",
			start=add_days(today, -3),
		)

	def _create_isolated_company(self):
		suffix = frappe.generate_hash(length=4).upper()
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Proj Filter Co {suffix}",
				"abbr": f"PF{suffix[:3]}",
				"default_currency": "INR",
				"country": "India",
			}
		).insert(ignore_permissions=True)
		return doc.name

	def _create_project(self, name, code, location, status="Open", start=None):
		doc = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"{name} {frappe.generate_hash(length=4)}",
				"cm_project_code": code,
				"cm_site_location": location,
				"company": self.company,
				"status": status,
				"expected_start_date": start,
			}
		).insert(ignore_permissions=True)
		if status != "Open":
			doc.db_set("status", status)
		return doc

	def test_a_standalone_location_filter(self):
		"""Test A: Standalone Location=Bengaluru returns only Bengaluru projects."""
		res = project.get_construction_projects(location="Bengaluru")
		ids = {p["id"] for p in res}
		self.assertEqual(ids, {self.p_blr_active.name, self.p_blr_hold.name})

	def test_b_location_with_search(self):
		"""Test B: Location=Bengaluru combined with Search applies both conditions."""
		res = project.get_construction_projects(search="Metro Hub", location="Bengaluru")
		self.assertEqual([p["id"] for p in res], [self.p_blr_active.name])

	def test_c_location_with_status(self):
		"""Test C: Location=Bengaluru combined with Status=In Progress returns only matching projects."""
		res = project.get_construction_projects(status="In Progress", location="Bengaluru")
		self.assertEqual([p["id"] for p in res], [self.p_blr_active.name])

	def test_d_all_three_filters(self):
		"""Test D: Search + Status + Location apply AND conditions."""
		res = project.get_construction_projects(search="Tech Park", status="On Hold", location="Bengaluru")
		self.assertEqual([p["id"] for p in res], [self.p_blr_hold.name])

		empty_res = project.get_construction_projects(search="Tech Park", status="In Progress", location="Bengaluru")
		self.assertEqual(empty_res, [])

	def test_e_no_matching_location(self):
		"""Test E: Unmatched location returns an empty list."""
		res = project.get_construction_projects(location="Nonexistent City XYZ")
		self.assertEqual(res, [])

	def test_f_no_location_filter(self):
		"""Test F: Unfiltered project list returns all company projects."""
		res = project.get_construction_projects()
		self.assertEqual(
			{p["id"] for p in res},
			{self.p_blr_active.name, self.p_blr_hold.name, self.p_mum_active.name},
		)

	def test_g_clear_filters_restores_full_list(self):
		"""Test G: Clearing filters after a filtered query restores the full list."""
		filtered = project.get_construction_projects(location="Mumbai")
		self.assertEqual(len(filtered), 1)

		restored = project.get_construction_projects(search="", status="", location="")
		self.assertEqual(len(restored), 3)
