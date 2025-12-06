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
    team_source_group_id = fields.Many2one('telegram.group', string='Team Source Group',
                                           help='The Telegram group that contains all Nerosoft team members. Anyone in this group will be recognized as team in all client groups.')
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
    
    def _generate_invite_link(self, chat_id):
        """Generate invite link for a group"""
        self.ensure_one()
        url = f"https://api.telegram.org/bot{self.bot_token}/exportChatInviteLink"
        
        payload = {'chat_id': chat_id}
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok'):
                return data.get('result')
            else:
                _logger.error(f"Failed to generate invite link: {data}")
                return None
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error generating invite link: {str(e)}")
            return None
    
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
            'allowed_updates': ['message', 'channel_post', 'my_chat_member', 'chat_member']
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
                
                # Handle bot being added to group
                if update.get('my_chat_member'):
                    self._handle_bot_status_change(update['my_chat_member'])
                    continue
                
                # Handle member status changes (joins/leaves)
                if update.get('chat_member'):
                    self._handle_member_status_change(update['chat_member'])
                    continue
                
                # Get message data
                message_data = update.get('message') or update.get('channel_post')
                if not message_data:
                    continue
                
                # Handle new members joining
                if message_data.get('new_chat_members'):
                    self._handle_new_members(message_data)
                
                # Handle member leaving
                if message_data.get('left_chat_member'):
                    self._handle_member_left(message_data)
                
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
    
    def _handle_bot_status_change(self, chat_member_data):
        """Handle bot being added/removed from group"""
        chat_data = chat_member_data.get('chat', {})
        new_status = chat_member_data.get('new_chat_member', {}).get('status')
        
        # Bot was added to group
        if new_status in ['member', 'administrator']:
            group = self._find_or_create_group(chat_data)
            if group:
                # Generate invite link
                invite_link = self._generate_invite_link(group.chat_id)
                if invite_link:
                    group.write({'invite_link': invite_link})
                    
                    # Send welcome message with invite link
                    welcome_msg = f"""🤖 <b>Bot Activated for {group.name}!</b>

📎 <b>Invite Link:</b>
{invite_link}

Share this link to add members to this group.
I'll automatically track team members vs clients! 📊"""
                    
                    self.send_telegram_message(group.chat_id, welcome_msg)
                    _logger.info(f"✅ Bot added to group {group.name}, invite link generated")
    
    def _handle_member_status_change(self, chat_member_data):
        """Handle member status changes (chat_member update)"""
        chat_data = chat_member_data.get('chat', {})
        user_data = chat_member_data.get('new_chat_member', {}).get('user', {})
        new_status = chat_member_data.get('new_chat_member', {}).get('status')
        old_status = chat_member_data.get('old_chat_member', {}).get('status')
        
        group = self._find_or_create_group(chat_data)
        if not group:
            return
        
        telegram_id = str(user_data.get('id'))
        
        # Member joined
        if old_status in ['left', 'kicked'] and new_status in ['member', 'administrator', 'creator']:
            self._process_member_join(user_data, group)
        
        # Member left or was removed
        elif old_status in ['member', 'administrator'] and new_status in ['left', 'kicked', 'restricted']:
            self._process_member_leave(telegram_id, group)
    
    def _handle_new_members(self, message_data):
        """Handle new_chat_members in message"""
        chat_data = message_data.get('chat', {})
        new_members = message_data.get('new_chat_members', [])
        
        group = self._find_or_create_group(chat_data)
        if not group:
            return
        
        for user_data in new_members:
            self._process_member_join(user_data, group)
    
    def _handle_member_left(self, message_data):
        """Handle left_chat_member in message"""
        chat_data = message_data.get('chat', {})
        user_data = message_data.get('left_chat_member', {})
        
        group = self._find_or_create_group(chat_data)
        if not group:
            return
        
        telegram_id = str(user_data.get('id'))
        self._process_member_leave(telegram_id, group)
    
    def _process_member_join(self, user_data, group):
        """Process a member joining a group"""
        telegram_id = str(user_data.get('id'))
        username = user_data.get('username', '')
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        display_name = ' '.join(filter(None, [first_name, last_name])) or username or 'Unknown'
        
        # Find or create member in this group
        member = self.env['telegram.member'].search([
            ('telegram_id', '=', telegram_id),
            ('group_id', '=', group.id)
        ], limit=1)
        
        if member:
            member.write({'is_active': True, 'left_date': False})
            _logger.info(f"✅ {display_name} re-joined {group.name}")
        else:
            member = self.env['telegram.member'].create({
                'name': display_name,
                'telegram_id': telegram_id,
                'username': username,
                'group_id': group.id,
                'is_bot': user_data.get('is_bot', False),
            })
            _logger.info(f"✅ New member {display_name} joined {group.name}")
        
        # If this is the team source group, register as team member
        if self.team_source_group_id and group.id == self.team_source_group_id.id:
            self._register_team_member(user_data)
    
    def _process_member_leave(self, telegram_id, group):
        """Process a member leaving a group"""
        member = self.env['telegram.member'].search([
            ('telegram_id', '=', telegram_id),
            ('group_id', '=', group.id)
        ], limit=1)
        
        if member:
            member.write({
                'is_active': False,
                'left_date': fields.Datetime.now()
            })
            _logger.info(f"👋 {member.name} left {group.name}")
            
            # If this is the team source group, deactivate team member
            if self.team_source_group_id and group.id == self.team_source_group_id.id:
                self._deactivate_team_member(telegram_id)
    
    def _register_team_member(self, user_data):
        """Register a user as a team member"""
        telegram_id = str(user_data.get('id'))
        username = user_data.get('username', '')
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        display_name = ' '.join(filter(None, [first_name, last_name])) or username or 'Unknown'
        
        # Check if already exists
        team_member = self.env['telegram.team.member'].search([
            ('telegram_id', '=', telegram_id)
        ], limit=1)
        
        if team_member:
            team_member.write({'is_active': True})
            _logger.info(f"🔄 Reactivated team member: {display_name}")
        else:
            self.env['telegram.team.member'].create({
                'name': display_name,
                'telegram_id': telegram_id,
                'username': username,
            })
            _logger.info(f"✅ Registered NEW team member: {display_name}")
    
    def _deactivate_team_member(self, telegram_id):
        """Deactivate a team member"""
        team_member = self.env['telegram.team.member'].search([
            ('telegram_id', '=', telegram_id)
        ], limit=1)
        
        if team_member:
            team_member.write({'is_active': False})
            _logger.info(f"⚠️ Deactivated team member: {team_member.name}")
            
            # TODO Phase 2: Check if member is still in other client groups
            # and send alert to steering committee
    
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
    
    def action_sync_team_members(self):
        """Manually sync team members from the team source group"""
        self.ensure_one()
        if not self.team_source_group_id:
            raise UserError(_('Please select a Team Source Group first'))
        
        team_group = self.team_source_group_id
        team_members = team_group.member_ids.filtered('is_active')
        
        # Get all unique telegram IDs from team group
        team_telegram_ids = team_members.mapped('telegram_id')
        
        # Update existing team member records
        synced_count = 0
        for member in team_members:
            existing = self.env['telegram.team.member'].search([
                ('telegram_id', '=', member.telegram_id)
            ])
            if existing:
                existing.write({'is_active': True})
            else:
                self.env['telegram.team.member'].create({
                    'name': member.name,
                    'telegram_id': member.telegram_id,
                    'username': member.username,
                })
            synced_count += 1
        
        # Deactivate team members no longer in the group
        all_team_ids = self.env['telegram.team.member'].search([]).mapped('telegram_id')
        removed_ids = list(set(all_team_ids) - set(team_telegram_ids))
        if removed_ids:
            self.env['telegram.team.member'].search([
                ('telegram_id', 'in', removed_ids)
            ]).write({'is_active': False})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Team Members Synced'),
                'message': _('Successfully synced %d team members from %s') % (synced_count, team_group.name),
                'type': 'success',
            }
        }