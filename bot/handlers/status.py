"""
Status handlers for the Telegram bot
Handles bot status changes (added/removed from chats) and my_chat_member events
"""

from telegram import Update, ChatMember
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ChatMemberStatus
import logging

from bot.database.database import db
from bot.utils.helpers import is_bot_admin, get_chat_admins

logger = logging.getLogger(__name__)


async def handle_bot_added_to_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle when bot is added to a chat (legacy method, prefer my_chat_member)"""
    message = update.message
    chat = message.chat
    
    # Skip if message is from GroupAnonymousBot (not a real user action)
    if message.from_user and message.from_user.username == "GroupAnonymousBot":
        logger.debug(f"Skipping GroupAnonymousBot message in chat {chat.id}")
        return
    
    # Only process group/supergroup chats
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    
    # Check if bot was added
    new_members = message.new_chat_members
    bot_added = any(member.id == context.bot.id for member in new_members)
    
    if not bot_added:
        return
    
    logger.info(f"Bot added to chat {chat.id} via legacy method")
    
    # Check if bot is admin and handle accordingly
    if await is_bot_admin(chat.id, context):
        await handle_bot_promoted_to_admin(chat, context)
    else:
        logger.warning(f"Bot added to chat {chat.id} but is not admin")


async def handle_bot_removed_from_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle when bot is removed from a chat (legacy method, prefer my_chat_member)"""
    message = update.message
    chat = message.chat
    
    # Skip if message is from GroupAnonymousBot (not a real user action)
    if message.from_user and message.from_user.username == "GroupAnonymousBot":
        logger.debug(f"Skipping GroupAnonymousBot message in chat {chat.id}")
        return
    
    # Check if bot was removed
    left_member = message.left_chat_member
    if not left_member or left_member.id != context.bot.id:
        return
    
    # Deactivate chat in database
    success = db.deactivate_chat(chat.id)
    if success:
        logger.info(f"Deactivated chat {chat.id} via legacy method")
    else:
        logger.error(f"Failed to deactivate chat {chat.id}")


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle my_chat_member updates (when bot status changes)"""
    my_chat_member = update.my_chat_member
    if not my_chat_member:
        return
    
    chat = my_chat_member.chat
    old_member = my_chat_member.old_chat_member
    new_member = my_chat_member.new_chat_member
    
    # Log the full update for debugging
    logger.info(f"my_chat_member update received for chat {chat.id} ({chat.type})")
    logger.debug(f"Old status: {old_member.status if old_member else 'None'}")
    logger.debug(f"New status: {new_member.status}")
    
    # Process groups, supergroups, and channels
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        logger.debug(f"Ignoring chat type {chat.type} for chat {chat.id}")
        return
    
    # Check if this is about our bot
    if new_member.user.id != context.bot.id:
        logger.debug(f"Update not about our bot (user {new_member.user.id})")
        return
    
    old_status = old_member.status if old_member else ChatMemberStatus.LEFT
    new_status = new_member.status
    
    logger.info(f"Bot status changed in chat {chat.id} ({chat.title}): {old_status} -> {new_status}")
    
    # Bot was added/promoted to admin
    if new_status == ChatMemberStatus.ADMINISTRATOR:
        logger.info(f"Bot promoted to admin in chat {chat.id}")
        if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            # Only groups and supergroups are added to bot_chats table
            await handle_bot_promoted_to_admin(chat, context)
        elif chat.type == ChatType.CHANNEL:
            # Channels are NOT added to bot_chats table
            # They are managed exclusively through chat_channel_bindings table
            logger.info(f"Bot added as admin to channel {chat.id} - channels are managed via bindings only")
    
    # Bot was removed, kicked, or left
    elif new_status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
        logger.info(f"Bot removed from {chat.type.value} {chat.id} (status: {new_status})")
        
        try:
            if chat.type == ChatType.CHANNEL:
                # For channels, we only need to deactivate channel bindings
                success = db.deactivate_channel_bindings(chat.id)
                if success:
                    logger.info(f"Successfully deactivated channel bindings for channel {chat.id}")
                else:
                    logger.warning(f"No active bindings found for channel {chat.id}")
                    
            else:
                # For groups and supergroups, handle as before
                cursor = db.connection.cursor()
                check_query = "SELECT COUNT(*) FROM bot_chats WHERE chat_id = %s"
                cursor.execute(check_query, (chat.id,))
                exists = cursor.fetchone()[0] > 0
                cursor.close()
                
                if exists:
                    success = db.deactivate_chat(chat.id)
                    if success:
                        logger.info(f"Successfully deactivated {chat.type.value} {chat.id} in database")
                        
                        # Also deactivate channel bindings for this chat
                        removed_bindings = db.remove_chat_channel_binding(chat.id)
                        if removed_bindings:
                            logger.info(f"Deactivated channel bindings for {chat.type.value} {chat.id}")
                            
                    else:
                        logger.error(f"Failed to deactivate {chat.type.value} {chat.id} in database")
                else:
                    logger.warning(f"{chat.type.value} {chat.id} not found in database (was never properly added)")
                
        except Exception as e:
            logger.error(f"Error deactivating {chat.type.value} {chat.id}: {e}")
    
    # Bot was demoted from admin to member
    elif old_status == ChatMemberStatus.ADMINISTRATOR and new_status == ChatMemberStatus.MEMBER:
        logger.info(f"Bot demoted from admin in chat {chat.id}")
        
        try:
            success = db.deactivate_chat(chat.id)
            if success:
                logger.info(f"Deactivated chat {chat.id} - bot demoted from admin")
                
                # Also remove channel bindings since bot lost admin rights
                removed_bindings = db.remove_chat_channel_binding(chat.id)
                if removed_bindings:
                    logger.info(f"Removed channel bindings for demoted bot in chat {chat.id}")
                    
        except Exception as e:
            logger.error(f"Error handling bot demotion in chat {chat.id}: {e}")
    
    # Bot became member (was added but not as admin)
    elif new_status == ChatMemberStatus.MEMBER:
        logger.warning(f"Bot added to chat {chat.id} as regular member (not admin)")
        
    else:
        logger.info(f"Unhandled status change in chat {chat.id}: {old_status} -> {new_status}")


async def handle_bot_promoted_to_admin(chat, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle when bot gets admin rights in a chat"""
    try:
        # Get real chat admins (not bots)
        admins = await get_chat_admins(chat.id, context)
        
        for admin in admins:
            # Convert chat.type to string value for database - THIS IS THE FIX!
            success = db.add_chat(chat.id, chat.title, chat.type.value, admin.user.id)
            if success:
                logger.info(f"Added chat {chat.id} for admin {admin.user.id}")
                
                # Send notification to admin in private message
                try:
                    await context.bot.send_message(
                        chat_id=admin.user.id,
                        text=(
                            "✅ **Бот готов к работе!**\n\n"
                            f"💬 **Чат:** {chat.title or 'Без названия'}\n\n"
                            "📋 Вы можете настроить пересылку отредактированных сообщений "
                            "с помощью команды /chats в этой беседе.\n\n"
                            "❗ **Важно:** Я буду отслеживать только сообщения обычных пользователей. "
                            "Сообщения администраторов игнорируются."
                        ),
                        parse_mode='Markdown'
                    )
                    logger.info(f"Notification sent to admin {admin.user.id}")
                except Exception as e:
                    logger.warning(f"Could not send notification to admin {admin.user.id}: {e}")
        
        logger.info(f"Bot promoted to admin in chat {chat.id}, notifications sent to {len(admins)} admins")
        
    except Exception as e:
        logger.error(f"Error handling bot promotion in chat {chat.id}: {e}")