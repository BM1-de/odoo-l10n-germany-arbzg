# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL

from ..models.hr_employee import DIGITS

LEGACY_TABLE = "hr_attendance_overtime_line"


class L10nDeTimeAccountImport(models.TransientModel):
    """Take over the overtime of Odoo 19.

    Odoo 19 kept a signed overtime balance in ``hr.attendance.overtime.line``.
    Odoo 20 dropped the model, but a database upgraded with OpenUpgrade still has
    the table. Its approved lines become entries of the kind ``transfer``, so the
    balance of every employee is the same as before; the module computes the
    account from the day after ``date`` on.
    """

    _name = "l10n_de.time.account.import"
    _description = "Take Over the Overtime of Odoo 19"

    date = fields.Date(
        string="Take Over Until",
        required=True,
        default=lambda self: self._default_date(),
        help="Overtime of Odoo 19 up to and including this date is taken over as it "
        "is. The working time account is computed from the following day on. Take "
        "the end of a period: a Sunday for accounts compared per week, the last day "
        "of a month for accounts compared per month.",
    )
    date_warning = fields.Char(compute="_compute_date_warning")
    with_settings = fields.Boolean(
        string="Take Over the Rules",
        default=True,
        help="Set period and tolerances of the contract versions from the overtime "
        "ruleset they had in Odoo 19, where no working time account is set yet.",
    )
    legacy_count = fields.Integer(
        string="Entries in Odoo 19", compute="_compute_legacy_count"
    )
    result = fields.Text(readonly=True)

    @api.model
    def _default_date(self):
        """The last Sunday: the end of a period for daily and weekly accounts."""
        today = fields.Date.context_today(self)
        return today - timedelta(days=today.weekday() + 1)

    @api.depends("date")
    def _compute_date_warning(self):
        for wizard in self:
            wizard.date_warning = (
                wizard.date
                and wizard.date.weekday() != 6
                and self.env._(
                    "This is not a Sunday. Accounts compared per week would start "
                    "in the middle of a week that Odoo 19 has booked in part."
                )
            )

    @api.model
    def _legacy_available(self):
        self.env.cr.execute(SQL("SELECT to_regclass(%s)", LEGACY_TABLE))
        return bool(self.env.cr.fetchone()[0])

    @api.depends("date")
    def _compute_legacy_count(self):
        available = self._legacy_available()
        for wizard in self:
            wizard.legacy_count = len(wizard._legacy_lines()) if available else 0

    def _legacy_lines(self):
        """Approved overtime of Odoo 19 that is not zero.

        :return: ``[(id, employee_id, date, hours)]``
        """
        self.ensure_one()
        self.env.cr.execute(
            SQL(
                """
                SELECT id, employee_id, date, COALESCE(manual_duration, duration)
                FROM %(table)s
                WHERE status = 'approved'
                  AND date <= %(date)s
                  AND ROUND(
                        COALESCE(manual_duration, duration, 0)::numeric, %(digits)s
                      ) != 0
                ORDER BY date, id
                """,
                table=SQL.identifier(LEGACY_TABLE),
                date=self.date,
                digits=DIGITS,
            )
        )
        return self.env.cr.fetchall()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _check(self):
        self.ensure_one()
        if not self._legacy_available():
            raise UserError(
                self.env._(
                    "This database has no overtime of Odoo 19: the table "
                    "%s does not exist.",
                    LEGACY_TABLE,
                )
            )

    def _take_over_settings(self):
        """Set the account of contract versions from their ruleset in Odoo 19.

        The first rule of a ruleset that compares the worked hours of a day or a
        week to the schedule gives the period and the tolerances. Minus hours were
        booked in Odoo 19 when the company had the absence management on.
        """
        self.env.cr.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE (table_name, column_name) IN (
                ('hr_version', 'ruleset_id'),
                ('hr_attendance_overtime_rule', 'ruleset_id')
            )
            """
        )
        if self.env.cr.fetchone()[0] != 2:
            return 0
        self.env.cr.execute(
            """
            SELECT DISTINCT ON (hv.id)
                hv.id, rule.quantity_period,
                COALESCE(rule.employer_tolerance, 0),
                COALESCE(rule.employee_tolerance, 0)
            FROM hr_version hv
            JOIN hr_attendance_overtime_rule rule
                ON rule.ruleset_id = hv.ruleset_id
                AND rule.base_off = 'quantity'
                AND rule.quantity_period IN ('day', 'week')
            WHERE hv.time_account_period = 'none'
            ORDER BY hv.id, rule.sequence, rule.id
            """
        )
        count = 0
        for (
            version_id,
            period,
            tolerance_plus,
            tolerance_minus,
        ) in self.env.cr.fetchall():
            version = self.env["hr.version"].sudo().browse(version_id)
            version.write(
                {
                    "time_account_period": period,
                    "time_account_tolerance_plus": tolerance_plus,
                    "time_account_tolerance_minus": tolerance_minus,
                    "time_account_negative": bool(
                        version.company_id.absence_management
                    ),
                }
            )
            count += 1
        return count

    def action_import(self):
        self._check()
        Line = (
            self.env["l10n_de.time.account.line"]
            .sudo()
            .with_context(time_account_system=True)
        )
        settings = self._take_over_settings() if self.with_settings else 0
        legacy = self._legacy_lines()
        refs = {f"{LEGACY_TABLE},{row[0]}": row for row in legacy}
        known = set(
            Line.search([("legacy_ref", "in", list(refs))]).mapped("legacy_ref")
        )
        employees = self.env["hr.employee"].sudo().with_context(active_test=False)
        Line.create(
            [
                {
                    "employee_id": employee_id,
                    "date": date,
                    "date_from": date,
                    "kind": "transfer",
                    "hours": round(hours, DIGITS),
                    "state": "booked",
                    "name": "Odoo 19",
                    "legacy_ref": ref,
                }
                for ref, (_id, employee_id, date, hours) in refs.items()
                if ref not in known
            ]
        )
        start = self.date + timedelta(days=1)
        for employee in employees.browse({row[1] for row in legacy}):
            if not employee.time_account_start or employee.time_account_start < start:
                employee.time_account_start = start
        self.result = self.env._(
            "%(new)s entries taken over, %(known)s were there already. "
            "%(settings)s contract versions got their account from the rules of "
            "Odoo 19. The accounts are computed from %(start)s on.",
            new=len(refs) - len(known),
            known=len(known),
            settings=settings,
            start=fields.Date.to_string(start),
        )
        return self._reopen()

    def action_compare(self):
        """List where the module computes something else than Odoo 19 booked.

        Nothing is stored. Periods are compared as the module cuts them, with the
        settings the contract versions have now, from the week of the first
        attendance of each employee on. Periods the module would ask to clarify
        count as zero, like everything it does not book.
        """
        self._check()
        legacy = defaultdict(lambda: defaultdict(float))
        for _id, employee_id, date, hours in self._legacy_lines():
            legacy[employee_id][date] += hours
        employees = self.env["hr.employee"].sudo().with_context(active_test=False)
        rows = []
        periods = 0
        Attendance = self.env["hr.attendance"].sudo()
        for employee in employees.browse(legacy):
            days = legacy[employee.id]
            # entries before the first attendance were booked by hand in Odoo 19,
            # opening balances for example: there is nothing to compute for them
            first = Attendance.search(
                [("employee_id", "=", employee.id)], order="date", limit=1
            )
            if not first:
                continue
            start = max(min(days), first.date)
            for values, version in employee._time_account_compute(
                # whole weeks, as Odoo 19 booked them
                start - timedelta(days=start.weekday()),
                self.date,
                finished_before=self.date + timedelta(days=1),
            ):
                periods += 1
                hours, _state = employee._time_account_booking(
                    version, values["deviation_hours"], values["unexplained_days"]
                )
                booked = sum(
                    amount
                    for date, amount in days.items()
                    if values["date_from"] <= date <= values["date"]
                )
                if round(hours - booked, 2):
                    rows.append(
                        f"{employee.name}: {values['date_from']} – {values['date']}: "
                        f"Odoo 19 {booked:+.2f}, {self.env._('computed')} {hours:+.2f}"
                    )
        self.result = "\n".join(
            [
                self.env._(
                    "%(periods)s periods compared, %(count)s differ.",
                    periods=periods,
                    count=len(rows),
                ),
                *rows,
            ]
        )
        return self._reopen()
