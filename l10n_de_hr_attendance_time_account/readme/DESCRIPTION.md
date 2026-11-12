A signed working time account (*Arbeitszeitkonto*) for the attendances of Odoo:
for every day, week or month it compares the worked hours to the hours of the
working schedule and books the difference as plus or minus hours. The balance
of an employee is the sum of all entries and can be negative.

Odoo 19 kept such a balance as overtime. Odoo 20 replaced it by time rules that
split attendances and add lines for missing time, without a balance that can
go below zero. This module brings the account back and keeps the attendances
untouched: it only reads them. Begin, end and duration of the working time stay
exactly as recorded, which is what German law asks employers to record (BAG,
13 September 2022, 1 ABR 22/21; § 17 MiLoG for marginal employment).

- **Computation:** worked hours come from the validated attendances, expected
  hours from the working schedule of the contract version valid on each day.
  Public holidays and time off that counts as worked (vacation, sickness)
  lower the expected hours, so they leave the account as it is.
- **Tolerance:** differences within a tolerance are booked with zero, beyond
  it the whole difference is booked.
- **Minus hours** are only booked when the contract version says so, as they
  need an agreement. A period can be set to zero with a reason, for example
  when the employer had no work for the employee.
- **Days without attendance** and without time off are not booked as minus
  right away. They wait as *to clarify* until the time off is entered or the
  minus hours are confirmed.
- **Compensation by time off:** time off of a type marked as *deducted from the
  working time account* keeps the expected hours, so the day is booked as
  minus.
- **Entries by hand:** opening balance, correction, payout and forfeiture, each
  with a reason. Entries are never deleted, they are reversed.
- **Closing:** closed months are not computed again. Later changes of
  attendances are booked as a correction in an open period.
- **§ 2 (2) MiLoG:** for accounts under the German Minimum Wage Act the module
  warns when plus hours get twelve months old and when a month adds more than
  half of the agreed monthly working time.
- **Documents:** an account statement and a record of working time (begin, end
  and duration per day) per employee as PDF, for the payroll records.
- **Coming from Odoo 19:** the overtime balance of Odoo 19 is taken over as it
  was, entry by entry.

The module is no payroll, no long-term account (*Wertguthaben*, § 7b SGB IV)
and no legal advice. It is provided without warranty; whether an account with
minus hours is allowed depends on the agreements of the employer.
