# -*- coding: utf-8 -*-
from odoo import models, fields, api

class TelegramGroup(models.Model):
    _name = 'telegram.group'
    _description = 'Telegram Group'
    _order = 'name'

    name = fields.Char('Group Name', required=True)
    chat_id = fields.Char('Chat ID', required=True, index=True)
    chat_type = fields.Char('Chat Type', help='Type of chat: group or supergroup')
    config_id = fields.Many2one('telegram.config', string='Configuration', required=True, ondelete='cascade')
    group_type = fields.Selection([
        ('team', 'Nerosoft Team'),
        ('client', 'Client Group'),
        ('other', 'Other')
    ], string='Group Type', default='other', required=True)
    is_monitored = fields.Boolean('Monitor This Group', default=True)
    description = fields.Text('Description')
    member_ids = fields.One2many('telegram.member', 'group_id', string='Members')
    message_ids = fields.One2many('telegram.message', 'group_id', string='Messages')
    member_count = fields.Integer('Member Count', compute='_compute_member_count', store=True)
    message_count = fields.Integer('Message Count', compute='_compute_message_count', store=True)
    
    @api.depends('member_ids')
    def _compute_member_count(self):
        for group in self:
            group.member_count = len(group.member_ids)
    
    @api.depends('message_ids')
    def _compute_message_count(self):
        for group in self:
            group.message_count = len(group.message_ids)
    
    _sql_constraints = [
        ('chat_id_config_unique', 'unique(chat_id, config_id)', 'This Telegram group is already registered for this configuration!')
    ]