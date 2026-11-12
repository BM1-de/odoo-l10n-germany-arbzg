# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from collections import defaultdict
from datetime import datetime, time
from zoneinfo import ZoneInfo

from odoo import api, fields, models

from ..models.hr_employee import _days, format_hours

UTC = ZoneInfo("UTC")


class TimeAccountReportMixin(models.AbstractModel):
    _name = "l10n_de.time.account.report.mixin"
    _description = "Working Time Account Report Helpers"

    @api.model
    def _get_period(self, docids, data):
        data = data or {}
        employees = self.env["hr.employee"].browse(data.get("employee_ids") or docids)
        today = fields.Date.context_today(self)
        date_from = fields.Date.to_date(data.get("date_from")) or today.replace(day=1)
        date_to = fields.Date.to_date(data.get("date_to")) or today
        return employees, date_from, date_to


class ReportTimeAccountStatement(models.AbstractModel):
    _name = "report.l10n_de_hr_attendance_time_account.report_statement"
    _inherit = "l10n_de.time.account.report.mixin"
    _description = "Working Time Account Statement"

    @api.model
    def _statement(self, employee, date_from, date_to):
        """Entries of the period with the running balance.

        The entries are read with the rights of the user, so everybody gets what
        the working time account shows them.
        """
        Line = self.env["l10n_de.time.account.line"]
        ((opening,),) = Line._read_group(
            [
                ("employee_id", "=", employee.id),
                ("state", "=", "booked"),
                ("date", "<", date_from),
            ],
            [],
            ["hours:sum"],
        )
        balance = opening or 0.0
        rows = []
        for line in Line.search(
            [
                ("employee_id", "=", employee.id),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ],
            order="date, id",
        ):
            if line.state == "booked":
                balance += line.hours
            rows.append({"line": line, "balance": balance})
        employee_sudo = employee.sudo()
        return {
            "employee": employee_sudo,
            "version": employee_sudo._get_version(date_to),
            "opening": opening or 0.0,
            "rows": rows,
            "closing": balance,
        }

    @api.model
    def _get_report_values(self, docids, data=None):
        employees, date_from, date_to = self._get_period(docids, data)
        return {
            "doc_ids": employees.ids,
            "doc_model": "hr.employee",
            "docs": [
                self._statement(employee, date_from, date_to) for employee in employees
            ],
            "date_from": date_from,
            "date_to": date_to,
            "format_hours": format_hours,
        }


class ReportTimeAccountTimesheet(models.AbstractModel):
    _name = "report.l10n_de_hr_attendance_time_account.report_timesheet"
    _inherit = "l10n_de.time.account.report.mixin"
    _description = "Record of Working Time"

    @api.model
    def _timesheet(self, employee, date_from, date_to):
        """Begin, end and duration of the working time per day, with time off.

        Attendances are read with the rights of the user. Time off and public
        holidays are shown by name only.
        """
        employee_sudo = employee.sudo()
        tz = ZoneInfo(employee_sudo._get_tz() or "UTC")
        attendances = defaultdict(list)
        for attendance in self.env["hr.attendance"].search(
            [
                ("employee_id", "=", employee.id),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("work_entry_type_id.count_as", "=", "working_time"),
            ],
            order="check_in",
        ):
            attendances[attendance.date].append(
                {
                    "check_in": attendance.check_in.replace(tzinfo=UTC)
                    .astimezone(tz)
                    .strftime("%H:%M"),
                    "check_out": attendance.check_out
                    and attendance.check_out.replace(tzinfo=UTC)
                    .astimezone(tz)
                    .strftime("%H:%M")
                    or "",
                    "break_hours": attendance.break_duration,
                    "worked_hours": attendance.worked_hours,
                }
            )
        start_dt = datetime.combine(date_from, time.min, tzinfo=tz)
        end_dt = datetime.combine(date_to, time.max, tzinfo=tz)
        absences = defaultdict(list)
        for leave in (
            self.env["resource.calendar.leaves"]
            .sudo()
            .search(
                [
                    ("resource_id", "in", [False, employee_sudo.resource_id.id]),
                    ("company_id", "in", [False, employee_sudo.company_id.id]),
                    ("date_from", "<=", end_dt.astimezone(UTC).replace(tzinfo=None)),
                    ("date_to", ">=", start_dt.astimezone(UTC).replace(tzinfo=None)),
                ],
                order="date_from",
            )
        ):
            name = leave.work_entry_type_id.name if leave.resource_id else leave.name
            first = leave.date_from.replace(tzinfo=UTC).astimezone(tz).date()
            last = leave.date_to.replace(tzinfo=UTC).astimezone(tz).date()
            for day in _days(max(first, date_from), min(last, date_to)):
                if name and name not in absences[day]:
                    absences[day].append(name)
        days = []
        total = 0.0
        for day in _days(date_from, date_to):
            worked = sum(row["worked_hours"] for row in attendances[day])
            total += worked
            days.append(
                {
                    "date": day,
                    "attendances": attendances[day],
                    "absences": ", ".join(absences[day]),
                    "worked_hours": worked,
                }
            )
        return {"employee": employee_sudo, "days": days, "total": total}

    @api.model
    def _get_report_values(self, docids, data=None):
        employees, date_from, date_to = self._get_period(docids, data)
        return {
            "doc_ids": employees.ids,
            "doc_model": "hr.employee",
            "docs": [
                self._timesheet(employee, date_from, date_to) for employee in employees
            ],
            "date_from": date_from,
            "date_to": date_to,
            "format_hours": format_hours,
        }
