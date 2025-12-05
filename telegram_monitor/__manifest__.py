# -*- coding: utf-8 -*-
{
    'name': 'Telegram Monitor',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Monitor Odoo instance via Telegram bot',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/telegram_config_views.xml',
        'views/telegram_group_views.xml',
    ],
    'installable': True,
    'application': True,
}