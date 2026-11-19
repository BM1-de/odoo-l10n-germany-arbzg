# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class HrEmployeeType(models.Model):
    _inherit = "hr.employee.type"

    arbzg_exempt = fields.Boolean(
        string="Exempt from the Working Time Act",
        help="Employees of this type are no employees in the sense of the Working "
        "Time Act, for example contractors and freelancers: their attendances are "
        "not checked.",
    )
