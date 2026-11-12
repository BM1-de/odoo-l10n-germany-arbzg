# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models

from .res_company import PERIODS


class HrVersion(models.Model):
    _inherit = "hr.version"

    time_account_period = fields.Selection(
        PERIODS,
        string="Working Time Account",
        default=lambda self: self.env.company.sudo().time_account_period,
        required=True,
        groups="hr.group_hr_user",
        tracking=True,
        help="Period over which worked hours are compared to the hours of the "
        "working schedule. Schedules without fixed days are compared per week "
        "at least.",
    )
    time_account_tolerance_plus = fields.Float(
        string="Tolerance for Plus Hours",
        default=lambda self: self.env.company.sudo().time_account_tolerance_plus,
        groups="hr.group_hr_user",
        tracking=True,
        help="A period with up to this many hours more than expected is booked "
        "with zero. Beyond it the whole difference is booked.",
    )
    time_account_tolerance_minus = fields.Float(
        string="Tolerance for Minus Hours",
        default=lambda self: self.env.company.sudo().time_account_tolerance_minus,
        groups="hr.group_hr_user",
        tracking=True,
        help="A period with up to this many hours less than expected is booked "
        "with zero. Beyond it the whole difference is booked.",
    )
    time_account_negative = fields.Boolean(
        string="Book Minus Hours",
        default=lambda self: self.env.company.sudo().time_account_negative,
        groups="hr.group_hr_user",
        tracking=True,
        help="Minus hours need an agreement with the employee. Without it, periods "
        "with less than the expected hours are booked with zero.",
    )
    time_account_milog = fields.Boolean(
        string="Monitor § 2 (2) MiLoG",
        groups="hr.group_hr_user",
        tracking=True,
        help="For accounts under the German Minimum Wage Act: warn when plus hours "
        "get twelve months old and when more than half of the agreed monthly "
        "working time is added in a month.",
    )

    _time_account_tolerances_positive = models.Constraint(
        "CHECK(COALESCE(time_account_tolerance_plus, 0) >= 0 "
        "AND COALESCE(time_account_tolerance_minus, 0) >= 0)",
        "The tolerances of the working time account cannot be negative.",
    )

    @api.model
    def _get_whitelist_fields_from_template(self):
        """Also copy the settings of the working time account from templates."""
        return super()._get_whitelist_fields_from_template() + [
            "time_account_period",
            "time_account_tolerance_plus",
            "time_account_tolerance_minus",
            "time_account_negative",
            "time_account_milog",
        ]
