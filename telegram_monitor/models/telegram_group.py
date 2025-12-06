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
        ('internal', 'Internal Team Chat'),
        ('client', 'Client Support Group'),
        ('other', 'Other')
    ], string='Group Type', default='other', required=True)
    is_monitored = fields.Boolean('Monitor This Group', default=True, 
                                   help='Track messages and calculate response times for this group')
    invite_link = fields.Char('Invite Link', readonly=True, help='Telegram invite link for this group')
    invite_link_created_at = fields.Datetime('Invite Link Created', readonly=True)
    description = fields.Text('Description')
    member_ids = fields.One2many('telegram.member', 'group_id', string='Members')
    message_ids = fields.One2many('telegram.message', 'group_id', string='Messages')
    member_count = fields.Integer('Member Count', compute='_compute_member_count', store=True)
    message_count = fields.Integer('Message Count', compute='_compute_message_count', store=True)
    team_member_count = fields.Integer('Team Members', compute='_compute_team_member_count', store=True)
    
    @api.depends('member_ids')
    def _compute_member_count(self):
        for group in self:
            group.member_count = len(group.member_ids.filtered('is_active'))
    
    @api.depends('message_ids')
    def _compute_message_count(self):
        for group in self:
            group.message_count = len(group.message_ids)
    
    @api.depends('member_ids', 'member_ids.is_team_member')
    def _compute_team_member_count(self):
        for group in self:
            group.team_member_count = len(group.member_ids.filtered(lambda m: m.is_team_member and m.is_active))
    
    def action_copy_invite_link(self):
        """Copy invite link to clipboard"""
        self.ensure_one()
        if not self.invite_link:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Invite Link',
                    'message': 'This group does not have an invite link yet. Make sure the bot is an admin in the group.',
                    'type': 'warning',
                }
            }
        
        # Return success with link to copy
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Invite Link',
                'message': f'Link: {self.invite_link}\n\nCopy this link to share with new members!',
                'type': 'info',
                'sticky': True,
            }
        }
    
    def action_regenerate_invite_link(self):
        """Regenerate invite link for this group"""
        self.ensure_one()
        config = self.config_id
        if not config:
            raise UserError('Configuration not found')
        
        new_link = config._generate_invite_link(self.chat_id)
        if new_link:
            self.write({
                'invite_link': new_link,
                'invite_link_created_at': fields.Datetime.now()
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Invite Link Regenerated',
                    'message': f'New link: {new_link}',
                    'type': 'success',
                    'sticky': True,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Failed',
                    'message': 'Could not generate invite link. Make sure bot is an admin in the group.',
                    'type': 'danger',
                }
            }
    
    _sql_constraints = [
        ('chat_id_config_unique', 'unique(chat_id, config_id)', 'This Telegram group is already registered for this configuration!')
    ]