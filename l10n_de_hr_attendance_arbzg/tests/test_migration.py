# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The upgrade from Odoo 19: employee types that are exempt."""

import importlib.util
from pathlib import Path

from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL

LEGACY = "openupgrade_legacy_20_0_employee_type"


def _load_migration():
    path = Path(__file__).parents[1] / "migrations/20.0.1.0.0/post-migration.py"
    spec = importlib.util.spec_from_file_location("arbzg_migration_20", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("post_install", "-at_install")
class TestMigration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migration = _load_migration()
        types = cls.env["hr.employee.type"]
        cls.freelancer = types.create({"name": "Freelancer (test)"})
        cls.contractor = types.create({"name": "Contractor (test)"})
        cls.permanent = types.create({"name": "Permanent (test)"})
        cls.employees = cls.env["hr.employee"]
        for name, employee_type in (
            ("Frieda Frei", cls.freelancer),
            ("Konrad Werk", cls.contractor),
            ("Paula Fest", cls.permanent),
            # a freelancer who kept the contract type of Odoo 19
            ("Felix Vertrag", cls.permanent),
        ):
            cls.employees |= cls.env["hr.employee"].create(
                {
                    "name": name,
                    "employee_type_id": employee_type.id,
                    "date_version": "2026-01-01",
                }
            )

    def upgrade(self, *old_types):
        """Run the migration on the employee types of Odoo 19 ``old_types``."""
        self.env.flush_all()
        legacy = SQL.identifier(LEGACY)
        self.env.cr.execute(SQL("ALTER TABLE hr_version ADD COLUMN %s varchar", legacy))
        for employee, old_type in zip(self.employees, old_types, strict=True):
            self.env.cr.execute(
                SQL(
                    "UPDATE hr_version SET %s = %s WHERE id = %s",
                    legacy,
                    old_type,
                    employee.current_version_id.id,
                )
            )
        self.migration.migrate(self.env.cr, "19.0.1.0.1")
        self.env.invalidate_all()

    def test_exempt_types_and_employees(self):
        self.upgrade("freelance", "contractor", "employee", "freelance")
        self.assertEqual(
            (
                self.freelancer.arbzg_exempt,
                self.contractor.arbzg_exempt,
                self.permanent.arbzg_exempt,
            ),
            (True, True, False),
        )
        # the employees of an exempt type need no mark of their own; the
        # freelancer with the shared type gets it, the others keep the check
        self.assertEqual(self.employees.mapped("arbzg_exempt"), [False] * 3 + [True])
        self.assertEqual(
            [employee._arbzg_applies() for employee in self.employees],
            [False, False, True, False],
        )

    def test_without_the_employee_types_of_odoo_19(self):
        with self.assertLogs("arbzg_migration_20", "WARNING"):
            self.migration.migrate(self.env.cr, "19.0.1.0.1")
        self.assertFalse(self.freelancer.arbzg_exempt)
        self.assertFalse(any(self.employees.mapped("arbzg_exempt")))
