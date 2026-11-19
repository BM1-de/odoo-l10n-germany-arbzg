# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Legal breaks, the daily maximum, the automatic check-out and the time rules."""

from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

DAY = datetime(2026, 10, 5)  # a Monday


def at(hours, minutes=0):
    return DAY + timedelta(hours=hours, minutes=minutes)


@tagged("post_install", "-at_install")
class TestArbzg(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "arbzg_enabled": True,
                "arbzg_break_mode": "insert",
                "arbzg_auto_check_out": True,
                "arbzg_responsible_id": cls.env.ref("base.user_admin").id,
                "attendance_validation": "no_validation",
            }
        )
        # the time rules of Odoo cut attendances into pieces; the tests of the
        # time rules turn their own rules on
        cls.env["hr.time.rule"].search([]).active = False
        cls.work = cls.company.attendance_work_entry_type_id
        cls.overtime = cls.env["hr.work.entry.type"].create(
            {"name": "Overtime (test)", "code": "ARBZGOT"}
        )
        cls.missing = cls.env["hr.work.entry.type"].create(
            {"name": "Missing time (test)", "code": "ARBZGMISS", "count_as": "absence"}
        )
        cls.rule_more = cls.env["hr.time.rule"].create(
            {
                "name": "More than the schedule",
                "threshold_operator": "exceed",
                "work_entry_type_id": cls.overtime.id,
                "active": False,
            }
        )
        cls.rule_less = cls.env["hr.time.rule"].create(
            {
                "name": "Less than the schedule",
                "threshold_operator": "less_than",
                "work_entry_type_id": cls.missing.id,
                "active": False,
            }
        )
        cls.flexible = cls.env["resource.calendar"].create(
            {"name": "Flexible", "calendar_type": "undefined"}
        )
        # the messages are compared in English, whatever the language of the database
        cls.user = new_test_user(
            cls.env, login="arbzg_user", groups="base.group_user", lang="en_US"
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Erika Muster",
                "user_id": cls.user.id,
                "resource_calendar_id": cls.flexible.id,
                "tz": "UTC",
                "date_version": "2026-01-01",
            }
        )
        cls.Attendance = cls.env["hr.attendance"]

    @classmethod
    def scheduled(cls, *hours):
        """An employee who works Monday to Friday at these hours."""
        calendar = cls.env["resource.calendar"].create(
            {
                "name": "Schedule",
                "company_id": cls.company.id,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "dayofweek": str(weekday),
                            "hour_from": hour_from,
                            "hour_to": hour_to,
                        },
                    )
                    for weekday in range(5)
                    for hour_from, hour_to in hours
                ],
            }
        )
        employee = cls.env["hr.employee"].create(
            {
                "name": "Max Beispiel",
                "resource_calendar_id": calendar.id,
                "tz": "UTC",
                "date_version": "2026-01-01",
            }
        )
        employee.work_contact_id.lang = "en_US"
        return employee

    def attend(self, start, end=None, employee=None, **vals):
        vals.update(
            {
                "employee_id": (employee or self.employee).id,
                "check_in": start,
                "check_out": end,
            }
        )
        return self.Attendance.create(vals)

    def day(self, employee=None):
        return self.Attendance.search(
            [
                ("employee_id", "=", (employee or self.employee).id),
                ("date", "=", DAY.date()),
            ],
            order="check_in",
        )

    def times(self, employee=None):
        return [
            (att.check_in.strftime("%H:%M"), att.check_out.strftime("%H:%M"))
            for att in self.day(employee)
        ]

    def worked(self, employee=None):
        return round(sum(self.day(employee).mapped("worked_hours")), 4)

    def bodies(self, attendances):
        return " ".join(attendances.message_ids.mapped("body"))

    # ------------------------------------------------------------------
    # breaks
    # ------------------------------------------------------------------

    def test_break_inserted_in_the_middle(self):
        self.attend(at(8), at(15))
        self.assertEqual(self.times(), [("08:00", "11:15"), ("11:45", "15:00")])
        self.assertEqual(self.worked(), 6.5)
        first, second = self.day()
        self.assertEqual(second.in_mode, "technical")
        self.assertEqual(second.out_mode, "manual")
        self.assertIn("30 minutes inserted", self.bodies(first))
        self.assertIn("11:15–11:45", self.bodies(first))

    def test_only_the_time_above_the_limit(self):
        self.attend(at(8), at(14, 10))
        self.assertEqual(self.times(), [("08:00", "11:00"), ("11:10", "14:10")])
        self.assertEqual(self.worked(), 6.0)

    def test_short_gap_is_no_break(self):
        self.attend(at(8), at(12))
        self.attend(at(12, 10), at(15, 30))
        # 7:20 hours of work, the 10 minutes do not count: 30 minutes in the
        # longest attendance, the first one
        self.assertEqual(
            self.times(),
            [("08:00", "09:45"), ("10:15", "12:00"), ("12:10", "15:30")],
        )
        self.assertEqual(self.worked(), round(7 + 20 / 60 - 0.5, 4))

    def test_longer_break_after_nine_hours(self):
        self.attend(at(8), at(12))
        self.attend(at(12, 30), at(18))
        # 9:30 hours of work and 30 minutes of break: 15 minutes are missing
        self.assertEqual(
            self.times(),
            [("08:00", "12:00"), ("12:30", "15:07"), ("15:22", "18:00")],
        )
        self.assertEqual(self.worked(), round(9.5 - 0.25, 4))

    def test_enough_break_changes_nothing(self):
        self.attend(at(8), at(12))
        self.attend(at(12, 30), at(16, 30))
        self.assertEqual(self.times(), [("08:00", "12:00"), ("12:30", "16:30")])
        self.assertFalse(any(self.day().mapped("arbzg_missing_break")))

    def test_up_to_six_hours_no_break(self):
        self.attend(at(8), at(14))
        self.assertEqual(self.times(), [("08:00", "14:00")])

    def test_open_attendance_is_not_checked(self):
        first = self.attend(at(8), at(12))
        self.attend(at(12, 5))
        self.assertEqual(len(self.day()), 2)
        # a day with an open attendance waits for the check-out
        first.write({"check_out": at(12, 1)})
        self.assertEqual(len(self.day()), 2)

    def test_removed_break_comes_back(self):
        self.attend(at(8), at(15))
        first, second = self.day()
        second.unlink()
        first.write({"check_out": at(15)})
        self.assertEqual(self.times(), [("08:00", "11:15"), ("11:45", "15:00")])

    def test_shorter_real_break_is_completed(self):
        self.attend(at(8), at(12))
        self.attend(at(12, 15), at(16, 15))
        # 8 hours of work, 15 minutes of break: 15 more minutes, in the first of
        # the two equally long attendances
        self.assertEqual(
            self.times(),
            [("08:00", "09:52"), ("10:07", "12:00"), ("12:15", "16:15")],
        )
        self.assertEqual(self.worked(), 7.75)

    def test_recorded_break_counts(self):
        # Odoo 20 deducts the break duration recorded on the attendance
        self.attend(at(8), at(16), break_duration=1.0)
        self.assertEqual(self.times(), [("08:00", "16:00")])
        self.assertEqual(self.worked(), 7.0)

    def test_shorter_recorded_break_is_completed(self):
        self.attend(at(8), at(16), break_duration=0.25)
        # 7:45 hours of work, 15 minutes of break: 15 more minutes
        self.assertEqual(self.times(), [("08:00", "11:52"), ("12:07", "16:00")])
        self.assertEqual(self.worked(), 7.5)
        self.assertEqual(self.day().mapped("break_duration"), [0.25, 0.0])

    def test_changed_recorded_break_is_checked(self):
        attendance = self.attend(at(8), at(16), break_duration=1.0)
        attendance.write({"break_duration": 0.0})
        self.assertEqual(self.times(), [("08:00", "11:45"), ("12:15", "16:00")])
        self.assertEqual(self.worked(), 7.5)

    def test_changed_recorded_break_is_checked_before_the_approval(self):
        self.company.attendance_validation = "manual_validation"
        attendance = self.attend(at(8), at(16), break_duration=1.0)
        attendance.write({"break_duration": 0.0})
        self.assertEqual(self.times(), [("08:00", "11:45"), ("12:15", "16:00")])
        self.assertEqual(self.day().mapped("state"), ["draft", "draft"])

    def test_gap_of_the_working_schedule_is_no_break(self):
        # Odoo 20 no longer deducts the lunch break of the working schedule:
        # 8 hours of work without a break
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), at(16), employee=employee)
        self.assertEqual(self.times(employee), [("08:00", "11:45"), ("12:15", "16:00")])
        self.assertEqual(self.worked(employee), 7.5)

    def test_corrected_technical_entry_becomes_manual(self):
        attendance = self.attend(
            at(8),
            at(8) + timedelta(seconds=1),
            in_mode="technical",
            out_mode="technical",
        )
        attendance.write({"check_out": at(12)})
        self.assertEqual(
            (attendance.in_mode, attendance.out_mode), ("manual", "manual")
        )
        other = self.attend(
            at(13),
            at(13) + timedelta(seconds=1),
            in_mode="systray",
            out_mode="technical",
        )
        other.write({"check_out": at(14)})
        self.assertEqual((other.in_mode, other.out_mode), ("systray", "manual"))

    def test_split_part_keeps_its_technical_start(self):
        self.attend(at(8), at(14, 10))
        first, second = self.day()
        self.assertEqual(second.in_mode, "technical")
        # only the end of the part after the inserted break is corrected: its
        # start stays technical, so the 10 minutes before it still count as
        # break, and 6:25 hours of work need 20 more minutes, not 25
        second.write({"check_out": at(14, 35)})
        self.assertEqual(
            self.times(),
            [("08:00", "11:00"), ("11:10", "12:42"), ("13:02", "14:35")],
        )
        self.assertEqual((second.in_mode, second.out_mode), ("technical", "manual"))

    # ------------------------------------------------------------------
    # who is checked
    # ------------------------------------------------------------------

    def test_exempt_employee(self):
        self.employee.arbzg_exempt = True
        self.attend(at(8), at(15))
        self.assertEqual(self.times(), [("08:00", "15:00")])

    def test_freelancer(self):
        self.employee.employee_type_id = self.env["hr.employee.type"].create(
            {"name": "Freelancer"}
        )
        self.employee.employee_type_id.arbzg_exempt = True
        self.attend(at(8), at(15))
        self.assertEqual(self.times(), [("08:00", "15:00")])

    def test_employee_type_that_is_not_exempt(self):
        self.employee.employee_type_id = self.env["hr.employee.type"].create(
            {"name": "Working student"}
        )
        self.attend(at(8), at(15))
        self.assertEqual(self.times(), [("08:00", "11:15"), ("11:45", "15:00")])

    def test_refused_attendance_is_no_work(self):
        self.company.attendance_validation = "manual_validation"
        # recorded without the check, as an import does
        self.Attendance.with_context(arbzg_skip=True).create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": at(8),
                    "check_out": at(11),
                },
                {
                    "employee_id": self.employee.id,
                    "check_in": at(11, 5),
                    "check_out": at(15),
                },
            ]
        )
        first, second = self.day()
        second.action_refuse()
        first.write({"check_out": at(11)})
        self.assertEqual(self.times(), [("08:00", "11:00"), ("11:05", "15:00")])
        # back to draft it is work again: 6:55 hours without a break
        second.action_reset_to_draft()
        self.assertEqual(
            self.times(),
            [("08:00", "11:00"), ("11:05", "12:47"), ("13:17", "15:00")],
        )
        self.assertEqual(self.day().mapped("state"), ["draft"] * 3)

    def test_attendance_of_an_absence_time_type_is_no_work(self):
        self.company.attendance_validation = "manual_validation"
        attendance = self.attend(at(8), at(15), work_entry_type_id=self.missing.id)
        self.assertEqual(self.times(), [("08:00", "15:00")])
        attendance.write({"work_entry_type_id": self.work.id})
        self.assertEqual(self.times(), [("08:00", "11:15"), ("11:45", "15:00")])

    def test_split_keeps_status_and_time_type(self):
        self.company.attendance_validation = "manual_validation"
        home = self.env.ref("hr_work_entry.generic_work_entry_type_home_working")
        self.attend(at(8), at(15), work_entry_type_id=home.id)
        self.assertEqual(self.times(), [("08:00", "11:15"), ("11:45", "15:00")])
        self.assertEqual(self.day().mapped("state"), ["draft", "draft"])
        self.assertEqual(self.day().work_entry_type_id, home)
        self.day().action_validate()
        self.assertEqual(self.times(), [("08:00", "11:15"), ("11:45", "15:00")])
        self.assertEqual(self.day().mapped("state"), ["validated", "validated"])

    def test_disabled_company(self):
        self.company.arbzg_enabled = False
        self.attend(at(8), at(15))
        self.assertEqual(self.times(), [("08:00", "15:00")])

    # ------------------------------------------------------------------
    # only point out
    # ------------------------------------------------------------------

    def test_notify_mode(self):
        self.company.arbzg_break_mode = "notify"
        attendance = self.attend(at(8), at(15))
        self.assertEqual(self.times(), [("08:00", "15:00")])
        self.assertEqual(attendance.arbzg_missing_break, 30)
        self.assertIn("30 minutes is missing", self.bodies(attendance))
        attendance.write({"check_out": at(15)})
        self.assertEqual(
            self.bodies(attendance).count("is missing"), 1, "reported only once"
        )
        attendance.write({"check_out": at(14, 5)})
        self.assertEqual(attendance.arbzg_missing_break, 5)
        attendance.write({"check_out": at(13)})
        self.assertEqual(attendance.arbzg_missing_break, 0)

    def test_break_recorded_after_the_check_out(self):
        # as "Break Management on Checkout" of Odoo does it
        self.company.write(
            {"arbzg_break_mode": "notify", "attendance_validation": "manual_validation"}
        )
        attendance = self.attend(at(8), at(15))
        self.assertEqual(attendance.arbzg_missing_break, 30)
        attendance.write({"break_duration": 0.5})
        self.assertEqual(attendance.arbzg_missing_break, 0)
        self.assertEqual(self.times(), [("08:00", "15:00")])

    def test_break_that_does_not_fit_is_pointed_out(self):
        # one hour of break after one hour of work, four attendances of 50
        # minutes with gaps of 10 minutes: the missing hour fits into none
        self.company.write(
            {
                "arbzg_break_hours_1": 1.0,
                "arbzg_break_minutes_1": 60,
                "arbzg_break_hours_2": 2.0,
                "arbzg_break_minutes_2": 60,
            }
        )
        self.Attendance.create(
            [
                {
                    "employee_id": self.employee.id,
                    "check_in": at(hour),
                    "check_out": at(hour, 50),
                }
                for hour in (8, 9, 10, 11)
            ]
        )
        self.assertEqual(len(self.day()), 4)
        first = self.day()[0]
        self.assertEqual(first.arbzg_missing_break, 60)
        self.assertFalse((self.day() - first).filtered("arbzg_missing_break"))
        self.assertIn("60 minutes is missing", self.bodies(first))

    # ------------------------------------------------------------------
    # maximum working time
    # ------------------------------------------------------------------

    def test_more_than_the_maximum_is_reported_not_shortened(self):
        self.attend(at(7), at(18, 30))
        # 11:30 hours, 45 minutes of break inserted: 10:45 hours stay
        self.assertEqual(self.worked(), 10.75)
        first = self.day()[0]
        self.assertTrue(first.arbzg_max_notified)
        self.assertIn("10:45 hours of work", self.bodies(first))
        self.assertIn(self.user.partner_id, first.message_ids.partner_ids)
        activity = self.env["mail.activity"].search(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.employee.id)]
        )
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity.user_id, self.env.ref("base.user_admin"))
        self.assertEqual(
            activity.activity_type_id,
            self.env.ref(
                "l10n_de_hr_attendance_arbzg.mail_activity_type_arbzg_maximum"
            ),
        )
        # a correction of the same day reports nothing again
        self.day()[-1].write({"check_out": at(18, 45)})
        self.assertEqual(
            self.env["mail.activity"].search_count(
                [("res_model", "=", "hr.employee"), ("res_id", "=", self.employee.id)]
            ),
            1,
        )

    def test_maximum_without_responsible(self):
        self.company.arbzg_responsible_id = False
        self.attend(at(7), at(18, 30))
        self.assertFalse(
            self.env["mail.activity"].search(
                [("res_model", "=", "hr.employee"), ("res_id", "=", self.employee.id)]
            )
        )
        self.assertTrue(self.day()[0].arbzg_max_notified)

    def test_maximum_to_the_attendance_approver(self):
        approver = new_test_user(
            self.env,
            login="arbzg_approver",
            groups="hr_attendance.group_hr_attendance_officer",
        )
        self.company.arbzg_responsible_id = False
        self.employee.attendance_manager_id = approver
        self.attend(at(7), at(18, 30))
        activity = self.env["mail.activity"].search(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.employee.id)]
        )
        self.assertEqual(activity.user_id, approver)

    # ------------------------------------------------------------------
    # forgotten check-out
    # ------------------------------------------------------------------

    def test_auto_check_out_at_the_maximum(self):
        attendance = self.attend(at(7))
        with freeze_time(at(17)):
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertFalse(attendance.check_out, "not yet at 17:00")
        with freeze_time(at(18)):
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertEqual(attendance.out_mode, "auto_check_out")
        # 10 hours of work plus the break of 45 minutes, which is inserted
        self.assertEqual(self.day()[-1].check_out, at(17, 45))
        self.assertEqual(self.worked(), 10.0)
        self.assertFalse(self.day()[0].arbzg_max_notified)
        self.assertIn("Checked out automatically", self.bodies(self.day()))

    def test_auto_check_out_counts_earlier_attendances(self):
        self.attend(at(7), at(11))
        attendance = self.attend(at(11, 30))
        with freeze_time(at(19)):
            self.Attendance._cron_arbzg_auto_check_out()
        # 4 hours before, 30 minutes of break, 6 more hours and 15 more
        # minutes of break: 17:45
        self.assertEqual(self.day()[-1].check_out, at(17, 45))
        self.assertEqual(self.worked(), 10.0)
        self.assertTrue(attendance.check_out)

    def test_auto_check_out_after_a_short_gap(self):
        self.attend(at(7), at(11))
        self.attend(at(11, 10))
        with freeze_time(at(19)):
            self.Attendance._cron_arbzg_auto_check_out()
        # the 10 minutes are no break: 4 + 6 hours of work and 45 minutes of
        # break, inserted into the longer second attendance
        self.assertEqual(self.day()[-1].check_out, at(17, 55))
        self.assertEqual(self.worked(), 10.0)

    def test_auto_check_out_with_a_recorded_break(self):
        self.attend(at(7), at(11), break_duration=0.5)
        self.attend(at(11, 10))
        with freeze_time(at(19)):
            self.Attendance._cron_arbzg_auto_check_out()
        # 3:30 hours of work and 30 minutes of break before, the 10 minutes are
        # no break: 6:30 more hours and 15 more minutes of break
        self.assertEqual(self.day()[-1].check_out, at(17, 55))
        self.assertEqual(self.worked(), 10.0)

    def test_auto_check_out_ignores_the_gap_of_the_schedule(self):
        # Odoo 20 no longer deducts the lunch break of the working schedule
        employee = self.scheduled((7, 12), (13, 18))
        self.attend(at(7), employee=employee)
        with freeze_time(at(17, 30)):
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertFalse(self.day(employee).check_out, "not yet at 17:30")
        with freeze_time(at(18, 30)):
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertEqual(self.times(employee), [("07:00", "12:00"), ("12:45", "17:45")])
        self.assertEqual(self.worked(employee), 10.0)

    def test_auto_check_out_skips_refused_attendances(self):
        attendance = self.attend(at(7))
        attendance.action_refuse()
        with freeze_time(at(20)):
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertFalse(attendance.check_out)

    def test_auto_check_out_switched_off(self):
        self.company.arbzg_auto_check_out = False
        attendance = self.attend(at(7))
        with freeze_time(at(20)):
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertFalse(attendance.check_out)

    # ------------------------------------------------------------------
    # time rules of Odoo
    # ------------------------------------------------------------------

    def rows(self, employee):
        """Times and time type of every attendance of the day."""
        return [
            (
                attendance.check_in.strftime("%H:%M"),
                attendance.check_out.strftime("%H:%M"),
                attendance.work_entry_type_id,
            )
            for attendance in self.day(employee)
        ]

    def test_time_rule_counts_the_day_with_the_break(self):
        self.rule_more.active = True
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), at(18), employee=employee)
        # 10 hours, 45 minutes of break inserted: 8 hours of work as scheduled
        # and 1:15 hours above, not the 2 hours without the break
        expected = [
            ("08:00", "12:37", self.work),
            ("13:22", "16:45", self.work),
            ("16:45", "18:00", self.overtime),
        ]
        self.assertEqual(self.rows(employee), expected)
        first, second, third = self.day(employee)
        self.assertEqual(first.worked_hours + second.worked_hours, 8.0)
        self.assertEqual(third.worked_hours, 1.25)
        self.assertEqual(third.source_attendance_id, second)
        self.assertEqual(third.time_rule_id, self.rule_more)
        self.assertFalse(any(self.day(employee).mapped("source_stale")))
        self.assertEqual(self.bodies(first).count("minutes inserted"), 1)
        # saving the day again changes nothing: no further break, no further line
        first.write({"check_out": first.check_out})
        second.write({"check_in": second.check_in})
        self.assertEqual(self.rows(employee), expected)
        self.assertEqual(self.bodies(self.day(employee)).count("minutes inserted"), 1)

    def test_check_in_and_out_by_the_employee(self):
        # as the menu of the attendances does it, with the rights of the user
        self.rule_more.active = True
        employee = self.scheduled((8, 12), (13, 17))
        employee.user_id = new_test_user(
            self.env,
            login="arbzg_scheduled",
            groups="base.group_user,hr_attendance.group_hr_attendance_own",
        )
        own = employee.with_user(employee.user_id).with_context(
            is_from_systray_check_in_out=True
        )
        with freeze_time(at(8)):
            own._attendance_action_change({"mode": "systray"})
        with freeze_time(at(18)):
            own._attendance_action_change({"mode": "systray"})
        self.assertEqual(
            self.rows(employee),
            [
                ("08:00", "12:37", self.work),
                ("13:22", "16:45", self.work),
                ("16:45", "18:00", self.overtime),
            ],
        )
        first, second, _third = self.day(employee)
        self.assertEqual((first.in_mode, first.out_mode), ("systray", "systray"))
        self.assertEqual((second.in_mode, second.out_mode), ("technical", "systray"))

    def test_time_rule_on_a_day_with_a_real_break(self):
        self.rule_more.active = True
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), at(12), employee=employee)
        self.attend(at(12, 45), at(18), employee=employee)
        self.assertEqual(
            self.rows(employee),
            [
                ("08:00", "12:00", self.work),
                ("12:45", "16:45", self.work),
                ("16:45", "18:00", self.overtime),
            ],
        )
        self.assertFalse(self.bodies(self.day(employee)).count("minutes inserted"))

    def test_time_rule_after_the_approval(self):
        self.rule_more.active = True
        self.company.attendance_validation = "manual_validation"
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), at(18), employee=employee)
        # the break at once, the time rule with the approval
        self.assertEqual(
            self.rows(employee),
            [("08:00", "12:37", self.work), ("13:22", "18:00", self.work)],
        )
        self.day(employee).action_validate()
        self.assertEqual(
            self.rows(employee),
            [
                ("08:00", "12:37", self.work),
                ("13:22", "16:45", self.work),
                ("16:45", "18:00", self.overtime),
            ],
        )
        self.assertEqual(set(self.day(employee).mapped("state")), {"validated"})

    def test_approval_within_the_tolerance_comes_first(self):
        self.rule_more.active = True
        self.company.write(
            {
                "attendance_validation": "tolerance_validation",
                "attendance_validation_tolerance": 1.0,
            }
        )
        # 8:30 hours are within the tolerance of the schedule: approved as a
        # whole, then the break, then the time rule (nothing above 8 hours)
        expected = [("08:00", "12:00", self.work), ("12:30", "16:30", self.work)]
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), at(16, 30), employee=employee)
        self.assertEqual(self.rows(employee), expected)
        self.assertEqual(self.day(employee).mapped("state"), ["validated", "validated"])
        # the same when checking out
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), employee=employee).write({"check_out": at(16, 30)})
        self.assertEqual(self.rows(employee), expected)
        self.assertEqual(self.day(employee).mapped("state"), ["validated", "validated"])
        # 10 hours are outside: they wait for the approval, with the break
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), at(18), employee=employee)
        self.assertEqual(
            self.rows(employee),
            [("08:00", "12:37", self.work), ("13:22", "18:00", self.work)],
        )
        self.assertEqual(self.day(employee).mapped("state"), ["draft", "draft"])

    def test_notify_mode_with_a_time_rule(self):
        self.rule_more.active = True
        self.company.arbzg_break_mode = "notify"
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), at(12), employee=employee)
        self.attend(at(12, 10), at(18, 10), employee=employee)
        # the time rule cuts the longest attendance, which shows the missing
        # break: it stays there and is reported once
        self.assertEqual(
            self.rows(employee),
            [
                ("08:00", "12:00", self.work),
                ("12:10", "16:10", self.work),
                ("16:10", "18:10", self.overtime),
            ],
        )
        self.assertEqual(self.day(employee).mapped("arbzg_missing_break"), [0, 45, 0])
        self.assertEqual(self.bodies(self.day(employee)).count("is missing"), 1)

    def test_lines_for_missing_time_are_no_work(self):
        self.rule_less.active = True
        employee = self.scheduled((8, 16))
        attendance = self.attend(at(8), at(14), employee=employee)
        # 2 hours are missing; Odoo adds a line for them, which is no work
        expected = [("08:00", "14:00", self.work), ("14:00", "16:00", self.missing)]
        self.assertEqual(self.rows(employee), expected)
        attendance.write({"check_out": at(14)})
        self.assertEqual(self.rows(employee), expected)
        self.assertFalse(self.bodies(self.day(employee)).count("minutes inserted"))

    def test_lines_for_missing_time_of_a_working_time_type(self):
        # the same with a time type for missing time that counts as working time
        self.missing.count_as = "working_time"
        self.rule_less.active = True
        employee = self.scheduled((8, 16))
        self.attend(at(8), at(14), employee=employee)
        self.assertEqual(
            self.rows(employee),
            [("08:00", "14:00", self.work), ("14:00", "16:00", self.missing)],
        )

    def test_split_with_a_rule_for_missing_time(self):
        self.rule_less.active = True
        employee = self.scheduled((8, 16))
        self.attend(at(8), at(16, 30), employee=employee)
        # 8 hours of work after the break: the rule must not see the day while
        # it is split, with the first half only
        self.assertEqual(
            self.rows(employee),
            [("08:00", "12:00", self.work), ("12:30", "16:30", self.work)],
        )

    def test_auto_check_out_with_a_time_rule(self):
        self.rule_more.active = True
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(7), employee=employee)
        expected = [
            ("07:00", "12:00", self.work),
            ("12:45", "15:45", self.work),
            ("15:45", "17:45", self.overtime),
        ]
        with freeze_time(at(18)):
            self.Attendance._cron_arbzg_auto_check_out()
            self.assertEqual(self.rows(employee), expected)
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertEqual(self.rows(employee), expected)
        self.assertEqual(self.worked(employee), 10.0)

    def test_auto_check_out_of_odoo(self):
        self.company.write(
            {
                "arbzg_auto_check_out": False,
                "auto_check_out": True,
                "auto_check_out_mode": "tolerance",
                "auto_check_out_tolerance": 2.0,
            }
        )
        employee = self.scheduled((8, 12), (13, 17))
        self.attend(at(8), employee=employee)
        with freeze_time(at(21)):
            self.Attendance._cron_auto_check_out()
        # Odoo first writes the end of the day and then the real check-out,
        # 2 hours after the 8 hours of the schedule: only that one is checked
        self.assertEqual(self.times(employee), [("08:00", "12:37"), ("13:22", "18:00")])
        self.assertFalse(any(self.day(employee).mapped("arbzg_max_notified")))
        self.assertFalse(
            self.env["mail.activity"].search(
                [("res_model", "=", "hr.employee"), ("res_id", "=", employee.id)]
            )
        )

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------

    def test_limits_are_checked(self):
        with self.assertRaises(ValidationError):
            self.company.arbzg_break_hours_2 = 5.0
        with self.assertRaises(ValidationError):
            self.company.arbzg_max_hours = 0
        with self.assertRaises(ValidationError):
            self.company.arbzg_min_break_minutes = 0

    def test_settings(self):
        settings = self.env["res.config.settings"].create({})
        settings.arbzg_max_hours = 8.0
        settings.execute()
        self.assertEqual(self.company.arbzg_max_hours, 8.0)
