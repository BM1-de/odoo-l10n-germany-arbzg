# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Germany Working Time Account",
    "summary": "Signed working time account (plus and minus hours) from attendances, "
    "with statements for German payroll records",
    "version": "20.0.1.0.0",
    "category": "Human Resources/Attendances",
    "website": "https://github.com/BM1-de/odoo-l10n-germany-arbzg",
    "author": "Baumgärtner Marketing GmbH",
    "maintainers": ["bm1-phillip"],
    "license": "AGPL-3",
    "development_status": "Alpha",
    "depends": ["hr_attendance", "hr_holidays"],
    "data": [
        "security/ir.access.csv",
        "data/mail_activity_type_data.xml",
        "data/ir_cron_data.xml",
        "report/time_account_reports.xml",
        "wizard/time_account_print_views.xml",
        "wizard/time_account_close_views.xml",
        "wizard/time_account_import_views.xml",
        "views/time_account_line_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_work_entry_type_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
