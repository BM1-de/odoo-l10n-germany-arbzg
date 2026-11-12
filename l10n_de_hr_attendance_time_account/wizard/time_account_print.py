# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class L10nDeTimeAccountPrint(models.TransientModel):
    _name = "l10n_de.time.account.print"
    _description = "Print Working Time Account Documents"

    @api.model
    def _default_employee_ids(self):
        if self.env.context.get("active_model") == "hr.employee":
            return self.env.context.get("active_ids", [])
        return self.env.user.employee_id.ids

    document = fields.Selection(
        [
            ("statement", "Account Statement"),
            ("timesheet", "Record of Working Time"),
        ],
        required=True,
        default="statement",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Employees",
        required=True,
        default=lambda self: self._default_employee_ids(),
    )
    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self)
        + relativedelta(months=-1, day=1),
    )
    date_to = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self)
        + relativedelta(day=1, days=-1),
    )

    def action_print(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(self.env._("The period ends before it starts."))
        # only what the user may read: record rules of the entries and attendances
        employees = self.employee_ids
        if self.document == "statement":
            employees._time_account_update()
            report = "l10n_de_hr_attendance_time_account.action_report_statement"
        else:
            report = "l10n_de_hr_attendance_time_account.action_report_timesheet"
        return self.env.ref(report).report_action(
            employees,
            data={
                "employee_ids": employees.ids,
                "date_from": fields.Date.to_string(self.date_from),
                "date_to": fields.Date.to_string(self.date_to),
            },
        )
