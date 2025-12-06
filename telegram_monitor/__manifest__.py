# -*- coding: utf-8 -*-
{
    'name': 'Telegram Group Monitor',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Monitor Telegram groups and track team response times',
    'description': """
        Telegram Group Monitor
        ======================
        Monitor Telegram groups and track team member response times for SLA compliance.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/telegram_cron.xml',
        'views/telegram_config_views.xml',
        'views/telegram_team_member_views.xml',
        'views/telegram_group_views.xml',
        'views/telegram_security_audit_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}