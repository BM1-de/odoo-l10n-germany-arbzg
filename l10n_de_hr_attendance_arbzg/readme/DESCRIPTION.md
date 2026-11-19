Checks the attendances of Odoo against the German Working Time Act
(*Arbeitszeitgesetz*, ArbZG); employers have to record the working time of
their employees (BAG, 13 September 2022, 1 ABR 22/21).

- **Breaks (§ 4 ArbZG):** more than 6 hours of work a day need a break of 30
  minutes, more than 9 hours 45 minutes. Gaps of at least 15 minutes between
  two attendances count as breaks, and so does the break duration recorded on
  an attendance, which Odoo deducts. Only the time above a limit needs a
  break: 6:10 hours of work need 10 minutes.
- **Missing break:** it is put into the middle of the longest attendance of the
  day and noted there, or only pointed out to the employee.
- **Maximum (§ 3 ArbZG):** more than 10 hours of work a day are reported to the
  employee and to a responsible person, once per day. The attendances are not
  shortened, as they must show the real time (§ 16 (2) ArbZG).
- **Forgotten check-out:** open attendances are checked out as soon as the
  maximum of the day is reached.
- **Time rules of Odoo:** the legal break is inserted before the time rules
  evaluate the day, so the time above the schedule is counted without the
  break. Refused attendances and the lines Odoo adds for missing time are no
  work.

All limits can be set per company, in case the law changes. Employees marked
as exempt (for example managing directors) and employees of an employee type
marked as exempt (for example contractors and freelancers) are not checked.
