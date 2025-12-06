# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class TelegramConfig(models.Model):
    _name = 'telegram.config'
    _description = 'Telegram Bot Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    bot_token = fields.Char(string='Bot Token', required=True, help='Your Telegram Bot Token from @BotFather')
    team_source_group_id = fields.Many2one('telegram.group', string='Team Source Group',
                                           help='The Telegram group that contains all Nerosoft team members. Anyone in this group will be recognized as team in all client groups.')
    bot_owner_telegram_id = fields.Char('Bot Owner Telegram ID', 
                                        help='Your personal Telegram User ID. You can always add the bot to any group. Find your ID using @userinfobot on Telegram.')
    monitoring_alerts_group_id = fields.Many2one('telegram.group', 
                                                 string='Monitoring Alerts Group',
                                                 help='Group that receives operational alerts (setup delays, security issues, member changes, etc.)')
    log_unauthorized_attempts = fields.Boolean('Log Unauthorized Attempts', default=True,
                                               help='Track when unauthorized users try to add the bot to groups for security audit')
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
    
    def send_telegram_message_with_keyboard(self, chat_id, message, keyboard):
        """Send a message to Telegram with inline keyboard"""
        self.ensure_one()
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'reply_markup': keyboard
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error sending Telegram message with keyboard: {str(e)}")
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
            'allowed_updates': ['message', 'channel_post', 'my_chat_member', 'chat_member', 'callback_query']
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
                
                # Handle callback queries (button clicks)
                if update.get('callback_query'):
                    self._handle_callback_query(update['callback_query'])
                    continue
                
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
        old_status = chat_member_data.get('old_chat_member', {}).get('status')
        from_user = chat_member_data.get('from', {})
        bot_user = chat_member_data.get('new_chat_member', {}).get('user', {})
        bot_id = bot_user.get('id')
        
        # Bot was added to group (as member, not admin yet)
        if old_status in ['left', 'kicked'] and new_status == 'member':
            from_telegram_id = str(from_user.get('id', ''))
            from_name = from_user.get('first_name', 'Unknown')
            from_username = from_user.get('username', '')
            
            # Check authorization
            if not self._is_authorized_to_add_bot(from_telegram_id, from_name, chat_data):
                return  # Already handled in authorization check
            
            # Authorized but not admin yet - send setup instructions
            group = self._find_or_create_group(chat_data)
            if group:
                group.write({
                    'needs_setup': True,
                    'setup_started_at': fields.Datetime.now(),
                    'setup_status': 'pending',
                    'created_by_telegram_id': from_telegram_id,
                    'created_by_name': from_name,
                })
                self._send_setup_incomplete_message(chat_data.get('id'), bot_id, from_name)
                
                # Send alert to monitoring group
                self._send_monitoring_alert_new_group(group, from_name, from_username, from_telegram_id)
                
                _logger.info(f"✅ Bot added to group {group.name} by {from_name} - waiting for admin promotion")
        
        # Bot was promoted to administrator
        elif new_status == 'administrator':
            from_telegram_id = str(from_user.get('id', ''))
            from_name = from_user.get('first_name', 'Unknown')
            
            # Check authorization (in case bot was added then promoted by different person)
            if not self._is_authorized_to_add_bot(from_telegram_id, from_name, chat_data):
                return
            
            # Handle duplicate group cleanup (group → supergroup conversion)
            self._handle_supergroup_conversion(chat_data)
            
            # Get the group (might be new supergroup after conversion)
            group = self._find_or_create_group(chat_data)
            if group:
                # Generate invite link
                invite_link = self._generate_invite_link(group.chat_id)
                if invite_link:
                    setup_duration = 0
                    if group.setup_started_at:
                        duration = fields.Datetime.now() - group.setup_started_at
                        setup_duration = int(duration.total_seconds() / 60)  # Convert to minutes
                    
                    group.write({
                        'invite_link': invite_link,
                        'invite_link_created_at': fields.Datetime.now(),
                        'needs_setup': False,
                        'setup_completed_at': fields.Datetime.now(),
                        'setup_status': 'complete',
                        'setup_duration': setup_duration,
                    })
                    
                    # Send welcome message with invite link
                    welcome_msg = f"""🤖 <b>Bot Activated for {group.name}!</b>

📎 <b>Invite Link:</b>
{invite_link}

Share this link to add members to this group.
I'll automatically track team members vs clients! 📊"""
                    
                    self.send_telegram_message(group.chat_id, welcome_msg)
                    
                    # Send completion alert to monitoring group
                    self._send_monitoring_alert_setup_complete(group, setup_duration)
                    
                    _logger.info(f"✅ Bot promoted to admin in {group.name} by {from_name}, invite link generated (setup time: {setup_duration} min)")
    
    def _handle_callback_query(self, callback_data):
        """Handle button clicks in Telegram"""
        query_id = callback_data.get('id')
        callback_type = callback_data.get('data')
        from_user = callback_data.get('from', {})
        message = callback_data.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        
        if callback_type == 'check_admin_status':
            group = self.env['telegram.group'].search([
                ('chat_id', '=', str(chat_id)),
                ('config_id', '=', self.id)
            ], limit=1)
            
            # Check if setup already complete
            if group and group.setup_status == 'complete':
                self._answer_callback_query(query_id, "✅ Already set up!")
                return
            
            # Check if bot is admin in this group
            is_admin = self._check_bot_admin_status(chat_id)
            
            if is_admin:
                # Bot is admin - generate invite link
                invite_link = self._generate_invite_link(chat_id)
                if invite_link and group:
                    setup_duration = 0
                    if group.setup_started_at:
                        duration = fields.Datetime.now() - group.setup_started_at
                        setup_duration = int(duration.total_seconds() / 60)
                    
                    group.write({
                        'invite_link': invite_link,
                        'invite_link_created_at': fields.Datetime.now(),
                        'needs_setup': False,
                        'setup_completed_at': fields.Datetime.now(),
                        'setup_status': 'complete',
                        'setup_duration': setup_duration,
                    })
                    
                    success_msg = f"""🎉 <b>Perfect! Setup Complete!</b>

📎 <b>Invite Link:</b>
{invite_link}

Share this link to add members to this group.
I'm now monitoring this group! 📊"""
                    
                    self.send_telegram_message(chat_id, success_msg)
                    
                    # Send completion alert to monitoring group
                    self._send_monitoring_alert_setup_complete(group, setup_duration)
                    
                    _logger.info(f"✅ Setup completed via button click for {group.name} (setup time: {setup_duration} min)")
                    
                # Answer callback query
                self._answer_callback_query(query_id, "✅ Setup complete!")
            else:
                # Bot is NOT admin yet
                reminder_msg = """⚠️ <b>Almost there!</b>

I'm not an admin yet. Please make sure you:
✓ Added me as Administrator
✓ Enabled "Invite Users via Link" permission

Try again when ready:"""
                
                keyboard = {
                    'inline_keyboard': [[
                        {
                            'text': '🔄 Check Again',
                            'callback_data': 'check_admin_status'
                        }
                    ]]
                }
                
                self.send_telegram_message_with_keyboard(chat_id, reminder_msg, keyboard)
                
                # Update monitoring group - setup attempted but failed
                if group:
                    self._send_monitoring_alert_setup_failed_attempt(group, from_user.get('first_name', 'Unknown'))
                
                _logger.warning(f"⚠️ User tried to complete setup but bot is not admin yet in {group.name if group else chat_id}")
                
                # Answer callback query
                self._answer_callback_query(query_id, "⚠️ Not admin yet - please check permissions")
    
    def _answer_callback_query(self, query_id, text):
        """Answer a callback query (acknowledge button click)"""
        self.ensure_one()
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        
        payload = {
            'callback_query_id': query_id,
            'text': text,
            'show_alert': False
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception as e:
            _logger.error(f"Failed to answer callback query: {str(e)}")
    
    def _check_bot_admin_status(self, chat_id):
        """Check if bot is an administrator in the group"""
        self.ensure_one()
        url = f"https://api.telegram.org/bot{self.bot_token}/getChatMember"
        
        # Get bot's own user ID first
        me_url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
        
        try:
            me_response = requests.get(me_url, timeout=10)
            me_data = me_response.json()
            bot_user_id = me_data.get('result', {}).get('id')
            
            # Now check bot's status in the group
            payload = {
                'chat_id': chat_id,
                'user_id': bot_user_id
            }
            
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
            
            if data.get('ok'):
                status = data.get('result', {}).get('status')
                return status == 'administrator'
            
            return False
            
        except Exception as e:
            _logger.error(f"Error checking bot admin status: {str(e)}")
            return False
    
    def _is_authorized_to_add_bot(self, telegram_id, user_name, chat_data):
        """Check if user is authorized to add bot to groups"""
        self.ensure_one()
        
        # Check if user is bot owner (always authorized)
        if self.bot_owner_telegram_id and telegram_id == self.bot_owner_telegram_id:
            _logger.info(f"✅ Bot owner {user_name} added bot to group - authorized")
            return True
        
        # Check if user is active team member
        team_member = self.env['telegram.team.member'].search([
            ('telegram_id', '=', telegram_id),
            ('is_active', '=', True)
        ], limit=1)
        
        if team_member:
            _logger.info(f"✅ Team member {user_name} added bot to group - authorized")
            return True
        
        # Unauthorized - log and leave
        _logger.warning(f"🔐 SECURITY ALERT: Unauthorized user {user_name} (ID: {telegram_id}) tried to add bot to {chat_data.get('title', 'Unknown Group')}")
        
        # Send warning message
        warning_msg = f"""⚠️ <b>Unauthorized Access</b>

Sorry, only authorized team members can add this bot to groups.

If you believe this is an error, please contact your administrator."""
        
        try:
            self.send_telegram_message(chat_data.get('id'), warning_msg)
        except:
            _logger.error("Failed to send unauthorized message")
        
        # Log attempt if enabled
        if self.log_unauthorized_attempts:
            self._log_unauthorized_attempt(telegram_id, user_name, chat_data)
        
        # Leave the group
        self._leave_group(chat_data.get('id'))
        
        return False
    
    def _log_unauthorized_attempt(self, telegram_id, user_name, chat_data):
        """Log unauthorized bot addition attempt for security audit"""
        # TODO Phase 2: Create security_audit model to track unauthorized access attempts
        # Alert Tier 1 Response Group if repeat offender detected
        _logger.warning(f"🔐 SECURITY AUDIT: Unauthorized attempt by {user_name} ({telegram_id}) to add bot to {chat_data.get('title')}")
    
    def _leave_group(self, chat_id):
        """Make bot leave a group"""
        self.ensure_one()
        url = f"https://api.telegram.org/bot{self.bot_token}/leaveChat"
        
        payload = {'chat_id': chat_id}
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok'):
                _logger.info(f"✅ Bot left group {chat_id}")
            else:
                _logger.error(f"Failed to leave group: {data}")
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error leaving group: {str(e)}")
    
    def _send_setup_incomplete_message(self, chat_id, bot_id, user_name):
        """Send setup instructions when bot is added without admin rights"""
        self.ensure_one()
        
        message = f"""⚠️ <b>SETUP INCOMPLETE</b>

Thanks {user_name}! To activate monitoring for this group:

📋 <b>STEPS:</b>
1. Tap the group name at the top of this chat
2. Scroll down and tap "Administrators"
3. Tap "Add Admin"
4. Select "Nero Bot"

When finished, click the button below:"""
        
        # Create inline keyboard with check status button
        keyboard = {
            'inline_keyboard': [[
                {
                    'text': '✅ I Made You Admin',
                    'callback_data': 'check_admin_status'
                }
            ]]
        }
        
        try:
            self.send_telegram_message_with_keyboard(chat_id, message, keyboard)
            _logger.info(f"📤 Sent setup instructions to chat {chat_id}")
        except Exception as e:
            _logger.error(f"Failed to send setup instructions: {str(e)}")
    
    def _send_monitoring_alert_new_group(self, group, creator_name, creator_username, creator_telegram_id):
        """Send alert to monitoring group when new group is created"""
        self.ensure_one()
        
        if not self.monitoring_alerts_group_id:
            return  # No monitoring group configured
        
        username_display = f"@{creator_username}" if creator_username else "No username"
        
        message = f"""🆕 <b>NEW GROUP CREATED</b>

📊 <b>Group:</b> {group.name}
👤 <b>Created by:</b> {creator_name}
🆔 <b>Telegram:</b> {username_display}
⏰ <b>Time:</b> {fields.Datetime.now().strftime('%b %d, %Y %I:%M %p')}
⚠️ <b>Status:</b> Pending admin setup

Group ID: {group.chat_id}
Creator ID: {creator_telegram_id}"""
        
        try:
            self.send_telegram_message(
                self.monitoring_alerts_group_id.chat_id,
                message
            )
            _logger.info(f"📤 Sent new group alert to monitoring group for {group.name}")
        except Exception as e:
            _logger.error(f"Failed to send monitoring alert: {str(e)}")
    
    def _send_monitoring_alert_setup_complete(self, group, setup_duration):
        """Send alert to monitoring group when setup is completed"""
        self.ensure_one()
        
        if not self.monitoring_alerts_group_id:
            return
        
        message = f"""✅ <b>SETUP COMPLETE</b>

📊 <b>Group:</b> {group.name}
👤 <b>Set up by:</b> {group.created_by_name or 'Unknown'}
⏱️ <b>Setup time:</b> {setup_duration} minutes
📎 <b>Invite link:</b> Generated
🎯 <b>Status:</b> Active monitoring

Group ID: {group.chat_id}"""
        
        try:
            self.send_telegram_message(
                self.monitoring_alerts_group_id.chat_id,
                message
            )
            _logger.info(f"📤 Sent setup complete alert to monitoring group for {group.name}")
        except Exception as e:
            _logger.error(f"Failed to send monitoring alert: {str(e)}")
    
    def _send_monitoring_alert_setup_failed_attempt(self, group, user_name):
        """Send alert when user tries to complete setup but bot is not admin"""
        self.ensure_one()
        
        if not self.monitoring_alerts_group_id:
            return
        
        message = f"""⚠️ <b>SETUP ATTEMPT FAILED</b>

📊 <b>Group:</b> {group.name}
👤 <b>User:</b> {user_name}
❌ <b>Issue:</b> Bot not yet admin
⏱️ <b>Pending for:</b> {self._get_pending_duration(group)} minutes

User clicked "I Made You Admin" but permissions not granted yet."""
        
        try:
            self.send_telegram_message(
                self.monitoring_alerts_group_id.chat_id,
                message
            )
            _logger.info(f"📤 Sent failed setup attempt alert for {group.name}")
        except Exception as e:
            _logger.error(f"Failed to send monitoring alert: {str(e)}")
    
    def _get_pending_duration(self, group):
        """Calculate how long setup has been pending"""
        if not group.setup_started_at:
            return 0
        duration = fields.Datetime.now() - group.setup_started_at
        return int(duration.total_seconds() / 60)
    
    def _handle_supergroup_conversion(self, chat_data):
        """Handle cleanup when a group is converted to supergroup"""
        self.ensure_one()
        
        chat_id = str(chat_data.get('id'))
        group_name = chat_data.get('title', '')
        
        # Supergroups have IDs starting with -100
        if not chat_id.startswith('-100'):
            return  # Not a supergroup
        
        # Look for old group with similar name created recently (within last 5 minutes)
        five_min_ago = fields.Datetime.now() - timedelta(minutes=5)
        
        old_groups = self.env['telegram.group'].search([
            ('name', '=', group_name),
            ('chat_id', '!=', chat_id),
            ('config_id', '=', self.id),
            ('create_date', '>=', five_min_ago)
        ])
        
        if old_groups:
            for old_group in old_groups:
                _logger.info(f"🔄 Merging old group {old_group.chat_id} into new supergroup {chat_id}")
                
                # Move members from old group to new group (will happen automatically on next poll)
                # For now, just delete the old group record
                old_group.unlink()
                
            _logger.info(f"✅ Cleaned up {len(old_groups)} duplicate group record(s)")
    
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
            # Alert Tier 1 Response Group for member removal approval
    
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