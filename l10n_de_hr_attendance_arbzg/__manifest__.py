# Copyright 2026 Baumgärtner Marketing GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Germany Working Time Act",
    "summary": "Legal breaks and the daily maximum of the German Working Time Act "
    "(ArbZG) for attendances",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Attendances",
    "website": "https://github.com/BM1-de/odoo-l10n-germany-arbzg",
    "author": "Baumgärtner Marketing GmbH",
    "maintainers": ["bm1-phillip"],
    "license": "AGPL-3",
    "development_status": "Alpha",
    "depends": ["hr_attendance"],
    "data": [
        "data/mail_activity_type_data.xml",
        "data/ir_cron_data.xml",
        "views/res_config_settings_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_attendance_views.xml",
    ],
    "images": ["static/description/banner.png"],
    "installable": True,
}
