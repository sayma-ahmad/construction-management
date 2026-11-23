# Copyright (c) 2026, TechnoTribes and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


class TestProjectPhase(FrappeTestCase):
	def setUp(self):
		self.project = frappe.db.get_value("Project", {}, "name")
		if not self.project:
			self.skipTest("Needs at least one Project.")

	def make_phase(self, **values):
		doc = {
			"doctype": "Project Phase",
			"phase_name": "Test Phase",
			"project": self.project,
			"start_date": nowdate(),
			"end_date": add_days(nowdate(), 10),
		}
		doc.update(values)
		return frappe.get_doc(doc)

	def test_valid_phase_is_saved_with_defaults(self):
		phase = self.make_phase().insert()
		self.assertEqual(phase.status, "Not Started")
		self.assertTrue(phase.name.startswith("PHASE-"))
		self.assertEqual(phase.project_name, frappe.db.get_value("Project", self.project, "project_name"))

	def test_new_phase_gets_next_number_in_project(self):
		last = frappe.db.get_value("Project Phase", {"project": self.project}, "max(sequence)") or 0
		phase = self.make_phase().insert()
		self.assertEqual(phase.sequence, last + 1)

	def test_project_is_required(self):
		with self.assertRaises(frappe.MandatoryError):
			self.make_phase(project=None).insert()

	def test_end_date_before_start_date_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_phase(end_date=add_days(nowdate(), -1)).insert()
		self.assertFalse(frappe.db.exists("Project Phase", {"phase_name": "Test Phase", "end_date": add_days(nowdate(), -1)}))

	def test_progress_outside_range_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_phase(progress=120).insert()
