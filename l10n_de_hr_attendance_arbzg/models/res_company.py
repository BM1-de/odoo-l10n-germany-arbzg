# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Settings of the Working Time Act per company."""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    arbzg_enabled = fields.Boolean(
        string="Working Time Act (ArbZG)",
        default=True,
        help="Check the legal breaks (§ 4 ArbZG) and the daily maximum working time "
        "(§ 3 ArbZG) on every attendance of the employees of this company.",
    )
    arbzg_break_mode = fields.Selection(
        [
            ("insert", "Insert the missing break"),
            ("notify", "Only point out the missing break"),
        ],
        string="Missing Break",
        default="insert",
        required=True,
        help="Insert: the missing break is put into the middle of the longest "
        "attendance of the day, which is split in two, and noted on it. Point out: "
        "the attendances stay unchanged; the missing minutes are shown on the "
        "attendance and the employee gets a message.",
    )
    arbzg_break_hours_1 = fields.Float(
        string="First Break After (Hours)",
        default=6.0,
        help="More working time than this per day needs the first break.",
    )
    arbzg_break_minutes_1 = fields.Integer(
        string="First Break (Minutes)",
        default=30,
    )
    arbzg_break_hours_2 = fields.Float(
        string="Longer Break After (Hours)",
        default=9.0,
        help="More working time than this per day needs the longer break.",
    )
    arbzg_break_minutes_2 = fields.Integer(
        string="Longer Break (Minutes)",
        default=45,
    )
    arbzg_min_break_minutes = fields.Integer(
        string="Shortest Break (Minutes)",
        default=15,
        help="Gaps between two attendances count as a break from this length on "
        "(breaks may be split into parts of at least 15 minutes, § 4 ArbZG).",
    )
    arbzg_max_hours = fields.Float(
        string="Maximum Working Time per Day (Hours)",
        default=10.0,
        help="More working time than this per day is not allowed (§ 3 ArbZG). The "
        "attendances are not shortened, as they must show the real time "
        "(§ 16 (2) ArbZG); the employee gets a message and the responsible person "
        "an activity.",
    )
    arbzg_auto_check_out = fields.Boolean(
        string="Check Out at the Maximum",
        default=True,
        help="Check out employees who forgot to check out as soon as the maximum "
        "working time of the day is reached (checked every 15 minutes).",
    )
    arbzg_responsible_id = fields.Many2one(
        "res.users",
        string="Responsible for Exceeded Working Time",
        help="Gets an activity when an employee worked more than the maximum. Empty: "
        "the attendance approver of the employee.",
    )

    @api.constrains(
        "arbzg_break_hours_1",
        "arbzg_break_minutes_1",
        "arbzg_break_hours_2",
        "arbzg_break_minutes_2",
        "arbzg_min_break_minutes",
        "arbzg_max_hours",
    )
    def _check_arbzg_limits(self):
        for company in self:
            if (
                min(company.arbzg_break_hours_1, company.arbzg_max_hours) <= 0
                or company.arbzg_break_hours_2 <= company.arbzg_break_hours_1
                or company.arbzg_break_minutes_1 < 0
                or company.arbzg_break_minutes_2 < company.arbzg_break_minutes_1
                or company.arbzg_min_break_minutes < 1
            ):
                raise ValidationError(
                    self.env._(
                        "The limits of the Working Time Act must be positive, and the "
                        "longer break must come later and last at least as long as "
                        "the first one."
                    )
                )

    def _arbzg_missing_break(self, work, breaks):
        """Break that is missing for ``work`` hours with ``breaks`` hours of breaks.

        A break is only required for the working time above a limit: whoever
        works 6:10 hours needs 10 minutes of break, not 30. Returns the missing
        hours and the working time left after taking them.
        """
        self.ensure_one()
        missing = 0.0
        for hours, minutes in (
            (self.arbzg_break_hours_1, self.arbzg_break_minutes_1),
            (self.arbzg_break_hours_2, self.arbzg_break_minutes_2),
        ):
            needed = minutes / 60.0
            if work > hours and breaks < needed:
                part = min(needed - breaks, work - hours)
                missing += part
                work -= part
                breaks += part
        return missing, work
