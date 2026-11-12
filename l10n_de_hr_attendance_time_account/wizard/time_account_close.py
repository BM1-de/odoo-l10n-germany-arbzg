# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class L10nDeTimeAccountClose(models.TransientModel):
    _name = "l10n_de.time.account.close"
    _description = "Close Working Time Accounts"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    lock_date = fields.Date(
        related="company_id.time_account_lock_date", string="Closed Until Now"
    )
    date = fields.Date(
        string="Close Until",
        required=True,
        default=lambda self: fields.Date.context_today(self)
        + relativedelta(day=1, days=-1),
        help="Entries up to and including this date are not computed again and "
        "cannot be changed.",
    )
    to_clarify_ids = fields.Many2many(
        "l10n_de.time.account.line",
        compute="_compute_to_clarify_ids",
        string="Periods to Clarify",
    )

    def _employees(self):
        return (
            self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("time_account_start", "!=", False),
                ]
            )
        )

    @api.depends("company_id", "date")
    def _compute_to_clarify_ids(self):
        for wizard in self:
            wizard.to_clarify_ids = self.env["l10n_de.time.account.line"].search(
                [
                    ("company_id", "=", wizard.company_id.id),
                    ("state", "=", "to_clarify"),
                    ("date", "<=", wizard.date),
                ]
            )

    def action_update(self):
        """Compute the open periods of all accounts of the company."""
        self.ensure_one()
        self.env["hr.employee"]._cron_time_account()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_close(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.date >= today:
            raise UserError(self.env._("Only periods in the past can be closed."))
        if self.lock_date and self.date <= self.lock_date:
            raise UserError(
                self.env._("The working time accounts are already closed until then.")
            )
        self._employees()._time_account_update(date_to=self.date)
        self.invalidate_recordset(["to_clarify_ids"])
        if self.to_clarify_ids:
            raise UserError(
                self.env._(
                    "%(count)s periods are still to clarify. Enter the missing time "
                    "off or confirm the minus hours first.",
                    count=len(self.to_clarify_ids),
                )
            )
        self.company_id.sudo().time_account_lock_date = self.date
        return {"type": "ir.actions.act_window_close"}

    def action_correct_closed(self):
        """Book what changed in closed periods as corrections dated today."""
        self.ensure_one()
        corrections = self._employees()._time_account_correct_closed()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "l10n_de_hr_attendance_time_account.time_account_line_action"
        )
        action["domain"] = [("id", "in", corrections.ids)]
        return action
