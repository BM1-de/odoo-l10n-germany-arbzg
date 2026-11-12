# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class HrWorkEntryType(models.Model):
    _inherit = "hr.work.entry.type"

    time_account_deduct = fields.Boolean(
        string="Deducted from the Working Time Account",
        tracking=True,
        help="Time off of this type is compensation for plus hours: the expected "
        "hours of the day stay as they are, so the day is booked as minus on the "
        "working time account. Leave it off for vacation, sickness and other time "
        "off that counts as worked.",
    )
