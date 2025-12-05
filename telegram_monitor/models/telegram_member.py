# -*- coding: utf-8 -*-
from odoo import models, fields, api

class TelegramMember(models.Model):
    _name = 'telegram.member'
    _description = 'Telegram Group Member'
    _order = 'name'

    name = fields.Char('Name', required=True)
    user_id = fields.Char('Telegram User ID', required=True, index=True)
    username = fields.Char('Username')
    group_id = fields.Many2one('telegram.group', string='Group', required=True, ondelete='cascade', index=True)
    is_team_member = fields.Boolean('Nerosoft Team Member', default=False)
    join_date = fields.Datetime('Joined Date', default=fields.Datetime.now)
    left_date = fields.Datetime('Left Date')
    is_active = fields.Boolean('Active in Group', default=True)
    phone = fields.Char('Phone Number')
    email = fields.Char('Email')
    notes = fields.Text('Notes')
    
    _sql_constraints = [
        ('user_group_unique', 'unique(user_id, group_id)', 'This user is already in this group!')
    ]
    
    def name_get(self):
        result = []
        for member in self:
            name = member.name
            if member.username:
                name = f"{name} (@{member.username})"
            result.append((member.id, name))
        return result