# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class TelegramConfig(models.Model):
    _name = 'telegram.config'
    _description = 'Telegram Bot Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    bot_token = fields.Char(string='Bot Token', required=True, help='Your Telegram Bot Token from @BotFather')
    active = fields.Boolean(string='Active', default=True)
    last_update_id = fields.Integer(string='Last Update ID', default=0, help='Used for polling to avoid duplicate messages')
    
    # Statistics
    total_messages = fields.Integer(string='Total Messages', compute='_compute_statistics')
    total_groups = fields.Integer(string='Total Groups', compute='_compute_statistics')
    
    @api.depends('active')
    def _compute_statistics(self):
        for config in self:
            config.total_groups = self.env['telegram.group'].search_count([('config_id', '=', config.id)])
            config.total_messages = self.env['telegram.message'].search_count([('group_id.config_id', '=', config.id)])
    
    def test_connection(self):
        """Test the bot connection"""
        self.ensure_one()
        url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok'):
                bot_info = data.get('result', {})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Bot connected successfully! Bot name: %s (@%s)') % (
                            bot_info.get('first_name', 'Unknown'),
                            bot_info.get('username', 'unknown')
                        ),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Bot connection failed: %s') % data.get('description', 'Unknown error'))
                
        except requests.exceptions.RequestException as e:
            raise UserError(_('Connection error: %s') % str(e))
    
    def send_telegram_message(self, chat_id, message):
        """Send a message to Telegram"""
        self.ensure_one()
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error sending Telegram message: {str(e)}")
            raise UserError(_("Failed to send Telegram message: %s") % str(e))
    
    @api.model
    def poll_telegram_messages(self):
        """Poll for new messages from Telegram (called by scheduled action)"""
        configs = self.search([('active', '=', True)])
        _logger.info(f"Polling Telegram messages for {len(configs)} active configuration(s)")
        for config in configs:
            config._fetch_updates()
    
    def _fetch_updates(self):
        """Fetch updates from Telegram API"""
        self.ensure_one()
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        
        params = {
            'offset': self.last_update_id + 1 if self.last_update_id else None,
            'timeout': 25,
            'allowed_updates': ['message', 'channel_post']
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok') and data.get('result'):
                _logger.info(f"Received {len(data['result'])} update(s) from Telegram")
                self._process_updates(data['result'])
            else:
                _logger.warning(f"Telegram API returned no updates or error: {data}")
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error fetching Telegram updates: {str(e)}")
    
    def _process_updates(self, updates):
        """Process received updates and store messages"""
        self.ensure_one()
        
        for update in updates:
            try:
                # Update the last_update_id
                if update.get('update_id', 0) > (self.last_update_id or 0):
                    self.last_update_id = update['update_id']
                
                # Get message data
                message_data = update.get('message') or update.get('channel_post')
                if not message_data:
                    continue
                
                # Extract chat and user information
                chat_data = message_data.get('chat', {})
                from_data = message_data.get('from', {})
                
                # Skip if not a group/supergroup
                if chat_data.get('type') not in ['group', 'supergroup']:
                    _logger.debug(f"Skipping message from non-group chat: {chat_data.get('type')}")
                    continue
                
                # Find or create group
                group = self._find_or_create_group(chat_data)
                if not group:
                    continue
                
                # Find or create member
                member = self._find_or_create_member(from_data, group)
                
                # Store the message
                self._store_message(message_data, group, member)
                
            except Exception as e:
                _logger.error(f"Error processing update {update.get('update_id')}: {str(e)}")
                continue
    
    def _find_or_create_group(self, chat_data):
        """Find or create a Telegram group"""
        chat_id = str(chat_data.get('id'))
        group = self.env['telegram.group'].search([
            ('chat_id', '=', chat_id),
            ('config_id', '=', self.id)
        ], limit=1)
        
        if not group:
            group = self.env['telegram.group'].create({
                'name': chat_data.get('title', 'Unknown Group'),
                'chat_id': chat_id,
                'chat_type': chat_data.get('type'),
                'config_id': self.id,
            })
            _logger.info(f"Created new Telegram group: {group.name} (ID: {chat_id})")
        
        return group
    
    def _find_or_create_member(self, from_data, group):
        """Find or create a Telegram member"""
        if not from_data:
            return None
        
        telegram_id = str(from_data.get('id'))
        member = self.env['telegram.member'].search([
            ('telegram_id', '=', telegram_id),
            ('group_id', '=', group.id)
        ], limit=1)
        
        if not member:
            username = from_data.get('username', '')
            first_name = from_data.get('first_name', '')
            last_name = from_data.get('last_name', '')
            
            display_name = ' '.join(filter(None, [first_name, last_name])) or username or 'Unknown'
            
            member = self.env['telegram.member'].create({
                'name': display_name,
                'telegram_id': telegram_id,
                'username': username,
                'group_id': group.id,
                'is_bot': from_data.get('is_bot', False),
            })
            _logger.info(f"Created new member: {member.name} (ID: {telegram_id}) in group {group.name}")
        
        return member
    
    def _store_message(self, message_data, group, member):
        """Store a message in the database"""
        message_id = str(message_data.get('message_id'))
        
        # Check if message already exists
        existing = self.env['telegram.message'].search([
            ('message_id', '=', message_id),
            ('group_id', '=', group.id)
        ], limit=1)
        
        if existing:
            _logger.debug(f"Message {message_id} already exists, skipping")
            return existing
        
        # Extract message content
        text = message_data.get('text') or message_data.get('caption', '')
        
        # Create message record
        message = self.env['telegram.message'].create({
            'message_id': message_id,
            'group_id': group.id,
            'member_id': member.id if member else False,
            'message_text': text,
            'message_date': datetime.fromtimestamp(message_data.get('date', 0)),
            'is_reply': bool(message_data.get('reply_to_message')),
        })
        
        _logger.info(f"✅ Stored message {message_id} from {member.name if member else 'Unknown'} in {group.name}")
        return message