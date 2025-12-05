# -*- coding: utf-8 -*-
from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)

class TelegramConfig(models.Model):
    _name = 'telegram.config'
    _description = 'Telegram Bot Configuration'

    name = fields.Char('Bot Name', required=True)
    bot_token = fields.Char('Bot Token', required=True)
    chat_id = fields.Char('Chat ID', required=True)
    is_active = fields.Boolean('Active', default=True)
    
    def send_message(self, message):
        """Send message via Telegram"""
        self.ensure_one()
        if not self.is_active:
            _logger.warning("Telegram bot is not active")
            return False
            
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            _logger.info(f"Telegram message sent successfully: {message[:50]}...")
            return True
        except Exception as e:
            _logger.error(f"Failed to send Telegram message: {str(e)}")
            return False
    
    def action_test_message(self):
        """Send a test message"""
        self.ensure_one()
        message = f"🤖 <b>Test Message from Odoo</b>\n\nYour Nero Bot is configured correctly!"
        result = self.send_message(message)
        if result:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Test message sent successfully! Check your Telegram.',
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Failed to send message. Check the logs.',
                    'type': 'danger',
                    'sticky': False,
                }
            }