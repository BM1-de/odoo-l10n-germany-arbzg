- The module does not know wages. It cannot check the earnings limit of
  marginal employment, nor whether the steady pay already covers the minimum
  wage (the exception of § 2 (2) MiLoG).
- Schedules without fixed days: Odoo spreads the weekly hours over the first
  days of the period asked for. A public holiday therefore lowers the expected
  hours of the week only if it falls on one of these days.
- An attendance belongs to the day it started on. Work over midnight is not
  split.
- Limits for the balance (traffic light) and automatic forfeiture are not
  built in yet; forfeitures are booked by hand.
- Employees see their entries, but only attendance officers print statements.
- The account is computed once a night, not at the moment an attendance
  changes.
- Not covered: surcharges, payroll export, long-term accounts (§ 7b SGB IV),
  collective agreements with their own rules.
