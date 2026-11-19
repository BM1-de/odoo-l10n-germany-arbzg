## 20.0.1.0.0

- Migration to Odoo 20.
- The legal break is inserted before the time rules of Odoo evaluate the day,
  and the check never starts them in between: the time above the schedule is
  counted with the break, without further lines.
- Odoo 20 no longer deducts the lunch break of the working schedule; the break
  duration recorded on an attendance counts as a break instead.
- Refused attendances, attendances of a time type that counts as absence and
  the lines of the time rules for missing time are no work. The part split off
  by a break keeps the time type and the status of the attendance.
- The selection of employee types of Odoo 19 (contractor, freelancer) is gone:
  an employee type can be marked as exempt from the Working Time Act. The
  upgrade from Odoo 19 marks the types of the former contractors and
  freelancers, or the employee if the type is shared with others.
- Contains the correction of 19.0.1.0.1.

## 19.0.1.0.1

- A technical entry of the absence management whose end is corrected becomes
  a manual entry on both sides again. Since 18.11.2026 Odoo 19 sets only the
  check-out to manual in that case; the technical check-in made the gap before
  the entry count as a break, even if it was shorter than the shortest break.
  The part split off by an inserted break keeps its technical check-in.

## 19.0.1.0.0

- First version for Odoo 19, built on the rules that Baumgärtner Marketing
  GmbH has used for its own attendances since September 2026.
