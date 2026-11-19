Employees check in and out as usual, and should record their breaks the same
way; the rule is only a safety net. Every time an attendance is created or
corrected, the whole day is checked again:

- A missing break appears as a gap in the middle of the longest attendance of
  the day, with a note on the attendance. Whoever records a real break later
  gets only the rest added; whoever removes an inserted break gets it back.
  The part after the break keeps the time type and the status of the
  attendance.
- With *Only point out the missing break*, the column *Missing Break
  (Minutes)* of the attendance list shows the minutes, and the employee gets a
  message.
- More than the maximum working time: the employee gets a message on the
  attendance and the responsible person an activity *Working Time Exceeded* on
  the employee.
- Every 15 minutes, a scheduled action checks out open attendances that
  reached the maximum of the day (*Automatic Check-Out*); the employee
  corrects the actual time if needed.

With the time rules of Odoo (*Attendances → Configuration → Automatic
Rules*), an attendance of 8:00 to 18:00 on a schedule of 8 hours becomes 8:00
to 12:37, 13:22 to 16:45 and 1:15 hours above the schedule from 16:45 to
18:00: the break first, then the time rule.
