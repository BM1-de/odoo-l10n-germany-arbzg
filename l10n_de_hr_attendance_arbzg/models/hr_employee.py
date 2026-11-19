# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    arbzg_exempt = fields.Boolean(
        string="Exempt from the Working Time Act",
        groups="hr.group_hr_user",
        help="For example managing directors and executives (§ 18 ArbZG). Employees "
        "of an employee type that is exempt, such as freelancers, are never checked.",
    )

    def _arbzg_applies(self):
        """Whether the Working Time Act is checked for this employee."""
        self.ensure_one()
        employee = self.sudo()
        return bool(
            employee.company_id.arbzg_enabled
            and not employee.arbzg_exempt
            and not employee.employee_type_id.arbzg_exempt
        )
