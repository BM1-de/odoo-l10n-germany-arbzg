# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Legal breaks and the daily maximum of the Working Time Act on attendances.

Every time an attendance of a day is created or changed, the whole day of the
employee is checked again:

- **Breaks (§ 4 ArbZG):** more than 6 hours of work need 30 minutes of break,
  more than 9 hours 45 minutes (both limits per company). Breaks are gaps of
  at least 15 minutes between two attendances, breaks inserted before and the
  break duration recorded on an attendance, which Odoo deducts from the worked
  hours. A break is only required for the time above a limit: 6:10 hours of
  work need 10 minutes. A missing break is put into the middle of the longest
  attendance, or only pointed out (per company).
- **Maximum (§ 3 ArbZG):** more than 10 hours of work a day are not
  shortened, because the attendances must show the real time (§ 16 (2)
  ArbZG). The employee gets a message, the responsible person an activity,
  once per day.
- **Forgotten check-out:** a scheduled action checks out open attendances as
  soon as the maximum is reached, plus the break that is still missing.

Work are the attendances that are not refused and whose time type counts as
working time; the lines that the time rules of Odoo add for missing time are
no work.

**Time rules of Odoo:** they cut the time above the schedule off an attendance
as a line of its own. The day is checked before they evaluate it
(``_trigger_time_rules``), so they see the day with its legal break, and the
writes of the check never start them: a split is two writes, and the rules
must not see the day in between.
"""

from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from markupsafe import Markup

from odoo import api, fields, models

#: a change of these fields changes the work or the breaks of a day
CHECKED_FIELDS = frozenset(
    {
        "check_in",
        "check_out",
        "employee_id",
        "break_duration",
        "work_entry_type_id",
        "state",
    }
)


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
        # Odoo 19 sets out_mode from technical to manual itself when check_out
        # is written, in_mode only when check_in is written (since 18.11.2026,
        # not yet in Odoo 20): remember the technical entries before, see
        # _arbzg_fix_technical
        technical = self.browse()
        if {"check_in", "check_out"} & set(vals):
            technical = self.filtered(
                lambda attendance: attendance.in_mode == "technical"
                and attendance.out_mode == "technical"
            )
        result = super().write(vals)
        technical.filtered(
            lambda attendance: attendance.check_out
            and attendance.employee_id._arbzg_applies()
        )._arbzg_fix_technical(entirely=True)
        if CHECKED_FIELDS & set(vals):
            self._arbzg_check()
        return result

    def _trigger_time_rules(self):
        """Check the day before the time rules of Odoo evaluate it.

        They must count the day with its legal break: a break inserted after
        them would leave overtime lines that are longer than the work was.
        Attendances that wait for their approval are no source of the rules yet
        and are checked after the write as usual.
        """
        self.filtered(lambda attendance: attendance.state == "validated")._arbzg_check()
        return super()._trigger_time_rules()

    # ------------------------------------------------------------------
    # check of a day
    # ------------------------------------------------------------------

    def _arbzg_check(self):
        """Check the days of these attendances against the Working Time Act.

        Not for the writes of the time rules of Odoo, of a refusal and of the
        automatic check-out of Odoo (``skip_time_rules``): they are steps in
        between, the day is checked before or after them.
        """
        context = self.env.context
        if context.get("arbzg_skip") or context.get("skip_time_rules"):
            return
        days = {
            (attendance.employee_id, attendance.date)
            for attendance in self
            if attendance.check_out and attendance.employee_id._arbzg_applies()
        }
        for employee, day in sorted(days, key=lambda key: (key[0].id, key[1])):
            self._arbzg_check_day(employee, day)

    @api.model
    def _arbzg_work_domain(self, employee, day):
        """The attendances of a day that are work: not refused, of a time type
        that counts as working time, and no line for missing time."""
        return [
            ("employee_id", "=", employee.id),
            ("date", "=", day),
            ("state", "!=", "refused"),
            ("work_entry_type_id.count_as", "=", "working_time"),
            "|",
            ("time_rule_id", "=", False),
            ("time_rule_id.threshold_operator", "=", "exceed"),
        ]

    @api.model
    def _arbzg_check_day(self, employee, day):
        company = employee.company_id
        # the own writes start neither this check nor the time rules of Odoo
        attendances = (
            self.sudo()
            .with_context(arbzg_skip=True, skip_time_rules=True)
            .search(self._arbzg_work_domain(employee, day), order="check_in")
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

    def _arbzg_fix_technical(self, entirely=False):
        """Odoo's absence management creates technical entries of one second.

        Once someone corrects such an entry to real times, it is a normal entry;
        otherwise it would stay red and count as technical. The part split off
        by an inserted break has only ``in_mode`` technical and keeps it.

        ``entirely``: these attendances were technical on both sides before
        their times were changed. Odoo may then have set ``out_mode`` to manual
        itself already, but leaves ``in_mode`` technical if only ``check_out``
        changed.
        """
        for attendance in self:
            if (entirely or attendance.out_mode == "technical") and _hours(
                attendance.check_out - attendance.check_in
            ) > 1 / 60.0:
                attendance.write(
                    {
                        field: "manual"
                        for field in ("in_mode", "out_mode")
                        if attendance[field] == "technical"
                    }
                )

    def _arbzg_work_and_breaks(self):
        """Hours of work and of breaks of these attendances (sorted, one day).

        Breaks are the gaps between attendances from the shortest break on, the
        gap before a part split off by an inserted break (``in_mode``
        technical), and the break duration recorded on an attendance, which
        Odoo deducts from the worked hours.
        """
        if not self:
            return 0.0, 0.0
        min_gap = self[0].employee_id.company_id.arbzg_min_break_minutes / 60.0
        work = sum(self.mapped("worked_hours"))
        breaks = 0.0
        previous = False
        for attendance in self:
            breaks += attendance.break_duration
            if previous:
                gap = _hours(attendance.check_in - previous.check_out)
                if gap >= min_gap or attendance.in_mode == "technical":
                    breaks += gap
            previous = attendance
        return work, breaks

    def _arbzg_insert_break(self, minutes):
        """Split the longest attendance of the day by a break of ``minutes``.

        The part split off keeps the time type, the status and the time rule
        of the attendance. Returns False if the break does not fit into it.
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
                "work_entry_type_id": target.work_entry_type_id.id,
                "state": target.state,
                "time_rule_id": target.time_rule_id.id,
                "source_attendance_id": target.source_attendance_id.id,
            }
        )
        employee = target.employee_id
        tz = ZoneInfo(employee._get_tz() or "UTC")
        env = target._arbzg_employee_env()
        target.with_env(env).message_post(
            body=env._(
                "Legal break: %(minutes)s minutes inserted automatically "
                "(%(start)s–%(end)s), because no sufficient break was recorded on "
                "this day.",
                minutes=minutes,
                start=start.replace(tzinfo=UTC).astimezone(tz).strftime("%H:%M"),
                end=end.replace(tzinfo=UTC).astimezone(tz).strftime("%H:%M"),
            ),
            message_type="comment",
            subtype_xmlid="mail.mt_note",
            author_id=self.env.ref("base.partner_root").id,
        )
        return True

    def _arbzg_set_missing_break(self, minutes):
        """Show a break that was not inserted on the longest attendance.

        It stays on the attendance that shows it already: the time rules of
        Odoo may cut the longest attendance, and the employee is told once.
        """
        target = self.filtered("arbzg_missing_break")[:1] or max(
            self, key=lambda attendance: attendance.worked_hours
        )
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
        for attendance in self.sudo().search(
            [("check_out", "=", False), ("state", "!=", "refused")]
        ):
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
        checking out.
        """
        self.ensure_one()
        company = self.employee_id.company_id
        earlier = self.sudo().search(
            [
                *self._arbzg_work_domain(self.employee_id, self.date),
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
        missing = max(company.arbzg_break_minutes_2 / 60.0 - breaks, 0.0)
        return self.check_in + timedelta(hours=rest + missing)
