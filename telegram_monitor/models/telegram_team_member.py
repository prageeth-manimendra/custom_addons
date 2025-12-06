# -*- coding: utf-8 -*-
from odoo import models, fields

class TelegramTeamMember(models.Model):
    _name = 'telegram.team.member'
    _description = 'Nerosoft Team Members Registry'
    _order = 'name'

    name = fields.Char('Name', required=True)
    telegram_id = fields.Char('Telegram User ID', required=True, index=True)
    username = fields.Char('Username')
    is_active = fields.Boolean('Active', default=True, help='Inactive members are no longer in the team source group')
    role = fields.Char('Role/Position')
    notes = fields.Text('Notes')
    
    _sql_constraints = [
        ('telegram_id_unique', 'unique(telegram_id)', 'This Telegram user is already registered as a team member!')
    ]
    
    def name_get(self):
        result = []
        for member in self:
            name = member.name
            if member.username:
                name = f"{name} (@{member.username})"
            result.append((member.id, name))
        return result