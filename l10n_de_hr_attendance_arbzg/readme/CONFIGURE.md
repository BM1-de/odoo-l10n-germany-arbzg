*Attendances → Configuration → Settings*, block *Working Time Act (Germany)*:

- switch the check on or off for the company;
- the breaks: after how many hours, how many minutes, and the shortest gap
  that counts as a break;
- whether a missing break is inserted or only pointed out;
- the maximum working time per day, the automatic check-out and who gets an
  activity when the maximum is exceeded (empty: the attendance approver of the
  employee).

On the employee, next to the attendance approver: *Exempt from the Working
Time Act*, for example for managing directors and executives (§ 18 ArbZG).

On the employee type (*Employees → Configuration → Employee Types*): *Exempt
from the Working Time Act*, for types that are no employees in the sense of
the act, for example contractors and freelancers. Odoo 20 has no fixed types
for them any more, so no type is exempt until it is marked.

When a database is upgraded from Odoo 19, the module marks the employee types
that the former contractors and freelancers got. If one of them got a type
that other employees share, that employee is marked as exempt instead.
