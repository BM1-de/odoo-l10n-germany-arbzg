# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models

#: employee types that are no employees in the sense of the Working Time Act
EXEMPT_TYPES = ("contractor", "freelance")


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    arbzg_exempt = fields.Boolean(
        string="Exempt from the Working Time Act",
        groups="hr.group_hr_user",
        help="For example managing directors and executives (§ 18 ArbZG). Contractors "
        "and freelancers are always exempt.",
    )

    def _arbzg_applies(self):
        """Whether the Working Time Act is checked for this employee."""
        self.ensure_one()
        employee = self.sudo()
        return bool(
            employee.company_id.arbzg_enabled
            and not employee.arbzg_exempt
            and employee.employee_type not in EXEMPT_TYPES
        )
