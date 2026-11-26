# Copyright (c) 2026, TechnoTribes and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ProjectPhase(Document):
	"""A stage of a construction project, such as Foundation Works or Finishing Works."""

	def before_insert(self):
		if not self.sequence and self.project:
			last = frappe.get_all(
				"Project Phase",
				filters={"project": self.project},
				pluck="sequence",
				order_by="sequence desc",
				limit=1,
			)
			self.sequence = ((last[0] if last else 0) or 0) + 1

	def validate(self):
		self.validate_from_to_dates("start_date", "end_date")
		if not 0 <= flt(self.progress) <= 100:
			frappe.throw(_("Progress must be between 0% and 100%."))
