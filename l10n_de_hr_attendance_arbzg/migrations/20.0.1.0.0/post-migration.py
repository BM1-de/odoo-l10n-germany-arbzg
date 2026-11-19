# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Exempt employee types after the upgrade from Odoo 19.

Odoo 19 had a fixed selection of employee types on the employee record
(``hr.version.employee_type``); the module did not check contractors and
freelancers. Odoo 20 replaces the selection by the records of
``hr.employee.type``, and the upgrade gives every employee record a type.

The types that only these employees got are marked as exempt from the Working
Time Act. If such an employee got a type that others share (for example the
contract type of Odoo 19), the employee is marked as exempt instead, so that
nobody else loses the check.
"""

import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)

#: values of the selection of Odoo 19 that were exempt
EXEMPT = ("contractor", "freelance")
#: the column of the selection after the upgrade: OpenUpgrade keeps it under a
#: legacy name, an upgrade without it leaves the column of the removed field
COLUMNS = ("openupgrade_legacy_20_0_employee_type", "employee_type")


def migrate(cr, version):
    column = next(
        (name for name in COLUMNS if column_exists(cr, "hr_version", name)), None
    )
    if not column:
        _logger.warning(
            "The employee types of Odoo 19 are not available any more: mark the "
            "employee types of contractors and freelancers as exempt from the "
            "Working Time Act by hand."
        )
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        SQL(
            """
            SELECT employee_type_id
              FROM hr_version
             WHERE employee_type_id IS NOT NULL
             GROUP BY employee_type_id
            HAVING bool_and(COALESCE(%(old)s IN %(exempt)s, FALSE))
            """,
            old=SQL.identifier(column),
            exempt=EXEMPT,
        )
    )
    types = env["hr.employee.type"].browse([row[0] for row in cr.fetchall()])
    types.write({"arbzg_exempt": True})
    cr.execute(
        SQL(
            """
            SELECT employee.id
              FROM hr_employee employee
              JOIN hr_version version ON version.id = employee.current_version_id
             WHERE %(old)s IN %(exempt)s
               AND NOT COALESCE(version.employee_type_id = ANY(%(types)s), FALSE)
            """,
            old=SQL.identifier("version", column),
            exempt=EXEMPT,
            types=types.ids,
        )
    )
    employees = env["hr.employee"].browse([row[0] for row in cr.fetchall()])
    employees.write({"arbzg_exempt": True})
    _logger.info(
        "Exempt from the Working Time Act after the upgrade: employee types %s, "
        "employees %s",
        types.mapped("name"),
        employees.mapped("name"),
    )
