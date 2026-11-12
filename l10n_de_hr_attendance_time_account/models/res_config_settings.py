# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    time_account_period = fields.Selection(
        related="company_id.time_account_period", readonly=False, required=True
    )
    time_account_tolerance_plus = fields.Float(
        related="company_id.time_account_tolerance_plus", readonly=False
    )
    time_account_tolerance_minus = fields.Float(
        related="company_id.time_account_tolerance_minus", readonly=False
    )
    time_account_negative = fields.Boolean(
        related="company_id.time_account_negative", readonly=False
    )
    time_account_lock_date = fields.Date(related="company_id.time_account_lock_date")
