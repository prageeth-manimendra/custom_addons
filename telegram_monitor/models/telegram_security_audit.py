# -*- coding: utf-8 -*-
from odoo import models, fields, api

class TelegramSecurityAudit(models.Model):
    _name = 'telegram.security.audit'
    _description = 'Telegram Security Audit Log'
    _order = 'create_date desc'

    name = fields.Char('User Name', required=True)
    telegram_id = fields.Char('Telegram ID', required=True, index=True)
    telegram_username = fields.Char('Telegram Username')
    group_name = fields.Char('Group Name', required=True)
    group_chat_id = fields.Char('Group Chat ID')
    config_id = fields.Many2one('telegram.config', string='Bot Configuration', required=True, ondelete='cascade')
    attempt_date = fields.Datetime('Attempt Date', default=fields.Datetime.now, required=True)
    attempt_type = fields.Selection([
        ('unauthorized_add', 'Unauthorized Bot Addition'),
        ('unauthorized_invite', 'Unauthorized Invite Attempt'),
    ], string='Attempt Type', default='unauthorized_add', required=True)
    notes = fields.Text('Notes')
    
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} ({record.telegram_id}) - {record.group_name}"
            result.append((record.id, name))
        return result