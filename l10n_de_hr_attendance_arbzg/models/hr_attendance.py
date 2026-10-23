# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Legal breaks and the daily maximum of the Working Time Act on attendances.

Every time an attendance of a day is created or changed, the whole day of the
employee is checked again:

- **Breaks (§ 4 ArbZG):** more than 6 hours of work need 30 minutes of break,
  more than 9 hours 45 minutes (both limits per company). Breaks are gaps of
  at least 15 minutes between two attendances, breaks inserted before and the
  breaks of the working schedule that Odoo deducts from the worked hours. A
  break is only required for the time above a limit: 6:10 hours of work need
  10 minutes. A missing break is put into the middle of the longest
  attendance, or only pointed out (per company).
- **Maximum (§ 3 ArbZG):** more than 10 hours of work a day are not
  shortened, because the attendances must show the real time (§ 16 (2)
  ArbZG). The employee gets a message, the responsible person an activity,
  once per day.
- **Forgotten check-out:** a scheduled action checks out open attendances as
  soon as the maximum is reached, plus the break that is still missing.
"""

from datetime import timedelta

from markupsafe import Markup
from pytz import timezone, utc

from odoo import api, fields, models
from odoo.tools.date_utils import sum_intervals
from odoo.tools.intervals import Intervals


def _hours(delta):
    return delta.total_seconds() / 3600.0


def _clock(hours):
    """``10.75`` → ``"10:45"``."""
    whole, minutes = divmod(int(round(hours * 60)), 60)
    return f"{whole}:{minutes:02d}"


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    arbzg_missing_break = fields.Integer(
        string="Missing Break (Minutes)",
        readonly=True,
        copy=False,
        help="Break that is missing on this day according to the Working Time Act, "
        "if it was only pointed out and not inserted.",
    )
    arbzg_max_notified = fields.Boolean(
        string="Maximum Reported",
        readonly=True,
        copy=False,
        help="Technical: exceeding the maximum working time of this day was already "
        "reported.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        attendances = super().create(vals_list)
        attendances._arbzg_check()
        return attendances

    def write(self, vals):
        result = super().write(vals)
        if {"check_in", "check_out", "employee_id"} & set(vals):
            self._arbzg_check()
        return result

    # ------------------------------------------------------------------
    # check of a day
    # ------------------------------------------------------------------

    def _arbzg_check(self):
        """Check the days of these attendances against the Working Time Act."""
        if self.env.context.get("arbzg_skip"):
            return
        days = {
            (attendance.employee_id, attendance.date)
            for attendance in self
            if attendance.check_out and attendance.employee_id._arbzg_applies()
        }
        for employee, day in sorted(days, key=lambda key: (key[0].id, key[1])):
            self._arbzg_check_day(employee, day)

    @api.model
    def _arbzg_check_day(self, employee, day):
        company = employee.company_id
        attendances = (
            self.sudo()
            .with_context(arbzg_skip=True)
            .search(
                [("employee_id", "=", employee.id), ("date", "=", day)],
                order="check_in",
            )
        )
        if not attendances or not all(attendances.mapped("check_out")):
            return
        attendances._arbzg_fix_technical()
        work, breaks = attendances._arbzg_work_and_breaks()
        missing, work_left = company._arbzg_missing_break(work, breaks)
        if work_left > company.arbzg_max_hours + 1 / 120.0:
            attendances._arbzg_report_maximum(work_left)
        minutes = int(round(missing * 60))
        if (
            minutes
            and company.arbzg_break_mode == "insert"
            and attendances._arbzg_insert_break(minutes)
        ):
            minutes = 0
        attendances._arbzg_set_missing_break(minutes)

    def _arbzg_fix_technical(self):
        """Odoo's absence management creates technical entries of one second.

        Once someone corrects such an entry to real times, it is a normal entry;
        otherwise it would stay red and count as technical.
        """
        for attendance in self:
            if (
                attendance.out_mode == "technical"
                and _hours(attendance.check_out - attendance.check_in) > 1 / 60.0
            ):
                vals = {"out_mode": "manual"}
                if attendance.in_mode == "technical":
                    vals["in_mode"] = "manual"
                attendance.write(vals)

    def _arbzg_work_and_breaks(self):
        """Hours of work and of breaks of these attendances (sorted, one day).

        Breaks are the gaps between attendances from the shortest break on, the
        gap before a part split off by an inserted break (``in_mode``
        technical), and the breaks of the working schedule that Odoo deducts
        from the worked hours.
        """
        if not self:
            return 0.0, 0.0
        min_gap = self[0].employee_id.company_id.arbzg_min_break_minutes / 60.0
        work = sum(self.mapped("worked_hours"))
        breaks = 0.0
        previous = False
        for attendance in self:
            breaks += max(
                _hours(attendance.check_out - attendance.check_in)
                - attendance.worked_hours,
                0.0,
            )
            if previous:
                gap = _hours(attendance.check_in - previous.check_out)
                if gap >= min_gap or attendance.in_mode == "technical":
                    breaks += gap
            previous = attendance
        return work, breaks

    def _arbzg_insert_break(self, minutes):
        """Split the longest attendance of the day by a break of ``minutes``.

        Returns False if the break does not fit into it.
        """
        target = max(self, key=lambda attendance: attendance.worked_hours)
        duration = timedelta(minutes=minutes)
        middle = target.check_in + (target.check_out - target.check_in) / 2
        start = (middle - duration / 2).replace(second=0, microsecond=0)
        end = start + duration
        if start <= target.check_in or end >= target.check_out:
            return False
        rest_end = target.check_out
        rest_mode = target.out_mode if target.out_mode != "technical" else "manual"
        target.write({"check_out": start, "arbzg_missing_break": 0})
        self.create(
            {
                "employee_id": target.employee_id.id,
                "check_in": end,
                "check_out": rest_end,
                "in_mode": "technical",
                "out_mode": rest_mode,
            }
        )
        employee = target.employee_id
        tz = timezone(employee._get_tz() or "UTC")
        env = target._arbzg_employee_env()
        target.with_env(env).message_post(
            body=env._(
                "Legal break: %(minutes)s minutes inserted automatically "
                "(%(start)s–%(end)s), because no sufficient break was recorded on "
                "this day.",
                minutes=minutes,
                start=utc.localize(start).astimezone(tz).strftime("%H:%M"),
                end=utc.localize(end).astimezone(tz).strftime("%H:%M"),
            ),
            message_type="comment",
            subtype_xmlid="mail.mt_note",
            author_id=self.env.ref("base.partner_root").id,
        )
        return True

    def _arbzg_set_missing_break(self, minutes):
        """Show a break that was not inserted on the longest attendance."""
        target = max(self, key=lambda attendance: attendance.worked_hours)
        (self - target).filtered("arbzg_missing_break").write(
            {"arbzg_missing_break": 0}
        )
        if target.arbzg_missing_break == minutes:
            return
        target.write({"arbzg_missing_break": minutes})
        if minutes:
            env = target._arbzg_employee_env()
            target.with_env(env)._arbzg_message_employee(
                env._(
                    "On %(day)s, a break of %(minutes)s minutes is missing according "
                    "to the Working Time Act (§ 4 ArbZG). Please record your breaks "
                    "by checking out and in again, or correct the attendances.",
                    day=target._arbzg_day_text(),
                    minutes=minutes,
                )
            )

    def _arbzg_report_maximum(self, work):
        """Report more than the maximum working time, once per day."""
        if any(self.mapped("arbzg_max_notified")):
            return
        first = self[0]
        employee = first.employee_id
        company = employee.company_id
        first.write({"arbzg_max_notified": True})
        env = first._arbzg_employee_env()
        first.with_env(env)._arbzg_message_employee(
            env._(
                "On %(day)s, the attendances show %(hours)s hours of work. More than "
                "%(maximum)s hours of work per day are not allowed (§ 3 ArbZG); please "
                "finish work in time. If the time is wrong, please correct the "
                "attendance.",
                day=first._arbzg_day_text(),
                hours=_clock(work),
                maximum=_clock(company.arbzg_max_hours),
            )
        )
        responsible = company.arbzg_responsible_id or employee.attendance_manager_id
        if not responsible:
            return
        renv = self.env(context=dict(self.env.context, lang=responsible.lang))
        self.env["mail.activity"].sudo().create(
            {
                "res_model_id": self.env["ir.model"]._get_id("hr.employee"),
                "res_id": employee.id,
                "activity_type_id": self.env.ref(
                    "l10n_de_hr_attendance_arbzg.mail_activity_type_arbzg_maximum"
                ).id,
                "user_id": responsible.id,
                "summary": renv._(
                    "More than %(maximum)s hours of work on %(day)s",
                    maximum=_clock(company.arbzg_max_hours),
                    day=first.with_env(renv)._arbzg_day_text(),
                ),
                "note": renv._(
                    "%(employee)s worked %(hours)s hours according to the attendances; "
                    "at most %(maximum)s hours are allowed (§ 3 ArbZG). The "
                    "attendances stay as recorded.",
                    employee=employee.name,
                    hours=_clock(work),
                    maximum=_clock(company.arbzg_max_hours),
                ),
                "date_deadline": fields.Date.context_today(self),
            }
        )

    def _arbzg_message_employee(self, text):
        """Post ``text`` on this attendance and notify the employee's user."""
        self.ensure_one()
        partner = self.employee_id.user_id.partner_id
        self.message_post(
            body=Markup("<p>%s</p>") % text,
            message_type="comment",
            subtype_xmlid="mail.mt_comment" if partner else "mail.mt_note",
            partner_ids=partner.ids,
            author_id=self.env.ref("base.partner_root").id,
        )

    def _arbzg_employee_env(self):
        """Environment in the language of the employee, for the messages."""
        self.ensure_one()
        employee = self.employee_id.sudo()
        lang = (
            employee.user_id.lang
            or employee.work_contact_id.lang
            or employee.company_id.partner_id.lang
            or self.env.lang
        )
        return self.env(context=dict(self.env.context, lang=lang))

    def _arbzg_day_text(self):
        self.ensure_one()
        lang = self.env["res.lang"]._get_data(code=self.env.lang or "en_US")
        return self.date.strftime(lang.date_format or "%m/%d/%Y")

    # ------------------------------------------------------------------
    # forgotten check-out
    # ------------------------------------------------------------------

    @api.model
    def _cron_arbzg_auto_check_out(self):
        """Check out open attendances that reached the maximum working time."""
        now = fields.Datetime.now()
        for attendance in self.sudo().search([("check_out", "=", False)]):
            employee = attendance.employee_id
            if (
                not employee._arbzg_applies()
                or not employee.company_id.arbzg_auto_check_out
            ):
                continue
            limit = attendance._arbzg_check_out_limit()
            if now < limit:
                continue
            attendance.write(
                {
                    "check_out": max(limit, attendance.check_in + timedelta(minutes=1)),
                    "out_mode": "auto_check_out",
                }
            )
            env = attendance._arbzg_employee_env()
            attendance.with_env(env).message_post(
                body=env._(
                    "Checked out automatically: the maximum working time of the day "
                    "(%(maximum)s hours) was reached. Please correct the actual time "
                    "yourself.",
                    maximum=_clock(employee.company_id.arbzg_max_hours),
                ),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
                author_id=self.env.ref("base.partner_root").id,
            )

    def _arbzg_check_out_limit(self):
        """Moment at which this open attendance reaches the daily maximum.

        The break that is still missing is added, because it is inserted when
        checking out, and so are the breaks of the working schedule that Odoo
        deducts in between.
        """
        self.ensure_one()
        company = self.employee_id.company_id
        earlier = self.sudo().search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("date", "=", self.date),
                ("check_out", "!=", False),
                ("check_in", "<", self.check_in),
            ],
            order="check_in",
        )
        work, breaks = earlier._arbzg_work_and_breaks()
        if earlier:
            gap = _hours(self.check_in - earlier[-1].check_out)
            if gap >= company.arbzg_min_break_minutes / 60.0:
                breaks += gap
        rest = max(company.arbzg_max_hours - work, 0.0)
        longest_break = company.arbzg_break_minutes_2 / 60.0
        limit = self.check_in + timedelta(hours=rest)
        # the breaks of the schedule depend on the limit and vice versa: three
        # rounds are enough, a lunch break moves the limit at most once
        for _step in range(3):
            scheduled = self._arbzg_scheduled_breaks(self.check_in, limit)
            missing = max(longest_break - breaks - scheduled, 0.0)
            limit = self.check_in + timedelta(hours=rest + scheduled + missing)
        return limit

    def _arbzg_scheduled_breaks(self, start, end):
        """Hours of the working schedule's breaks between ``start`` and ``end``.

        The same breaks that Odoo deducts from the worked hours (lunch), see
        ``hr.attendance._get_worked_hours_in_range``.
        """
        self.ensure_one()
        resource = self.employee_id.resource_id
        if end <= start or resource._is_flexible():
            return 0.0
        calendar = self._get_employee_calendar()
        tz = timezone(resource.tz) if not calendar else timezone(calendar.tz)
        start_tz = utc.localize(start).astimezone(tz)
        end_tz = utc.localize(end).astimezone(tz)
        lunch = self.employee_id._employee_attendance_intervals(
            start_tz, end_tz, lunch=True
        )
        worked = sum_intervals(Intervals([(start_tz, end_tz, self)]) - lunch)
        return max(_hours(end - start) - worked, 0.0)
