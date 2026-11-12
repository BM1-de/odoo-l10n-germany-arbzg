# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

#: entries the module books itself; users never create or delete them
SYSTEM_KINDS = ("deviation", "transfer")
#: what a user may change on an entry of the given kind, while it is not closed
EDITABLE = {
    "deviation": {"confirmed", "neutral_reason"},
    "transfer": set(),
}
EDITABLE_MANUAL = {"name"}


class L10nDeTimeAccountLine(models.Model):
    """One entry of the working time account of an employee.

    The balance of the account is the sum of ``hours`` over the booked entries.
    Entries of the kind ``deviation`` come from
    :meth:`hr.employee._time_account_update`, one per finished period; all other
    kinds are booked by hand, except ``transfer``, which holds what was taken over
    from another system.
    """

    _name = "l10n_de.time.account.line"
    _description = "Working Time Account Entry"
    _order = "date desc, id desc"
    _rec_name = "name"

    employee_id = fields.Many2one(
        "hr.employee",
        required=True,
        index=True,
        ondelete="restrict",
        default=lambda self: self.env.context.get("default_employee_id"),
    )
    company_id = fields.Many2one(
        related="employee_id.company_id", store=True, index=True
    )
    date = fields.Date(
        required=True,
        index=True,
        default=fields.Date.context_today,
        help="For computed entries the last day of the period.",
    )
    date_from = fields.Date(string="Period Start", readonly=True)
    kind = fields.Selection(
        [
            ("deviation", "Deviation"),
            ("opening", "Opening Balance"),
            ("adjustment", "Correction"),
            ("payout", "Payout"),
            ("forfeit", "Forfeiture"),
            ("transfer", "Taken Over"),
        ],
        required=True,
        default="adjustment",
        index=True,
    )
    period = fields.Selection(
        [("day", "Day"), ("week", "Week"), ("month", "Month")], readonly=True
    )
    expected_hours = fields.Float(readonly=True)
    worked_hours = fields.Float(readonly=True)
    deviation_hours = fields.Float(
        string="Difference",
        readonly=True,
        help="Worked minus expected hours of the period, before tolerance.",
    )
    hours = fields.Float(
        string="Booked Hours",
        help="What the entry adds to the account. Negative for minus hours, payouts "
        "and forfeitures.",
    )
    name = fields.Char(string="Reason")
    state = fields.Selection(
        [("booked", "Booked"), ("to_clarify", "To Clarify")],
        default="booked",
        required=True,
        readonly=True,
        index=True,
        help="To clarify: the period has scheduled days without attendance and "
        "without time off. Nothing is booked until the time off is entered or the "
        "minus hours are confirmed.",
    )
    unexplained_days = fields.Integer(
        string="Days Without Attendance",
        readonly=True,
        help="Scheduled days of the period without attendance and without time off.",
    )
    confirmed = fields.Boolean(
        string="Minus Confirmed",
        help="The days without attendance are minus hours indeed.",
    )
    neutral_reason = fields.Char(
        string="Not Booked Because",
        help="Books the period with zero, for example when the employer had no work "
        "for the employee. Minus hours must not be booked in that case.",
    )
    origin_line_id = fields.Many2one(
        "l10n_de.time.account.line",
        string="Belongs To",
        readonly=True,
        index="btree_not_null",
        ondelete="restrict",
        help="The entry this one reverses, or the closed period it corrects.",
    )
    reversal_ids = fields.One2many(
        "l10n_de.time.account.line", "origin_line_id", readonly=True
    )
    correction_hours = fields.Float(
        readonly=True,
        help="Sum of the corrections booked for this period after it was closed.",
    )
    legacy_ref = fields.Char(
        string="Reference in the Previous System", readonly=True, index=True
    )
    locked = fields.Boolean(compute="_compute_locked", string="Closed")

    _legacy_ref_uniq = models.Constraint(
        "UNIQUE(legacy_ref)",
        "This entry of the previous system has already been taken over.",
    )

    @api.depends("date", "company_id.time_account_lock_date")
    def _compute_locked(self):
        for line in self:
            lock_date = line.company_id.sudo().time_account_lock_date
            line.locked = bool(lock_date and line.date and line.date <= lock_date)

    @api.depends("kind", "name", "date")
    def _compute_display_name(self):
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for line in self:
            line.display_name = " · ".join(
                part
                for part in (
                    line.date and fields.Date.to_string(line.date),
                    kinds.get(line.kind),
                    line.name,
                )
                if part
            )

    def _is_system(self):
        return bool(self.env.context.get("time_account_system"))

    @api.model_create_multi
    def create(self, vals_list):
        system = self._is_system()
        for vals in vals_list:
            kind = vals.get("kind", "adjustment")
            if system:
                continue
            if kind in SYSTEM_KINDS:
                raise UserError(
                    self.env._("Entries of this kind are booked by the system only.")
                )
            if not (vals.get("name") or "").strip():
                raise UserError(self.env._("An entry booked by hand needs a reason."))
            if float_is_zero(vals.get("hours") or 0.0, precision_digits=4):
                raise UserError(self.env._("An entry needs hours other than zero."))
            vals["state"] = "booked"
            vals.setdefault("date_from", vals.get("date"))
        lines = super().create(vals_list)
        if not system:
            lines._check_not_locked()
            lines._log_on_employee()
        return lines

    def write(self, vals):
        if self._is_system():
            return super().write(vals)
        self._check_not_locked()
        for line in self:
            allowed = EDITABLE.get(line.kind, EDITABLE_MANUAL)
            forbidden = set(vals) - allowed
            if forbidden:
                raise UserError(
                    self.env._(
                        "Booked entries are not changed afterwards. Reverse the entry "
                        "and book it again. (Fields: %s)",
                        ", ".join(sorted(forbidden)),
                    )
                )
        result = super().write(vals)
        if {"confirmed", "neutral_reason"} & set(vals):
            for line in self.filtered(lambda line: line.kind == "deviation"):
                line.employee_id._time_account_update(line.date_from, line.date)
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_system(self):
        if not self._is_system():
            raise UserError(
                self.env._(
                    "Entries of the working time account are not deleted. Reverse "
                    "the entry instead."
                )
            )

    def _check_not_locked(self):
        for line in self:
            if line.locked:
                raise UserError(
                    self.env._(
                        "The working time accounts are closed until %(date)s. Book "
                        "the change in an open period.",
                        date=line.company_id.sudo().time_account_lock_date,
                    )
                )

    def _log_on_employee(self):
        """Note entries booked by hand in the chatter of the employee."""
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for line in self:
            line.employee_id.sudo().message_post(
                body=Markup("%(title)s: %(kind)s, %(date)s, %(hours)s h<br/>%(reason)s")
                % {
                    "title": self.env._("Working time account"),
                    "kind": kinds.get(line.kind, ""),
                    "date": fields.Date.to_string(line.date),
                    "hours": f"{line.hours:+.2f}",
                    "reason": line.name or "",
                },
                author_id=self.env.user.partner_id.id,
                subtype_xmlid="mail.mt_note",
            )

    def action_reverse(self):
        """Book the opposite of entries booked by hand, dated today."""
        today = fields.Date.context_today(self)
        reversals = self.browse()
        for line in self:
            if line.kind in SYSTEM_KINDS:
                raise UserError(
                    self.env._("Only entries booked by hand can be reversed.")
                )
            if line.origin_line_id or line.reversal_ids:
                raise UserError(
                    self.env._("This entry is a reversal or has been reversed already.")
                )
            reversals += self.create(
                {
                    "employee_id": line.employee_id.id,
                    "date": today,
                    "kind": line.kind,
                    "hours": -line.hours,
                    "name": self.env._(
                        "Reversal of %(date)s: %(reason)s",
                        date=fields.Date.to_string(line.date),
                        reason=line.name or "",
                    ),
                    "origin_line_id": line.id,
                }
            )
        return reversals

    def action_confirm_minus(self):
        self.filtered(lambda line: line.kind == "deviation").write({"confirmed": True})
        return True
