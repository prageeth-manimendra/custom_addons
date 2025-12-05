# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class TelegramConfig(models.Model):
    _name = 'telegram.config'
    _description = 'Telegram Bot Configuration'

    name = fields.Char('Bot Name', required=True)
    bot_token = fields.Char('Bot Token', required=True)
    chat_id = fields.Char('Chat ID', required=True)
    is_active = fields.Boolean('Active', default=True)
    
    @api.model
    def send_message(self, message):
        """Send message via Telegram"""
        _logger.info(f"Sending Telegram message: {message}")
        return True
