# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models

#: periods a working time account can compare worked and expected hours over
PERIODS = [
    ("none", "No working time account"),
    ("day", "Per day"),
    ("week", "Per week"),
    ("month", "Per month"),
]


class ResCompany(models.Model):
    _inherit = "res.company"

    time_account_period = fields.Selection(
        PERIODS,
        string="Working Time Account",
        default="none",
        required=True,
        help="Default for new contract versions: the period over which worked hours "
        "are compared to the hours of the working schedule.",
    )
    time_account_tolerance_plus = fields.Float(
        string="Tolerance for Plus Hours",
        help="Default for new contract versions. A period with up to this many hours "
        "more than expected is booked with zero.",
    )
    time_account_tolerance_minus = fields.Float(
        string="Tolerance for Minus Hours",
        help="Default for new contract versions. A period with up to this many hours "
        "less than expected is booked with zero.",
    )
    time_account_negative = fields.Boolean(
        string="Book Minus Hours",
        default=True,
        help="Default for new contract versions. Minus hours need an agreement with "
        "the employee.",
    )
    time_account_lock_date = fields.Date(
        string="Working Time Accounts Closed Until",
        help="Entries up to and including this date are closed: they are neither "
        "computed again nor changed.",
    )

    _time_account_tolerances_positive = models.Constraint(
        "CHECK(COALESCE(time_account_tolerance_plus, 0) >= 0 "
        "AND COALESCE(time_account_tolerance_minus, 0) >= 0)",
        "The tolerances of the working time account cannot be negative.",
    )
