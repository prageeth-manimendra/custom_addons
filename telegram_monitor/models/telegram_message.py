# -*- coding: utf-8 -*-
from odoo import models, fields, api

class TelegramMessage(models.Model):
    _name = 'telegram.message'
    _description = 'Telegram Message'
    _order = 'message_date desc'

    group_id = fields.Many2one('telegram.group', string='Group', required=True, ondelete='cascade', index=True)
    member_id = fields.Many2one('telegram.member', string='Sender', ondelete='set null', index=True)
    message_text = fields.Text('Message', required=True)
    message_id = fields.Char('Telegram Message ID', required=True, index=True)
    message_date = fields.Datetime('Date', default=fields.Datetime.now, required=True, index=True)
    is_reply = fields.Boolean('Is Reply', default=False)
    is_from_team = fields.Boolean('From Team Member', compute='_compute_is_from_team', store=True)
    needs_response = fields.Boolean('Needs Response', default=False)
    ai_classification = fields.Selection([
        ('urgent', 'Urgent - Needs Immediate Response'),
        ('normal', 'Normal - Needs Response'),
        ('info', 'Informational - No Response Needed'),
        ('thanks', 'Acknowledgment/Thanks')
    ], string='AI Classification')
    response_time = fields.Integer('Response Time (minutes)')
    responded = fields.Boolean('Responded', default=False)
    responded_by_id = fields.Many2one('telegram.member', string='Responded By')
    responded_at = fields.Datetime('Responded At')
    
    @api.depends('member_id', 'member_id.is_team_member')
    def _compute_is_from_team(self):
        for message in self:
            message.is_from_team = message.member_id.is_team_member if message.member_id else False
    
    _sql_constraints = [
        ('message_id_unique', 'unique(message_id, group_id)', 'This message is already recorded!')
    ]