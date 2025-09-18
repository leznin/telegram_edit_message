"""
Helper functions for the Telegram bot
"""

from typing import List, Optional
from telegram import ChatMember, Chat, User
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)


async def is_user_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is admin in the chat"""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


async def is_bot_admin(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if bot is admin in the chat"""
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        return bot_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception as e:
        logger.error(f"Error checking bot admin status: {e}")
        return False


async def check_bot_channel_permissions(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Check bot permissions in channel and return detailed status"""
    result = {
        'is_admin': False,
        'can_post_messages': False,
        'can_edit_messages': False,
        'can_delete_messages': False,
        'error': None
    }
    
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        
        # Проверяем статус бота
        if bot_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            result['is_admin'] = True
            
            # Проверяем конкретные права
            if hasattr(bot_member, 'can_post_messages'):
                result['can_post_messages'] = bot_member.can_post_messages
            
            if hasattr(bot_member, 'can_edit_messages'):
                result['can_edit_messages'] = bot_member.can_edit_messages
            
            if hasattr(bot_member, 'can_delete_messages'):
                result['can_delete_messages'] = bot_member.can_delete_messages
                
        elif bot_member.status == ChatMember.MEMBER:
            # Обычный участник - может отправлять сообщения если канал не restricted
            result['can_post_messages'] = True
            
        logger.info(f"Bot permissions in {chat_id}: {result}")
        return result
        
    except Exception as e:
        error_msg = str(e)
        result['error'] = error_msg
        logger.error(f"Error checking bot permissions in channel {chat_id}: {error_msg}")
        
        # Пытаемся определить тип ошибки
        if "not found" in error_msg.lower() or "chat not found" in error_msg.lower():
            result['error'] = "Канал не найден или бот не добавлен в канал"
        elif "forbidden" in error_msg.lower():
            result['error'] = "Нет доступа к каналу - добавьте бота в канал"
        elif "administrator rights" in error_msg.lower():
            result['error'] = "Боту нужны права администратора в канале"
        
        return result


async def get_chat_admins(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> List[ChatMember]:
    """Get list of chat administrators"""
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return [admin for admin in admins if not admin.user.is_bot]
    except Exception as e:
        logger.error(f"Error getting chat admins: {e}")
        return []


def format_user_mention(user: User) -> str:
    """Format user mention for display"""
    if user.username:
        return f"@{user.username}"
    elif user.full_name:
        return user.full_name
    else:
        return f"User {user.id}"


def format_chat_title(chat: Chat) -> str:
    """Format chat title for display"""
    if chat.title:
        return chat.title
    elif chat.type == Chat.PRIVATE:
        return f"Private chat with {format_user_mention(chat)}"
    else:
        return f"Chat {chat.id}"


def escape_markdown(text: str) -> str:
    """Escape special markdown characters for MarkdownV2"""
    if not text:
        return ""
    
    # Список специальных символов для MarkdownV2
    special_chars = [
        '\\', '_', '*', '[', ']', '(', ')', '~', '`', 
        '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    ]
    
    # Экранируем символы в правильном порядке (backslash первым)
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def escape_markdown_safe(text: str) -> str:
    """Safely escape markdown with additional validation"""
    if not text:
        return ""
    
    try:
        # Удаляем или заменяем проблематичные последовательности
        text = str(text)
        
        # Заменяем переносы строк на пробелы для безопасности
        text = text.replace('\n', ' ').replace('\r', ' ')
        
        # Удаляем непечатаемые символы
        text = ''.join(char for char in text if char.isprintable() or char.isspace())
        
        # Обрезаем до разумной длины
        if len(text) > 3000:
            text = text[:3000] + "..."
        
        return escape_markdown(text)
    except Exception as e:
        logger.error(f"Error in escape_markdown_safe: {e}")
        # Возвращаем безопасную версию без специальных символов
        return ''.join(char for char in str(text) if char.isalnum() or char.isspace())[:1000]


def truncate_text(text: str, max_length: int = 4000) -> str:
    """Truncate text to fit Telegram message limits"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


async def safe_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> bool:
    """Safely delete a message"""
    try:
        logger.info(f"Attempting to delete message {message_id} in chat {chat_id}")
        
        # Проверяем, является ли бот администратором
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        logger.info(f"Bot status in chat {chat_id}: {bot_member.status}")
        
        if bot_member.status not in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            logger.warning(f"Bot is not admin in chat {chat_id}, cannot delete message")
            return False
            
        # Проверяем права на удаление сообщений
        if hasattr(bot_member, 'can_delete_messages') and not bot_member.can_delete_messages:
            logger.warning(f"Bot doesn't have can_delete_messages permission in chat {chat_id}")
            return False
        
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully deleted message {message_id} in chat {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting message {message_id} in chat {chat_id}: {e}")
        return False


async def safe_send_message(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> Optional[int]:
    """Safely send a message and return message ID"""
    try:
        message = await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return message.message_id
    except Exception as e:
        logger.error(f"Error sending message to chat {chat_id}: {e}")
        return None


async def safe_send_to_channel(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE, parse_mode: str = None) -> bool:
    """Safely send message to channel with fallback mechanisms"""
    try:
        # Сначала проверяем права бота в канале
        permissions = await check_bot_channel_permissions(chat_id, context)
        
        if permissions['error']:
            logger.error(f"Channel permissions error: {permissions['error']}")
            return False
            
        if not permissions['can_post_messages']:
            logger.error(f"Bot cannot post messages to channel {chat_id}")
            return False
        
        # Пытаемся отправить с указанным parse_mode
        if parse_mode:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
                logger.info(f"Successfully sent message to channel {chat_id} with {parse_mode}")
                return True
            except Exception as parse_error:
                logger.warning(f"Failed to send with {parse_mode}: {parse_error}")
                # Продолжаем к fallback
        
        # Fallback: отправляем без parse_mode
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text
            )
            logger.info(f"Successfully sent fallback message to channel {chat_id}")
            return True
        except Exception as fallback_error:
            logger.error(f"Failed to send fallback message: {fallback_error}")
            return False
            
    except Exception as e:
        logger.error(f"Unexpected error in safe_send_to_channel: {e}")
        return False


async def forward_message_to_channel(
    from_chat_id: int,
    message_id: int,
    to_chat_id: int,
    context: ContextTypes.DEFAULT_TYPE
) -> Optional[int]:
    """Forward a message to channel and return forwarded message ID"""
    try:
        forwarded = await context.bot.forward_message(
            chat_id=to_chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id
        )
        return forwarded.message_id
    except Exception as e:
        logger.error(f"Error forwarding message: {e}")
        return None


async def send_media_to_channel(
    message,
    channel_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    caption: str = None
) -> bool:
    """Send media file to channel with fallback mechanisms"""
    try:
        # Check bot permissions first
        permissions = await check_bot_channel_permissions(channel_id, context)
        if permissions['error'] or not permissions['can_post_messages']:
            logger.error(f"Cannot send media to channel {channel_id}: {permissions.get('error', 'No permissions')}")
            return False

        # Determine media type and send accordingly
        if hasattr(message, 'photo') and message.photo:
            # Send the largest photo
            largest_photo = message.photo[-1]  # Last one is largest
            await context.bot.send_photo(
                chat_id=channel_id,
                photo=largest_photo.file_id,
                caption=caption[:1024] if caption else None,  # Telegram caption limit
                parse_mode=None  # No parse mode for media captions to avoid issues
            )
            logger.info(f"Successfully sent photo to channel {channel_id}")
            return True

        elif hasattr(message, 'video') and message.video:
            await context.bot.send_video(
                chat_id=channel_id,
                video=message.video.file_id,
                caption=caption[:1024] if caption else None,
                parse_mode=None
            )
            logger.info(f"Successfully sent video to channel {channel_id}")
            return True

        elif hasattr(message, 'document') and message.document:
            await context.bot.send_document(
                chat_id=channel_id,
                document=message.document.file_id,
                caption=caption[:1024] if caption else None,
                parse_mode=None
            )
            logger.info(f"Successfully sent document to channel {channel_id}")
            return True

        elif hasattr(message, 'audio') and message.audio:
            await context.bot.send_audio(
                chat_id=channel_id,
                audio=message.audio.file_id,
                caption=caption[:1024] if caption else None,
                parse_mode=None
            )
            logger.info(f"Successfully sent audio to channel {channel_id}")
            return True

        elif hasattr(message, 'voice') and message.voice:
            await context.bot.send_voice(
                chat_id=channel_id,
                voice=message.voice.file_id,
                caption=caption[:1024] if caption else None,
                parse_mode=None
            )
            logger.info(f"Successfully sent voice message to channel {channel_id}")
            return True

        else:
            logger.warning("Unknown media type, cannot send")
            return False

    except Exception as e:
        logger.error(f"Error sending media to channel {channel_id}: {e}")
        return False