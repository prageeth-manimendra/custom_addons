# -*- coding: utf-8 -*-
from odoo import models, fields, api

class TelegramMember(models.Model):
    _name = 'telegram.member'
    _description = 'Telegram Group Member'
    _order = 'name'

    name = fields.Char('Name', required=True)
    telegram_id = fields.Char('Telegram User ID', required=True, index=True)
    username = fields.Char('Username')
    group_id = fields.Many2one('telegram.group', string='Group', required=True, ondelete='cascade', index=True)
    is_bot = fields.Boolean('Is Bot', default=False)
    is_team_member = fields.Boolean('Is Team Member', compute='_compute_is_team_member', store=False)
    join_date = fields.Datetime('Joined Date', default=fields.Datetime.now)
    left_date = fields.Datetime('Left Date')
    is_active = fields.Boolean('Active in Group', default=True)
    phone = fields.Char('Phone Number')
    email = fields.Char('Email')
    notes = fields.Text('Notes')
    
    def _compute_is_team_member(self):
        """Check if this member is registered as a Nerosoft team member globally"""
        # Get all active team member telegram IDs
        team_telegram_ids = self.env['telegram.team.member'].search([
            ('is_active', '=', True)
        ]).mapped('telegram_id')
        
        # Check each member
        for member in self:
            member.is_team_member = member.telegram_id in team_telegram_ids
    
    _sql_constraints = [
        ('telegram_id_group_unique', 'unique(telegram_id, group_id)', 'This user is already in this group!')
    ]
    
    def name_get(self):
        result = []
        for member in self:
            name = member.name
            if member.username:
                name = f"{name} (@{member.username})"
            result.append((member.id, name))
        return result