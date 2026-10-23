# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    arbzg_enabled = fields.Boolean(related="company_id.arbzg_enabled", readonly=False)
    arbzg_break_mode = fields.Selection(
        related="company_id.arbzg_break_mode", readonly=False
    )
    arbzg_break_hours_1 = fields.Float(
        related="company_id.arbzg_break_hours_1", readonly=False
    )
    arbzg_break_minutes_1 = fields.Integer(
        related="company_id.arbzg_break_minutes_1", readonly=False
    )
    arbzg_break_hours_2 = fields.Float(
        related="company_id.arbzg_break_hours_2", readonly=False
    )
    arbzg_break_minutes_2 = fields.Integer(
        related="company_id.arbzg_break_minutes_2", readonly=False
    )
    arbzg_min_break_minutes = fields.Integer(
        related="company_id.arbzg_min_break_minutes", readonly=False
    )
    arbzg_max_hours = fields.Float(related="company_id.arbzg_max_hours", readonly=False)
    arbzg_auto_check_out = fields.Boolean(
        related="company_id.arbzg_auto_check_out", readonly=False
    )
    arbzg_responsible_id = fields.Many2one(
        related="company_id.arbzg_responsible_id", readonly=False
    )
