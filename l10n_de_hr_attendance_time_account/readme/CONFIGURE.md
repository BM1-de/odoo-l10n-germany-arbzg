*Attendances → Configuration → Settings*, block *Working Time Account
(Germany)*: the defaults for new contract versions (period, tolerances, minus
hours).

On the employee, in the work information next to the working schedule (the
values belong to the contract version, so they can change over time):

- *Working Time Account*: per day, per week (Monday to Sunday) or per month.
  A schedule without fixed days is compared per week at least.
- *Tolerance for Plus Hours* and *Tolerance for Minus Hours*.
- *Book Minus Hours*: only with an agreement with the employee.
- *Monitor § 2 (2) MiLoG*: for accounts under the Minimum Wage Act. It does
  not apply when the steady monthly pay already covers the minimum wage for
  all hours; the module cannot tell, as it does not know wages.
- *Working Time Account Since*: nothing is computed before this date. Left
  empty, the account starts the day it is computed for the first time.

On the types of time off (*Time Off → Configuration → Time Off Types*):
*Deducted from the Working Time Account* for time off that compensates plus
hours. Leave it off for vacation, sickness and everything else that counts as
worked.

An opening balance is booked under *Attendances → Working Time Account → Book
by Hand*.

Coming from Odoo 19: *Attendances → Configuration → Take Over from Odoo 19*
takes over the overtime entries up to a date and, if wanted, the period and
tolerances of the overtime rulesets. Take the end of a period as the date: a
Sunday for weekly accounts, the last day of a month for monthly ones. *Compare
with the Computation* lists the periods the module would compute differently,
without storing anything.
