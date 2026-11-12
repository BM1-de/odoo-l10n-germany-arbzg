# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools import float_compare, format_date

#: hours are compared and stored with this many decimals
DIGITS = 4
#: plus hours under § 2 (2) MiLoG are announced this many days before they are due
MILOG_NOTICE_DAYS = 60
#: share of the agreed monthly working time that may be added per month (§ 2 (2) MiLoG)
MILOG_MONTHLY_SHARE = 0.5


def format_hours(hours, sign=False):
    """Hours as ``h:mm``, the way German time records show them."""
    minutes = round(abs(hours or 0.0) * 60)
    prefix = "−" if (hours or 0.0) < 0 and minutes else "+" if sign and minutes else ""
    return f"{prefix}{minutes // 60}:{minutes % 60:02d}"


def _days(date_from, date_to):
    day = date_from
    while day <= date_to:
        yield day
        day += timedelta(days=1)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    time_account_period = fields.Selection(
        related="version_id.time_account_period",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_user",
    )
    time_account_tolerance_plus = fields.Float(
        related="version_id.time_account_tolerance_plus",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_user",
    )
    time_account_tolerance_minus = fields.Float(
        related="version_id.time_account_tolerance_minus",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_user",
    )
    time_account_negative = fields.Boolean(
        related="version_id.time_account_negative",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_user",
    )
    time_account_milog = fields.Boolean(
        related="version_id.time_account_milog",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_user",
    )
    time_account_start = fields.Date(
        string="Working Time Account Since",
        groups="hr.group_hr_user",
        tracking=True,
        help="Nothing is computed before this date. Empty: the account starts the "
        "day it is computed for the first time.",
    )
    time_account_line_ids = fields.One2many(
        "l10n_de.time.account.line",
        "employee_id",
        groups="hr_attendance.group_hr_attendance_officer",
    )
    time_account_balance = fields.Float(
        string="Working Time Balance",
        compute="_compute_time_account_balance",
        groups="hr_attendance.group_hr_attendance_officer",
    )
    time_account_balance_display = fields.Char(
        string="Balance as Text",
        compute="_compute_time_account_balance",
        groups="hr_attendance.group_hr_attendance_officer",
    )
    time_account_to_clarify = fields.Integer(
        string="Periods to Clarify",
        compute="_compute_time_account_balance",
        groups="hr_attendance.group_hr_attendance_officer",
    )
    time_account_due_date = fields.Date(
        string="Plus Hours Due",
        readonly=True,
        groups="hr.group_hr_user",
        help="§ 2 (2) MiLoG: the oldest plus hours must be compensated by paid time "
        "off or payment by this date.",
    )
    time_account_due_hours = fields.Float(
        string="Plus Hours Due (Hours)", readonly=True, groups="hr.group_hr_user"
    )
    time_account_warning = fields.Text(
        string="Working Time Account Warnings",
        readonly=True,
        groups="hr.group_hr_user",
    )

    # ------------------------------------------------------------------
    # balance
    # ------------------------------------------------------------------

    @api.depends("time_account_line_ids.hours", "time_account_line_ids.state")
    def _compute_time_account_balance(self):
        Line = self.env["l10n_de.time.account.line"].sudo()
        booked = dict(
            Line._read_group(
                [("employee_id", "in", self.ids), ("state", "=", "booked")],
                ["employee_id"],
                ["hours:sum"],
            )
        )
        to_clarify = dict(
            Line._read_group(
                [("employee_id", "in", self.ids), ("state", "=", "to_clarify")],
                ["employee_id"],
                ["__count"],
            )
        )
        for employee in self:
            employee.time_account_balance = booked.get(employee, 0.0)
            employee.time_account_balance_display = format_hours(
                employee.time_account_balance, sign=True
            )
            employee.time_account_to_clarify = to_clarify.get(employee, 0)

    def _time_account_balance_at(self, date):
        """Balance of the account at the end of ``date``."""
        self.ensure_one()
        ((hours,),) = (
            self.env["l10n_de.time.account.line"]
            .sudo()
            ._read_group(
                [
                    ("employee_id", "=", self.id),
                    ("state", "=", "booked"),
                    ("date", "<=", date),
                ],
                [],
                ["hours:sum"],
            )
        )
        return hours or 0.0

    def action_open_time_account(self):
        self.ensure_one()
        self._time_account_update()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "l10n_de_hr_attendance_time_account.time_account_line_action"
        )
        action["domain"] = [("employee_id", "=", self.id)]
        action["context"] = {"default_employee_id": self.id}
        return action

    # ------------------------------------------------------------------
    # periods, expected and worked hours
    # ------------------------------------------------------------------

    def _time_account_today(self):
        self.ensure_one()
        return datetime.now(ZoneInfo(self.sudo()._get_tz() or "UTC")).date()

    def _time_account_versions(self, date_from, date_to):
        """Contract versions in effect within the dates, clipped to their contract.

        :return: ``[(date_from, date_to, hr.version)]`` ordered by date, inclusive
        """
        self.ensure_one()
        employee = self.sudo()
        result = []
        periods = employee._get_version_periods(
            date_from, date_to, check_contract=False
        )
        for start, end, version in periods.get(employee, []):
            if version.contract_date_start:
                start = max(start, version.contract_date_start)
            if version.contract_date_end:
                end = min(end, version.contract_date_end)
            if start <= end:
                result.append((start, end, version))
        return sorted(result, key=lambda period: period[0])

    @api.model
    def _time_account_kind(self, version):
        """Period the account of ``version`` is computed over.

        A schedule without fixed days has no expected hours for a single day, so a
        daily account is computed per week.
        """
        if not version:
            return "none"
        kind = version.time_account_period or "none"
        if kind == "day" and version.resource_calendar_id._is_flexible():
            kind = "week"
        return kind

    def _time_account_periods(self, date_from, date_to, versions):
        """Cut the dates into the periods the account is computed over.

        A period ends on its natural end (the day, Sunday, the last day of the
        month), or earlier, on the last day before a contract version with another
        kind of period starts. The last period may end after ``date_to``.

        :return: ``[(date_from, date_to, hr.version, kind)]``, the version being
            the one in effect on the first day
        """

        def version_at(day):
            for start, end, version in versions:
                if start <= day <= end:
                    return version
            return self.env["hr.version"]

        periods = []
        cursor = date_from
        while cursor <= date_to:
            version = version_at(cursor)
            kind = self._time_account_kind(version)
            if kind == "week":
                end = cursor + timedelta(days=6 - cursor.weekday())
            elif kind == "month":
                end = cursor + relativedelta(day=31)
            else:
                end = cursor
            probe = cursor
            while probe < end:
                following = version_at(probe + timedelta(days=1))
                if self._time_account_kind(following) != kind:
                    break
                probe += timedelta(days=1)
            periods.append((cursor, probe, version, kind))
            cursor = probe + timedelta(days=1)
        return periods

    def _time_account_leave_domain(self):
        """Time off that counts as worked: it lowers the expected hours.

        Time off that is deducted from the account does not, so its days end up
        as minus hours.
        """
        self.ensure_one()
        return [
            ("company_id", "in", [False, self.sudo().company_id.id]),
            ("count_as", "=", "absence"),
            "|",
            ("work_entry_type_id", "=", False),
            ("work_entry_type_id.time_account_deduct", "=", False),
        ]

    def _time_account_calendar_hours(self, date_from, date_to, versions):
        """Hours of the working schedule per day.

        :return: ``{date: [scheduled, expected]}``: the hours of the schedule, and
            what is left of them after public holidays and time off that counts as
            worked. Schedules without any hours target have no expected hours.
        """
        self.ensure_one()
        employee = self.sudo()
        resource = employee.resource_id
        domain = employee._time_account_leave_domain()
        result = defaultdict(lambda: [0.0, 0.0])
        for version_start, version_end, version in versions:
            start = max(version_start, date_from)
            end = min(version_end, date_to)
            calendar = version.resource_calendar_id
            if start > end or not calendar or calendar._is_fully_flexible():
                continue
            tz = ZoneInfo(version._get_tz() or "UTC")
            start_dt = datetime.combine(start, time.min, tzinfo=tz)
            end_dt = datetime.combine(end, time.max, tzinfo=tz)
            for index, compute_leaves in ((0, False), (1, True)):
                intervals = calendar._work_intervals_batch(
                    start_dt,
                    end_dt,
                    resources_per_tz={tz: resource},
                    domain=domain,
                    compute_leaves=compute_leaves,
                )[resource.id]
                for interval_start, interval_stop, _records in intervals:
                    day = interval_start.astimezone(tz).date()
                    seconds = (interval_stop - interval_start).total_seconds()
                    result[day][index] += seconds / 3600.0
        return result

    def _time_account_worked_hours(self, date_from, date_to):
        """Worked hours per day from the validated attendances.

        Attendances of a type that counts as absence are left out: Odoo adds such
        lines for missing time when its own time rules are used.

        :return: ``{date: hours}``
        """
        self.ensure_one()
        attendances = (
            self.env["hr.attendance"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", self.id),
                    ("date", ">=", date_from),
                    ("date", "<=", date_to),
                    ("state", "=", "validated"),
                    ("check_out", "!=", False),
                    ("work_entry_type_id.count_as", "=", "working_time"),
                ]
            )
        )
        result = defaultdict(float)
        for attendance in attendances:
            result[attendance.date] += attendance.worked_hours
        return result

    def _time_account_deducted_days(self, date_from, date_to):
        """Days with time off that is deducted from the account."""
        self.ensure_one()
        employee = self.sudo()
        tz = ZoneInfo(employee._get_tz() or "UTC")
        utc = ZoneInfo("UTC")
        start_dt = datetime.combine(date_from, time.min, tzinfo=tz)
        end_dt = datetime.combine(date_to, time.max, tzinfo=tz)
        leaves = (
            self.env["resource.calendar.leaves"]
            .sudo()
            .search(
                [
                    ("resource_id", "=", employee.resource_id.id),
                    ("work_entry_type_id.time_account_deduct", "=", True),
                    ("date_from", "<=", end_dt.astimezone(utc).replace(tzinfo=None)),
                    ("date_to", ">=", start_dt.astimezone(utc).replace(tzinfo=None)),
                ]
            )
        )
        days = set()
        for leave in leaves:
            first = leave.date_from.replace(tzinfo=utc).astimezone(tz).date()
            last = leave.date_to.replace(tzinfo=utc).astimezone(tz).date()
            days.update(_days(max(first, date_from), min(last, date_to)))
        return days

    # ------------------------------------------------------------------
    # booking
    # ------------------------------------------------------------------

    @api.model
    def _time_account_booking(self, version, deviation, unexplained_days, line=None):
        """What a period books, given its difference of worked and expected hours.

        Within the tolerance nothing is booked, beyond it the whole difference.
        Minus hours are only booked when the contract version allows them, and not
        before days without attendance and without time off are clarified. With a
        schedule without fixed days that is a period without any attendance.

        :return: ``(hours, state)``
        """
        deviation = round(deviation, DIGITS)
        if line and (line.neutral_reason or "").strip():
            return 0.0, "booked"
        if (
            float_compare(
                deviation, version.time_account_tolerance_plus, precision_digits=DIGITS
            )
            > 0
        ):
            return deviation, "booked"
        if (
            float_compare(
                deviation,
                -version.time_account_tolerance_minus,
                precision_digits=DIGITS,
            )
            < 0
            and version.time_account_negative
        ):
            if unexplained_days and not (line and line.confirmed):
                return 0.0, "to_clarify"
            return deviation, "booked"
        return 0.0, "booked"

    def _time_account_period_values(self, start, end, version, kind, data):
        """Values of the entry of one period.

        :param dict data: ``calendar`` ``{date: [scheduled, expected]}``, ``worked``
            ``{date: hours}`` and ``deducted`` (set of dates), covering the period
        """
        expected = worked = 0.0
        unexplained_days = 0
        fixed_days = not version.resource_calendar_id._is_flexible()
        for day in _days(start, end):
            _scheduled, expected_day = data["calendar"].get(day, (0.0, 0.0))
            worked_day = data["worked"].get(day, 0.0)
            expected += expected_day
            worked += worked_day
            if (
                fixed_days
                and float_compare(expected_day, 0.0, precision_digits=DIGITS) > 0
                and not worked_day
                and day not in data["deducted"]
            ):
                # work was expected, also after time off for a part of the day,
                # and there is no attendance at all
                unexplained_days += 1
        if not fixed_days and expected > 0 and not worked:
            # a schedule without fixed days has no single day to point at: the
            # whole period without any attendance is what has to be clarified
            unexplained_days = 1
        return {
            "kind": "deviation",
            "period": kind,
            "date_from": start,
            "date": end,
            "expected_hours": round(expected, DIGITS),
            "worked_hours": round(worked, DIGITS),
            "deviation_hours": round(worked - expected, DIGITS),
            "unexplained_days": unexplained_days,
        }

    def _time_account_compute(self, date_from, date_to, finished_before=None):
        """Compute the entries of the periods starting within the dates.

        Nothing is stored. Used by :meth:`_time_account_update`, and to check
        closed or taken over periods against what the module would compute.

        :param date finished_before: leave out periods that end on this date or later
        :return: ``[(values, hr.version)]`` ordered by date; ``hours`` and ``state``
            are not part of the values, see :meth:`_time_account_booking`
        """
        self.ensure_one()
        if date_from > date_to:
            return []
        # periods may reach back to a Monday and ahead to the end of a month
        horizon = date_to + timedelta(days=31)
        versions = self._time_account_versions(date_from, horizon)
        periods = [
            period
            for period in self._time_account_periods(date_from, date_to, versions)
            if period[3] != "none"
            and (not finished_before or period[1] < finished_before)
        ]
        if not periods:
            return []
        first, last = periods[0][0], periods[-1][1]
        data = {
            "worked": self._time_account_worked_hours(first, last),
            "deducted": self._time_account_deducted_days(first, last),
            "calendar": {},
        }
        # Schedules with fixed days in one go. Schedules without fixed days per
        # period: Odoo spreads their weekly hours from the first day asked for.
        fixed = [
            period
            for period in versions
            if not period[2].resource_calendar_id._is_flexible()
        ]
        data["calendar"].update(self._time_account_calendar_hours(first, last, fixed))
        flexible = [period for period in versions if period not in fixed]
        result = []
        for start, end, version, kind in periods:
            if flexible:
                data["calendar"].update(
                    self._time_account_calendar_hours(start, end, flexible)
                )
            result.append(
                (
                    self._time_account_period_values(start, end, version, kind, data),
                    version,
                )
            )
        return result

    def _time_account_update(self, date_from=None, date_to=None):
        """Book the finished periods of the open part of the account.

        Entries of periods that are closed (see the lock date of the company) are
        never touched. Within the dates, entries that no longer match a period are
        removed, for example after the kind of period was changed.

        :param date date_from: defaults to the start of the account
        :param date date_to: defaults to yesterday
        """
        Line = (
            self.env["l10n_de.time.account.line"]
            .sudo()
            .with_context(time_account_system=True)
        )
        for employee in self.sudo():
            today = employee._time_account_today()
            if not employee.time_account_start:
                if not any(
                    employee._time_account_kind(version) != "none"
                    for version in employee.version_ids
                ):
                    continue
                employee.time_account_start = today
            start = max(
                date_from or employee.time_account_start, employee.time_account_start
            )
            lock_date = employee.company_id.time_account_lock_date
            if lock_date:
                start = max(start, lock_date + timedelta(days=1))
            end = min(date_to or today, today - timedelta(days=1))
            existing = {
                line.date_from: line
                for line in Line.search(
                    [
                        ("employee_id", "=", employee.id),
                        ("kind", "=", "deviation"),
                        ("date_from", ">=", start),
                        ("date_from", "<=", end),
                    ]
                )
            }
            for values, version in employee._time_account_compute(
                start, end, finished_before=today
            ):
                line = existing.pop(values["date_from"], Line)
                hours, state = employee._time_account_booking(
                    version, values["deviation_hours"], values["unexplained_days"], line
                )
                values.update(hours=hours, state=state)
                if not line:
                    Line.create(dict(values, employee_id=employee.id))
                    continue
                changed = {
                    name: value
                    for name, value in values.items()
                    if (
                        float_compare(line[name], value, precision_digits=DIGITS)
                        if isinstance(value, float)
                        else line[name] != value
                    )
                }
                if changed:
                    line.write(changed)
            if existing:
                Line.browse([line.id for line in existing.values()]).unlink()
        return True

    # ------------------------------------------------------------------
    # closed periods
    # ------------------------------------------------------------------

    def _time_account_closed_differences(self, date_from=None):
        """Closed periods that would be booked differently today.

        Attendances and time off can still change after a period was closed. The
        entry of the period stays as it is; the difference is booked as a
        correction in an open period, see :meth:`_time_account_correct_closed`.

        :return: ``[(line, hours)]``: the entry and the hours missing on it
        """
        self.ensure_one()
        employee = self.sudo()
        lock_date = employee.company_id.time_account_lock_date
        if not lock_date or not employee.time_account_start:
            return []
        start = max(
            date_from or employee.time_account_start, employee.time_account_start
        )
        lines = {
            line.date_from: line
            for line in self.env["l10n_de.time.account.line"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", employee.id),
                    ("kind", "=", "deviation"),
                    ("date_from", ">=", start),
                    ("date", "<=", lock_date),
                ]
            )
        }
        result = []
        for values, version in employee._time_account_compute(
            start, lock_date, finished_before=lock_date + timedelta(days=1)
        ):
            line = lines.get(values["date_from"])
            if not line or line.date != values["date"]:
                continue
            hours, state = employee._time_account_booking(
                version, values["deviation_hours"], 0, line
            )
            difference = round(hours - line.hours - line.correction_hours, DIGITS)
            if state == "booked" and difference:
                result.append((line, difference))
        return result

    def _time_account_correct_closed(self):
        """Book the differences of closed periods as corrections dated today."""
        Line = self.env["l10n_de.time.account.line"]
        corrections = Line
        for employee in self:
            for line, hours in employee._time_account_closed_differences():
                corrections += (
                    Line.sudo()
                    .with_context(time_account_system=True)
                    .create(
                        {
                            "employee_id": employee.id,
                            "date": employee._time_account_today(),
                            "date_from": employee._time_account_today(),
                            "kind": "adjustment",
                            "hours": hours,
                            "state": "booked",
                            "origin_line_id": line.id,
                            "name": self.env._(
                                "Change after closing: "
                                "period %(date_from)s to %(date_to)s",
                                date_from=format_date(self.env, line.date_from),
                                date_to=format_date(self.env, line.date),
                            ),
                        }
                    )
                )
                line.sudo().with_context(time_account_system=True).write(
                    {"correction_hours": line.correction_hours + hours}
                )
        return corrections

    # ------------------------------------------------------------------
    # § 2 (2) MiLoG
    # ------------------------------------------------------------------

    def _time_account_plus_hours_by_month(self):
        """Plus hours that are still on the account, by the month they were added.

        Minus hours, payouts and forfeitures use up the oldest plus hours first.

        :return: ``{first day of the month: hours}``, only months with hours left
        """
        self.ensure_one()
        lines = (
            self.env["l10n_de.time.account.line"]
            .sudo()
            .search(
                [("employee_id", "=", self.id), ("state", "=", "booked")],
                order="date, id",
            )
        )
        months = {}
        debt = 0.0
        for line in lines:
            if line.hours > 0:
                hours = line.hours
                if debt:
                    used = min(debt, hours)
                    debt -= used
                    hours -= used
                if hours:
                    month = line.date.replace(day=1)
                    months[month] = months.get(month, 0.0) + hours
                continue
            remaining = -line.hours
            for month in sorted(months):
                used = min(months[month], remaining)
                months[month] -= used
                remaining -= used
                if not remaining:
                    break
            debt += remaining
        return {
            month: round(hours, DIGITS)
            for month, hours in months.items()
            if round(hours, DIGITS) > 0
        }

    def _time_account_monitor(self):
        """Refresh the warnings of the account and notify the responsible person.

        For employees whose current contract version is monitored under § 2 (2)
        MiLoG: plus hours have to be compensated within twelve calendar months
        after the month they were added, and a month may add at most half of the
        agreed monthly working time. Independent of that: an employee who leaves
        should not leave with a balance.
        """
        for employee in self.sudo():
            today = employee._time_account_today()
            warnings = []
            due_date = False
            due_hours = 0.0
            version = employee.version_id
            if version.time_account_milog and employee.time_account_start:
                months = employee._time_account_plus_hours_by_month()
                if months:
                    oldest = min(months)
                    due_date = oldest + relativedelta(months=13, days=-1)
                    due_hours = months[oldest]
                    if due_date <= today + timedelta(days=MILOG_NOTICE_DAYS):
                        warnings.append(
                            self.env._(
                                "§ 2 (2) MiLoG: %(hours).2f plus hours from %(month)s "
                                "must be compensated by %(date)s.",
                                hours=due_hours,
                                month=format_date(
                                    self.env, oldest, date_format="MM/yyyy"
                                ),
                                date=format_date(self.env, due_date),
                            )
                        )
                warnings += employee._time_account_monthly_share_warnings(today)
            departure_date = (
                "departure_date" in employee._fields and employee.departure_date
            )
            balance = employee._time_account_balance_at(today)
            if departure_date and round(balance, 2):
                warnings.append(
                    self.env._(
                        "The employee leaves on %(date)s with a balance of "
                        "%(hours).2f hours. § 2 (2) MiLoG: compensate it in the "
                        "calendar month after the end of the employment at the "
                        "latest.",
                        date=format_date(self.env, departure_date),
                        hours=balance,
                    )
                )
            text = "\n".join(warnings) or False
            notify = text and text != employee.time_account_warning
            employee.write(
                {
                    "time_account_due_date": due_date,
                    "time_account_due_hours": due_hours,
                    "time_account_warning": text,
                }
            )
            if notify:
                employee._time_account_notify(text)
        return True

    def _time_account_monthly_share_warnings(self, today):
        """Months of the last twelve that added more than half of the agreed time."""
        self.ensure_one()
        first_month = max(
            today.replace(day=1) - relativedelta(months=12),
            self.time_account_start.replace(day=1),
        )
        added = defaultdict(float)
        for line in (
            self.env["l10n_de.time.account.line"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", self.id),
                    ("state", "=", "booked"),
                    ("kind", "=", "deviation"),
                    ("hours", ">", 0),
                    ("date", ">=", first_month),
                ]
            )
        ):
            added[line.date.replace(day=1)] += line.hours
        warnings = []
        for month in sorted(added):
            month_end = month + relativedelta(day=31)
            versions = self._time_account_versions(month, month_end)
            agreed = sum(
                scheduled
                for scheduled, _expected in self._time_account_calendar_hours(
                    month, month_end, versions
                ).values()
            )
            if agreed and added[month] > MILOG_MONTHLY_SHARE * agreed:
                warnings.append(
                    self.env._(
                        "§ 2 (2) MiLoG: %(month)s added %(hours).2f plus hours, more "
                        "than half of the agreed %(agreed).2f hours.",
                        month=format_date(self.env, month, date_format="MM/yyyy"),
                        hours=added[month],
                        agreed=agreed,
                    )
                )
        return warnings

    def _time_account_notify(self, text):
        """Schedule an activity for the person responsible for the employee.

        That is the attendance approver, or else the HR responsible of the
        contract version, which Odoo always sets.
        """
        self.ensure_one()
        employee = self.sudo()
        employee.activity_schedule(
            "l10n_de_hr_attendance_time_account.mail_activity_type_time_account",
            user_id=(employee.attendance_manager_id or employee.hr_responsible_id).id,
            note=Markup("<br/>").join(text.split("\n")),
        )

    # ------------------------------------------------------------------
    # scheduled action
    # ------------------------------------------------------------------

    @api.model
    def _cron_time_account(self):
        """Book the finished periods of all accounts and refresh their warnings."""
        versions = (
            self.env["hr.version"]
            .sudo()
            .search(
                [
                    ("time_account_period", "!=", "none"),
                    ("employee_id", "!=", False),
                ]
            )
        )
        employees = versions.employee_id | self.sudo().search(
            [("time_account_start", "!=", False)]
        )
        employees._time_account_update()
        employees._time_account_monitor()
        return True
