# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Legal breaks, the daily maximum and the automatic check-out."""

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
            }
        )
        cls.flexible = cls.env["resource.calendar"].create(
            {"name": "Flexible", "flexible_hours": True, "tz": "UTC"}
        )
        cls.user = new_test_user(cls.env, login="arbzg_user", groups="base.group_user")
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Erika Muster",
                "user_id": cls.user.id,
                "resource_calendar_id": cls.flexible.id,
                "tz": "UTC",
            }
        )
        cls.Attendance = cls.env["hr.attendance"]

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
            [("employee_id", "=", (employee or self.employee).id), ("date", "=", DAY)],
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

    def test_break_of_the_working_schedule_counts(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "With lunch",
                "tz": "UTC",
                "attendance_ids": [
                    (0, 0, vals)
                    for vals in (
                        {
                            "name": "Morning",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                        {
                            "name": "Lunch",
                            "dayofweek": "0",
                            "hour_from": 12,
                            "hour_to": 13,
                            "day_period": "lunch",
                        },
                        {
                            "name": "Afternoon",
                            "dayofweek": "0",
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "afternoon",
                        },
                    )
                ],
            }
        )
        employee = self.env["hr.employee"].create(
            {"name": "Max Beispiel", "resource_calendar_id": calendar.id, "tz": "UTC"}
        )
        self.attend(at(8), at(16), employee=employee)
        self.assertEqual(self.times(employee), [("08:00", "16:00")])
        self.assertEqual(self.worked(employee), 7.0)

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

    # ------------------------------------------------------------------
    # who is checked
    # ------------------------------------------------------------------

    def test_exempt_employee(self):
        self.employee.arbzg_exempt = True
        self.attend(at(8), at(15))
        self.assertEqual(self.times(), [("08:00", "15:00")])

    def test_freelancer(self):
        self.employee.employee_type = "freelance"
        self.attend(at(8), at(15))
        self.assertEqual(self.times(), [("08:00", "15:00")])

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

    def test_auto_check_out_with_the_schedule_break(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "With lunch",
                "tz": "UTC",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Lunch",
                            "dayofweek": "0",
                            "hour_from": 12,
                            "hour_to": 13,
                            "day_period": "lunch",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Day",
                            "dayofweek": "0",
                            "hour_from": 7,
                            "hour_to": 12,
                            "day_period": "morning",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Afternoon",
                            "dayofweek": "0",
                            "hour_from": 13,
                            "hour_to": 18,
                            "day_period": "afternoon",
                        },
                    ),
                ],
            }
        )
        employee = self.env["hr.employee"].create(
            {"name": "Max Beispiel", "resource_calendar_id": calendar.id, "tz": "UTC"}
        )
        attendance = self.attend(at(7), employee=employee)
        with freeze_time(at(18, 30)):
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertEqual(attendance.check_out, at(18))
        self.assertEqual(self.worked(employee), 10.0)

    def test_auto_check_out_switched_off(self):
        self.company.arbzg_auto_check_out = False
        attendance = self.attend(at(7))
        with freeze_time(at(20)):
            self.Attendance._cron_arbzg_auto_check_out()
        self.assertFalse(attendance.check_out)

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
