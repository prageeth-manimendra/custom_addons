# -*- coding: utf-8 -*-
from odoo import models, fields, api

class TelegramMessage(models.Model):
    _name = 'telegram.message'
    _description = 'Telegram Message'
    _order = 'message_date desc'

    message_id = fields.Char('Message ID', required=True, index=True)
    group_id = fields.Many2one('telegram.group', string='Group', required=True, ondelete='cascade', index=True)
    member_id = fields.Many2one('telegram.member', string='From', required=True, ondelete='cascade')
    message_text = fields.Text('Message')
    message_date = fields.Datetime('Date', required=True, index=True)
    is_from_team = fields.Boolean('From Team', compute='_compute_is_from_team', store=True)
    is_reply = fields.Boolean('Is Reply', default=False)
    reply_to_message_id = fields.Char('Reply To Message ID')
    
    @api.depends('member_id', 'member_id.is_team_member')
    def _compute_is_from_team(self):
        """Determine if message is from a team member"""
        for message in self:
            message.is_from_team = message.member_id.is_team_member if message.member_id else False
    
    _sql_constraints = [
        ('message_id_group_unique', 'unique(message_id, group_id)', 'This message already exists!')
    ]