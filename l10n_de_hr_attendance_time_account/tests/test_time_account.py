# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Working time account: computation, entries by hand, closing, take over."""

from datetime import date, datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

MONDAY = date(2026, 10, 5)
#: two weeks later, a Monday as well: both weeks before are finished
TODAY = "2026-10-19 10:00:00"


def day(offset):
    return MONDAY + timedelta(days=offset)


@tagged("post_install", "-at_install")
class TestTimeAccount(TransactionCase):
    _test_user_groups = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {"attendance_validation": "no_validation", "time_account_lock_date": False}
        )
        # the time rules of Odoo cut attendances into pieces; one test turns them on
        cls.env["hr.time.rule"].search([]).active = False
        cls.Line = cls.env["l10n_de.time.account.line"]
        cls.calendar = cls._calendar("40 hours", range(5), [(8, 12), (13, 17)])
        cls.user = new_test_user(
            cls.env, login="account_user", groups="base.group_user"
        )
        cls.manager = new_test_user(
            cls.env,
            login="account_manager",
            groups="hr_attendance.group_hr_attendance_manager,hr.group_hr_user",
        )
        cls.employee = cls._employee("Erika Muster", user_id=cls.user.id)
        cls.vacation = cls.env["hr.work.entry.type"].create(
            {"name": "Vacation", "code": "TAVAC", "count_as": "absence"}
        )
        cls.compensation = cls.env["hr.work.entry.type"].create(
            {
                "name": "Time off for plus hours",
                "code": "TACOMP",
                "count_as": "absence",
                "time_account_deduct": True,
            }
        )

    @classmethod
    def _calendar(cls, name, days, hours):
        return cls.env["resource.calendar"].create(
            {
                "name": name,
                "company_id": cls.env.company.id,
                "full_time_required_hours": 40,
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
                    for weekday in days
                    for hour_from, hour_to in hours
                ],
            }
        )

    @classmethod
    def _employee(cls, name, **values):
        return cls.env["hr.employee"].create(
            {
                "name": name,
                "tz": "UTC",
                "resource_calendar_id": cls.calendar.id,
                "date_version": "2026-01-01",
                "time_account_period": "day",
                "time_account_tolerance_plus": 0.25,
                "time_account_tolerance_minus": 0.25,
                "time_account_negative": True,
                "time_account_start": MONDAY,
                **values,
            }
        )

    def attend(self, offset, start, stop, employee=None):
        base = datetime.combine(day(offset), datetime.min.time())
        return self.env["hr.attendance"].create(
            {
                "employee_id": (employee or self.employee).id,
                "check_in": base + timedelta(hours=start),
                "check_out": base + timedelta(hours=stop),
            }
        )

    def absent(self, first, last, work_entry_type, employee=None):
        employee = employee or self.employee
        return self.env["resource.calendar.leaves"].create(
            {
                "name": work_entry_type.name,
                "resource_id": employee.resource_id.id,
                "calendar_id": employee.resource_calendar_id.id,
                "work_entry_type_id": work_entry_type.id,
                "count_as": "absence",
                "date_from": datetime.combine(day(first), datetime.min.time()),
                "date_to": datetime.combine(day(last), datetime.max.time()),
            }
        )

    def update(self, employee=None, now=TODAY):
        employee = employee or self.employee
        with freeze_time(now):
            employee._time_account_update()
        return self.Line.search(
            [("employee_id", "=", employee.id), ("kind", "=", "deviation")],
            order="date_from",
        )

    def booked(self, lines):
        return {line.date_from: (line.hours, line.state) for line in lines}

    def full_week(self, employee=None, offset=0):
        for weekday in range(5):
            self.attend(offset + weekday, 8, 16, employee)

    # ------------------------------------------------------------------
    # computation
    # ------------------------------------------------------------------

    def test_day_plus_minus_tolerance(self):
        self.attend(0, 8, 17.5)  # 9:30 instead of 8:00
        self.attend(1, 8, 15)  # 7:00
        self.attend(2, 8, 16 + 10 / 60)  # 8:10, within the tolerance
        self.attend(3, 8, 15.75)  # 7:45, exactly the tolerance
        self.attend(4, 8, 16)
        self.full_week(offset=7)
        lines = self.update()
        booked = self.booked(lines)
        self.assertEqual(booked[day(0)], (1.5, "booked"))
        self.assertEqual(booked[day(1)], (-1.0, "booked"))
        self.assertEqual(booked[day(2)], (0.0, "booked"))
        self.assertEqual(booked[day(3)], (0.0, "booked"))
        self.assertEqual(booked[day(5)], (0.0, "booked"), "Saturday: nothing expected")
        self.assertEqual(len(lines), 14, "one entry per finished day")
        first = lines[0]
        self.assertEqual(
            (
                first.expected_hours,
                first.worked_hours,
                first.deviation_hours,
                first.period,
            ),
            (8.0, 9.5, 1.5, "day"),
        )
        self.assertEqual(lines[2].deviation_hours, round(10 / 60, 4))
        self.assertEqual(self.employee.time_account_balance, 0.5)
        self.assertEqual(self.employee.time_account_balance_display, "+0:30")
        # computing again changes nothing
        ids = lines.ids
        self.assertEqual(self.update().ids, ids)

    def test_running_period_is_not_booked(self):
        self.full_week()
        self.full_week(offset=7)
        self.attend(14, 8, 12)  # today
        lines = self.update()
        self.assertEqual(lines[-1].date, day(13))

    def test_account_starts_when_first_computed(self):
        employee = self._employee("Neu Anfang", time_account_start=False)
        self.attend(0, 8, 18, employee)
        self.assertFalse(self.update(employee), "the account starts today")
        self.assertEqual(employee.time_account_start, day(14))
        without = self._employee(
            "Ohne Konto", time_account_start=False, time_account_period="none"
        )
        self.update(without)
        self.assertFalse(without.time_account_start)

    def test_no_minus_hours_without_agreement(self):
        self.employee.time_account_negative = False
        self.attend(0, 8, 14)
        self.attend(1, 8, 18)
        booked = self.booked(self.update())
        self.assertEqual(booked[day(0)], (0.0, "booked"))
        self.assertEqual(booked[day(1)], (2.0, "booked"))
        self.assertEqual(booked[day(2)], (0.0, "booked"), "no attendance, no minus")

    def test_week(self):
        self.employee.time_account_period = "week"
        self.attend(0, 8, 18)  # 10
        self.attend(1, 8, 18)  # 10
        self.attend(2, 8, 18)  # 10
        self.attend(3, 8, 20)  # 12: 42 hours on four days
        self.full_week(offset=7)
        lines = self.update()
        self.assertEqual(len(lines), 2)
        week = lines[0]
        self.assertEqual((week.date_from, week.date), (day(0), day(6)))
        self.assertEqual((week.expected_hours, week.worked_hours), (40.0, 42.0))
        # Friday has no attendance, so the week is to clarify only if it ends in
        # minus hours. It ends with plus hours: booked.
        self.assertEqual((week.hours, week.state), (2.0, "booked"))
        self.assertEqual(week.unexplained_days, 1)
        self.assertEqual((lines[1].hours, lines[1].period), (0.0, "week"))

    def test_month(self):
        self.employee.write(
            {"time_account_period": "month", "time_account_start": date(2026, 9, 1)}
        )
        first = date(2026, 9, 1)
        for offset in range(30):
            current = first + timedelta(days=offset)
            if current.weekday() < 5:
                self.attend((current - MONDAY).days, 8, 16.5)
        lines = self.update()
        self.assertEqual(len(lines), 1, "October is still running")
        month = lines[0]
        self.assertEqual((month.date_from, month.date), (first, date(2026, 9, 30)))
        # September 2026 has 22 working days
        self.assertEqual((month.expected_hours, month.worked_hours), (176.0, 187.0))
        self.assertEqual(month.hours, 11.0)

    def test_new_working_schedule(self):
        """A new contract version with another schedule counts from its date."""
        part_time = self._calendar("20 hours", range(5), [(8, 12)])
        self.employee.create_version(
            {"date_version": day(2), "resource_calendar_id": part_time.id}
        )
        for weekday in range(5):
            self.attend(weekday, 8, 14)
        lines = self.update()
        booked = self.booked(lines)
        self.assertEqual(booked[day(1)], (-2.0, "booked"), "6 of 8 hours")
        self.assertEqual(booked[day(2)], (2.0, "booked"), "6 instead of 4 hours")
        self.assertEqual(lines[2].expected_hours, 4.0)

    def test_change_of_period_within_a_week(self):
        """The week ends early when the next version compares per day."""
        self.employee.version_id.time_account_period = "week"
        self.employee.create_version(
            {"date_version": day(3), "time_account_period": "day"}
        )
        self.full_week()
        lines = self.update()
        self.assertEqual(
            [(line.date_from, line.date, line.period) for line in lines[:3]],
            [
                (day(0), day(2), "week"),
                (day(3), day(3), "day"),
                (day(4), day(4), "day"),
            ],
        )
        self.assertEqual(lines[0].expected_hours, 24.0)

    def test_time_off_that_counts_as_worked(self):
        self.absent(0, 1, self.vacation)
        self.attend(2, 8, 16)
        booked = self.booked(self.update())
        self.assertEqual(booked[day(0)], (0.0, "booked"))
        self.assertEqual(booked[day(1)], (0.0, "booked"))
        self.assertEqual(booked[day(2)], (0.0, "booked"))
        line = self.Line.search(
            [("employee_id", "=", self.employee.id), ("date_from", "=", day(0))]
        )
        self.assertEqual((line.expected_hours, line.unexplained_days), (0.0, 0))

    def test_public_holiday(self):
        self.env["resource.calendar.leaves"].create(
            {
                "name": "Public holiday",
                "company_id": self.company.id,
                "date_from": datetime.combine(day(0), datetime.min.time()),
                "date_to": datetime.combine(day(0), datetime.max.time()),
            }
        )
        self.attend(0, 8, 10)  # worked on the public holiday: all of it is plus
        booked = self.booked(self.update())
        self.assertEqual(booked[day(0)], (2.0, "booked"))

    def test_time_off_deducted_from_the_account(self):
        self.absent(0, 0, self.compensation)
        lines = self.update()
        first = lines[0]
        self.assertEqual((first.expected_hours, first.worked_hours), (8.0, 0.0))
        self.assertEqual((first.hours, first.state), (-8.0, "booked"))
        self.assertEqual(first.unexplained_days, 0)

    def test_day_without_attendance_is_to_clarify(self):
        self.attend(1, 8, 16)
        lines = self.update()
        monday = lines[0]
        self.assertEqual((monday.hours, monday.state), (0.0, "to_clarify"))
        self.assertEqual((monday.deviation_hours, monday.unexplained_days), (-8.0, 1))
        self.assertEqual(self.employee.time_account_to_clarify, 9)
        with freeze_time(TODAY):
            # the time off was missing: enter it and the day is fine
            self.absent(2, 2, self.vacation)
            # Monday was not worked indeed
            monday.with_user(self.manager).action_confirm_minus()
            # on Thursday the employer had no work
            lines[3].with_user(self.manager).neutral_reason = "No work available"
        booked = self.booked(self.update())
        self.assertEqual(booked[day(0)], (-8.0, "booked"))
        self.assertEqual(booked[day(2)], (0.0, "booked"))
        self.assertEqual(booked[day(3)], (0.0, "booked"))
        self.assertEqual(booked[day(4)], (0.0, "to_clarify"))
        self.assertEqual(self.employee.time_account_balance, -8.0)

    def test_schedule_without_fixed_days(self):
        """Weekly hours without fixed days: compared per week, never per day."""
        flexible = self.env["resource.calendar"].create(
            {
                "name": "7.5 hours a week",
                "company_id": self.company.id,
                "calendar_type": "undefined",
                "hours_per_week": 7.5,
                "hours_per_day": 1.5,
                "days_per_week": 5,
                "full_time_required_hours": 40,
            }
        )
        employee = self._employee("Mini Job", resource_calendar_id=flexible.id)
        self.attend(1, 9, 13, employee)
        self.attend(3, 9, 14, employee)  # 9 hours in the first week
        self.attend(8, 9, 12, employee)  # 3 hours in the second week
        lines = self.update(employee)
        self.assertEqual(
            [
                (line.period, line.expected_hours, line.hours, line.state)
                for line in lines
            ],
            [("week", 7.5, 1.5, "booked"), ("week", 7.5, -4.5, "booked")],
        )
        # a week without any attendance is to clarify, not minus right away
        lines = self.update(employee, now="2026-10-26 10:00:00")
        self.assertEqual(
            (lines[2].deviation_hours, lines[2].hours, lines[2].state),
            (-7.5, 0.0, "to_clarify"),
        )
        lines[2].with_user(self.manager).action_confirm_minus()
        self.assertEqual((lines[2].hours, lines[2].state), (-7.5, "booked"))
        no_target = self.env["resource.calendar"].create(
            {
                "name": "Fully flexible",
                "company_id": self.company.id,
                "calendar_type": "undefined",
                "hours_per_week": 0,
                "hours_per_day": 0,
            }
        )
        # without any hours target nothing is expected: all worked time is plus
        employee.resource_calendar_id = no_target
        lines = self.update(employee, now="2026-10-26 10:00:00")
        self.assertEqual(
            [(line.expected_hours, line.hours, line.state) for line in lines],
            [(0.0, 9.0, "booked"), (0.0, 3.0, "booked"), (0.0, 0.0, "booked")],
        )

    def test_timezone(self):
        """An attendance belongs to the day it started on for the employee."""
        employee = self._employee("Berlin", tz="Europe/Berlin")
        # 23:30 UTC on Sunday is 01:30 on Monday in Berlin
        self.env["hr.attendance"].create(
            {
                "employee_id": employee.id,
                "check_in": datetime(2026, 10, 4, 23, 30),
                "check_out": datetime(2026, 10, 5, 9, 30),
            }
        )
        lines = self.update(employee)
        self.assertEqual((lines[0].date_from, lines[0].worked_hours), (day(0), 10.0))

    def test_contract_dates(self):
        """Days outside the contract have no account."""
        employee = self._employee(
            "Kurz Vertrag", contract_date_start=day(1), contract_date_end=day(3)
        )
        self.full_week(employee)
        lines = self.update(employee)
        self.assertEqual(lines.mapped("date_from"), [day(1), day(2), day(3)])
        self.assertIn("Deviation", lines[0].display_name)
        self.assertFalse(employee._time_account_compute(day(3), day(1)))
        self.assertFalse(employee._time_account_closed_differences())
        with freeze_time(TODAY):
            action = employee.action_open_time_account()
        self.assertEqual(action["domain"], [("employee_id", "=", employee.id)])
        self.assertIn(
            "time_account_period",
            self.env["hr.version"]._get_whitelist_fields_from_template(),
        )

    def test_change_of_settings(self):
        """Entries that no longer match a period are replaced."""
        self.full_week()
        self.assertEqual(len(self.update()), 14)
        self.employee.time_account_period = "week"
        lines = self.update()
        self.assertEqual(
            [(line.date_from, line.period) for line in lines],
            [(day(0), "week"), (day(7), "week")],
        )
        self.employee.time_account_period = "none"
        self.assertFalse(self.update())

    def test_time_rules_of_odoo(self):
        """With the time rules of Odoo all worked time still counts once."""
        self.env["hr.time.rule"].with_context(active_test=False).search(
            []
        ).active = True
        self.attend(0, 8, 19)
        lines = self.update()
        self.assertEqual(lines[0].worked_hours, 11.0)
        self.assertEqual(lines[0].hours, 3.0)

    # ------------------------------------------------------------------
    # entries by hand
    # ------------------------------------------------------------------

    def test_entries_by_hand(self):
        Line = self.Line.with_user(self.manager)
        with freeze_time(TODAY):
            opening = Line.create(
                {
                    "employee_id": self.employee.id,
                    "date": day(0),
                    "kind": "opening",
                    "hours": 12.5,
                    "name": "Balance of the previous system",
                }
            )
            self.assertEqual(opening.state, "booked")
            self.assertIn(
                "Balance of the previous system",
                self.employee.message_ids[0].body,
            )
            with self.assertRaises(UserError):
                Line.create({"employee_id": self.employee.id, "hours": 1})
            with self.assertRaises(UserError):
                Line.create(
                    {"employee_id": self.employee.id, "hours": 0, "name": "Nothing"}
                )
            with self.assertRaises(UserError):
                Line.create(
                    {
                        "employee_id": self.employee.id,
                        "kind": "deviation",
                        "hours": 1,
                        "name": "By hand",
                    }
                )
            with self.assertRaises(UserError):
                opening.hours = 10
            with self.assertRaises(UserError):
                opening.unlink()
            with self.assertRaises(UserError) as error:
                opening.sudo().unlink()
            self.assertIn("not deleted", str(error.exception))
            opening.name = "Balance of 2025"
            payout = Line.create(
                {
                    "employee_id": self.employee.id,
                    "date": day(1),
                    "kind": "payout",
                    "hours": -4,
                    "name": "Paid with the October salary",
                }
            )
            self.assertEqual(self.employee.time_account_balance, 8.5)
            reversal = payout.action_reverse()
            self.assertEqual((reversal.hours, reversal.origin_line_id), (4.0, payout))
            self.assertEqual(self.employee.time_account_balance, 12.5)
            with self.assertRaises(UserError):
                payout.action_reverse()

    def test_access(self):
        other = self._employee("Other Employee")
        self.attend(0, 8, 18)
        self.attend(0, 8, 19, other)
        self.update()
        self.update(other)
        own = self.Line.with_user(self.user).search([])
        self.assertEqual(own.employee_id, self.employee)
        with self.assertRaises(UserError):
            own[0].sudo().action_reverse()
        with self.assertRaises(AccessError):
            self.Line.with_user(self.user).create(
                {"employee_id": self.employee.id, "hours": 5, "name": "For me"}
            )
        self.assertEqual(
            self.Line.with_user(self.manager).search([]).employee_id,
            self.employee | other,
        )

    # ------------------------------------------------------------------
    # closing
    # ------------------------------------------------------------------

    def test_closing(self):
        self.full_week()
        self.attend(7, 8, 18)
        Close = self.env["l10n_de.time.account.close"].with_user(self.manager)
        with freeze_time(TODAY):
            wizard = Close.create({"date": day(6)})
            wizard.action_close()
            self.assertEqual(self.company.time_account_lock_date, day(6))
            with self.assertRaises(UserError):
                Close.create({"date": day(6)}).action_close()
            with self.assertRaises(UserError):
                Close.create({"date": day(20)}).action_close()
            # the second week has days without attendance
            with self.assertRaises(UserError):
                Close.create({"date": day(13)}).action_close()
            action = Close.create({"date": day(13)}).action_update()
            self.assertEqual(action["res_model"], "l10n_de.time.account.close")
        lines = self.update()
        monday = lines[0]
        self.assertTrue(monday.locked)
        with freeze_time(TODAY), self.assertRaises(UserError):
            self.Line.with_user(self.manager).create(
                {
                    "employee_id": self.employee.id,
                    "date": day(3),
                    "hours": 1,
                    "name": "Into the closed week",
                }
            )
        # an attendance of the closed week is corrected afterwards
        self.env["hr.attendance"].search(
            [("employee_id", "=", self.employee.id), ("date", "=", day(0))]
        ).check_out = datetime.combine(day(0), datetime.min.time()) + timedelta(
            hours=18
        )
        self.update()
        self.assertEqual(monday.hours, 0.0, "the closed entry stays")
        with freeze_time(TODAY):
            self.assertEqual(
                self.employee._time_account_closed_differences(), [(monday, 2.0)]
            )
            wizard = Close.create({"date": day(6)})
            action = wizard.action_correct_closed()
            correction = self.Line.search(action["domain"])
            self.assertEqual(
                (
                    correction.kind,
                    correction.hours,
                    correction.origin_line_id,
                    correction.date,
                ),
                ("adjustment", 2.0, monday, day(14)),
            )
            self.assertEqual(monday.correction_hours, 2.0)
            self.assertFalse(self.employee._time_account_closed_differences())
            self.assertFalse(self.Line.search(wizard.action_correct_closed()["domain"]))

    # ------------------------------------------------------------------
    # § 2 (2) MiLoG
    # ------------------------------------------------------------------

    def _book(self, date_, hours, kind="adjustment"):
        return self.Line.with_context(time_account_system=True).create(
            {
                "employee_id": self.employee.id,
                "date": date_,
                "date_from": date_,
                "kind": kind,
                "hours": hours,
                "state": "booked",
                "name": "Test",
            }
        )

    def test_oldest_plus_hours_are_used_first(self):
        self._book(date(2025, 10, 20), -3)  # minus hours first
        self._book(date(2025, 11, 5), 2)  # all of them settle the minus
        self._book(date(2025, 11, 10), 5)  # 1 of them settles the rest
        self._book(date(2025, 12, 5), 4)
        self._book(date(2026, 1, 15), -3)  # uses up 3 of November
        self._book(date(2026, 2, 1), 6)
        self.assertEqual(
            self.employee._time_account_plus_hours_by_month(),
            {date(2025, 11, 1): 1.0, date(2025, 12, 1): 4.0, date(2026, 2, 1): 6.0},
        )

    def test_milog_monitoring(self):
        self.employee.write(
            {
                "time_account_milog": True,
                "time_account_start": date(2025, 11, 1),
                "hr_responsible_id": self.manager.id,
            }
        )
        self._book(date(2025, 11, 10), 5)
        with freeze_time("2026-09-01 10:00:00"):
            self.employee._time_account_monitor()
        self.assertEqual(self.employee.time_account_due_date, date(2026, 11, 30))
        self.assertEqual(self.employee.time_account_due_hours, 5.0)
        self.assertFalse(self.employee.time_account_warning, "more than 60 days left")
        with freeze_time(TODAY):
            self.employee._time_account_monitor()
        self.assertIn("30", self.employee.time_account_warning)
        activity = self.employee.activity_ids
        self.assertEqual(activity.user_id, self.manager)
        with freeze_time(TODAY):
            self.employee._time_account_monitor()
        self.assertEqual(self.employee.activity_ids, activity, "notified once")
        # compensated: nothing is due any more
        self._book(day(0), -5, kind="payout")
        with freeze_time(TODAY):
            self.employee._time_account_monitor()
        self.assertFalse(self.employee.time_account_due_date)
        self.assertFalse(self.employee.time_account_warning)

    def test_leaving_with_a_balance(self):
        self._book(day(0), 2.5)
        self.env["hr.employee.departure"].create(
            {
                "employee_id": self.employee.id,
                "departure_reason_id": self.env["hr.departure.reason"]
                .search([], limit=1)
                .id,
                "dismissal_date": day(40),
            }
        )
        with freeze_time(TODAY):
            self.employee._time_account_monitor()
        self.assertIn("2.50", self.employee.time_account_warning)
        self.assertTrue(self.employee.activity_ids)

    def test_milog_half_of_the_agreed_time(self):
        part_time = self._calendar("8 hours", [0, 1], [(8, 12)])
        self.employee.write(
            {
                "time_account_milog": True,
                "resource_calendar_id": part_time.id,
                "time_account_period": "week",
                "time_account_start": date(2026, 9, 1),
            }
        )
        # September 2026: 9 scheduled days of 4 hours are 36 hours agreed
        for offset in (-28, -21, -14, -7):
            self.attend(offset, 8, 15)  # 7 instead of 4 hours on Monday
            self.attend(offset + 1, 8, 16)  # 8 instead of 4 hours on Tuesday
        with freeze_time(TODAY):
            self.employee._time_account_update()
            self.employee._time_account_monitor()
        # three of the four weeks with 7 plus hours each end in September
        self.assertIn("21.00", self.employee.time_account_warning)
        self.assertIn("36.00", self.employee.time_account_warning)

    # ------------------------------------------------------------------
    # take over from Odoo 19
    # ------------------------------------------------------------------

    def _legacy_rules(self, version):
        """The overtime ruleset the version had in Odoo 19."""
        self.env.cr.execute(
            "ALTER TABLE hr_version ADD COLUMN IF NOT EXISTS ruleset_id integer"
        )
        self.env.cr.execute(
            """
            CREATE TABLE IF NOT EXISTS hr_attendance_overtime_rule (
                id serial PRIMARY KEY, ruleset_id integer, sequence integer,
                base_off varchar, quantity_period varchar,
                employer_tolerance double precision,
                employee_tolerance double precision
            )
            """
        )
        self.env.cr.execute(
            """
            INSERT INTO hr_attendance_overtime_rule
                (ruleset_id, sequence, base_off, quantity_period,
                 employer_tolerance, employee_tolerance)
            VALUES
                (7, 10, 'timing', 'day', 0, 0),
                (7, 20, 'quantity', 'week', 0.5, 0.25)
            """
        )
        self.env.cr.execute(
            "UPDATE hr_version SET ruleset_id = 7 WHERE id = %s", (version.id,)
        )

    def _legacy(self):
        self.env.cr.execute(
            """
            CREATE TABLE IF NOT EXISTS hr_attendance_overtime_line (
                id serial PRIMARY KEY, employee_id integer, date date,
                duration double precision, manual_duration double precision,
                status varchar
            )
            """
        )
        self.env.cr.execute(
            """
            INSERT INTO hr_attendance_overtime_line
                (employee_id, date, duration, manual_duration, status)
            VALUES
                (%(id)s, '2025-12-31', 12.85, -12.85, 'approved'),
                (%(id)s, '2026-10-05', 1.5, 1.5, 'approved'),
                (%(id)s, '2026-10-06', -1, -1, 'approved'),
                (%(id)s, '2026-10-07', 0, 0, 'approved'),
                (%(id)s, '2026-10-08', 3, 3, 'to_approve'),
                (%(id)s, '2026-10-14', 2, 2, 'approved'),
                (%(other)s, '2026-10-05', 4, 4, 'approved')
            """,
            {"id": self.employee.id, "other": self.other.id},
        )

    def test_take_over_from_odoo_19(self):
        Import = self.env["l10n_de.time.account.import"].with_user(self.manager)
        with freeze_time(TODAY), self.assertRaises(UserError):
            Import.create({"date": day(6)}).action_import()
        # an employee without any attendance, and with an overtime ruleset
        self.other = self._employee("Regel Werk", time_account_period="none")
        self._legacy()
        self._legacy_rules(self.other.version_id)
        self.attend(0, 8, 17.5)  # what Odoo 19 booked with +1.5
        self.attend(1, 8, 15)  # -1
        self.attend(2, 8, 16)
        self.attend(3, 8, 19)  # +3, not approved in Odoo 19
        self.attend(4, 8, 16)
        self.full_week(offset=7)
        with freeze_time(TODAY):
            wizard = Import.create({})
            self.assertEqual(wizard.date, day(13), "the last Sunday")
            self.assertFalse(wizard.date_warning)
            wizard.date = day(8)
            self.assertTrue(wizard.date_warning)
            wizard.date = day(6)
            self.assertEqual(wizard.legacy_count, 4)
            wizard.with_settings = False
            wizard.action_import()
            self.assertEqual(self.other.time_account_period, "none")
            wizard.with_settings = True
            wizard.action_import()
            self.assertEqual(
                (
                    self.other.time_account_period,
                    self.other.time_account_tolerance_plus,
                    self.other.time_account_tolerance_minus,
                    self.other.time_account_negative,
                ),
                ("week", 0.5, 0.25, False),
            )
            taken = self.Line.search(
                [("employee_id", "=", self.employee.id), ("kind", "=", "transfer")]
            )
            self.assertEqual(sorted(taken.mapped("hours")), [-12.85, -1.0, 1.5])
            self.assertEqual(self.employee.time_account_start, day(7))
            wizard.action_import()
            self.assertEqual(
                self.Line.search_count(
                    [("employee_id", "=", self.employee.id), ("kind", "=", "transfer")]
                ),
                3,
                "taking over twice does not double",
            )
            wizard.action_compare()
            self.assertIn("Erika Muster", wizard.result)
            self.assertIn("+3.00", wizard.result, "Thursday differs")
            self.assertEqual(wizard.result.count("Erika Muster"), 1)
        lines = self.update()
        self.assertEqual(lines[0].date_from, day(7), "computed after the take over")
        self.assertEqual(self.employee.time_account_balance, -12.35)

    # ------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------

    def test_documents(self):
        self.attend(0, 8, 12)
        self.attend(0, 13, 18.5)
        self.absent(1, 1, self.vacation)
        self._book(day(-3), 7.25, kind="opening")
        self.update()
        Print = self.env["l10n_de.time.account.print"].with_user(self.manager)
        self.assertFalse(Print.create({}).employee_ids, "the manager is no employee")
        self.assertEqual(
            Print.with_context(active_model="hr.employee", active_ids=self.employee.ids)
            .create({})
            .employee_ids,
            self.employee,
        )
        with freeze_time(TODAY):
            wizard = Print.create(
                {
                    "employee_ids": [(6, 0, self.employee.ids)],
                    "date_from": day(0),
                    "date_to": day(6),
                }
            )
            action = wizard.action_print()
            self.assertEqual(action["data"]["employee_ids"], self.employee.ids)
            Report = self.env["ir.actions.report"].with_user(self.manager)
            statement = Report._render_qweb_html(
                "l10n_de_hr_attendance_time_account.report_statement",
                self.employee.ids,
                data=action["data"],
            )[0].decode()
            self.assertIn("Erika Muster", statement)
            self.assertIn("+7:15", statement, "balance carried forward")
            self.assertIn("+1:30", statement, "plus hours of Monday")
            self.assertIn("+8:45", statement, "balance after Monday")
            wizard.document = "timesheet"
            action = wizard.action_print()
            timesheet = Report._render_qweb_html(
                "l10n_de_hr_attendance_time_account.report_timesheet",
                self.employee.ids,
                data=action["data"],
            )[0].decode()
            for text in ("08:00", "12:00", "13:00", "18:30", "Vacation", "9:30"):
                self.assertIn(text, timesheet)
            wizard.date_to = day(-1)
            with self.assertRaises(UserError):
                wizard.action_print()

    def test_cron(self):
        self.attend(0, 8, 18)
        with freeze_time(TODAY):
            self.env["hr.employee"]._cron_time_account()
        self.assertTrue(
            self.Line.search(
                [("employee_id", "=", self.employee.id), ("hours", "=", 2.0)]
            )
        )
