# -*- coding: utf-8 -*-
{
    'name': 'Telegram Group Monitor',
    'version': '1.0',
    'category': 'Productivity',
    'summary': 'Monitor Telegram group messages and track team response times',
    'description': """
        Telegram Group Monitor
        ======================
        Monitor messages from Telegram groups and track:
        - Client messages
        - Team member responses
        - Response times
        - Message history
        
        Features:
        - Automatic message polling every 30 seconds
        - Group and member management
        - Message tracking and analytics
        - Team response time monitoring
    """,
    'author': 'Nero Soft Solutions',
    'website': 'https://nerosoftsolutions.com',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/telegram_cron.xml',
        'views/telegram_config_views.xml',
        'views/telegram_group_views.xml',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}