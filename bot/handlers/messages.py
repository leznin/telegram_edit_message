"""
Message handlers for the Telegram bot
Handles message editing events and forwarding
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType
import logging
from datetime import datetime, timedelta

from bot.database.database import db
from bot.utils.helpers import (
    is_user_admin,
    safe_delete_message,
    truncate_text,
    escape_markdown,
    escape_markdown_safe,
    check_bot_channel_permissions,
    safe_send_to_channel,
    forward_message_to_channel,
    send_media_to_channel
)

logger = logging.getLogger(__name__)


async def send_channel_notification(edited_message, chat, user, edited_text, has_media, media_type, media_info, media_forward_success, delete_success, channel_id, context):
    """Send notification about edited message to channel"""
    # Format message for channel with edited message info
    user_data = {}

    # Обязательные поля пользователя
    user_data['id'] = user.id
    user_data['is_bot'] = user.is_bot
    user_data['first_name'] = user.first_name

    # Опциональные поля пользователя
    if hasattr(user, 'last_name') and user.last_name:
        user_data['last_name'] = user.last_name
    if hasattr(user, 'username') and user.username:
        user_data['username'] = user.username
    if hasattr(user, 'language_code') and user.language_code:
        user_data['language_code'] = user.language_code
    if hasattr(user, 'is_premium') and user.is_premium:
        user_data['is_premium'] = user.is_premium
    if hasattr(user, 'added_to_attachment_menu') and user.added_to_attachment_menu:
        user_data['added_to_attachment_menu'] = user.added_to_attachment_menu

    # Дополнительные поля для ботов (обычно недоступны в сообщениях от пользователей)
    if user.is_bot:
        if hasattr(user, 'can_join_groups') and user.can_join_groups is not None:
            user_data['can_join_groups'] = user.can_join_groups
        if hasattr(user, 'can_read_all_group_messages') and user.can_read_all_group_messages is not None:
            user_data['can_read_all_group_messages'] = user.can_read_all_group_messages
        if hasattr(user, 'supports_inline_queries') and user.supports_inline_queries is not None:
            user_data['supports_inline_queries'] = user.supports_inline_queries
        if hasattr(user, 'can_connect_to_business') and user.can_connect_to_business is not None:
            user_data['can_connect_to_business'] = user.can_connect_to_business
        if hasattr(user, 'has_main_web_app') and user.has_main_web_app is not None:
            user_data['has_main_web_app'] = user.has_main_web_app

    # Логирование всех данных пользователя
    logger.info(f"Complete user data: {user_data}")

    # Создаем детальное сообщение с безопасной обработкой данных
    user_display_name = user_data.get('first_name', 'Unknown')
    if user_data.get('last_name'):
        user_display_name += f" {user_data['last_name']}"

    username_display = f"@{user_data['username']}" if user_data.get('username') else "без username"

    # Создаем сообщение с максимальной информацией, используя безопасное экранирование
    formatted_message = f"""🔄 **ОТРЕДАКТИРОВАННОЕ СООБЩЕНИЕ УДАЛЕНО**

👤 **ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:**
• ID: `{escape_markdown(str(user_data['id']))}`
• Имя: {escape_markdown_safe(user_display_name)}
• Username: {escape_markdown_safe(username_display)}
• Тип: {'🤖 Бот' if user_data['is_bot'] else '👨‍💻 Пользователь'}"""

    # Добавляем опциональные данные если они есть
    if user_data.get('language_code'):
        formatted_message += f"\n• Язык: `{escape_markdown(user_data['language_code'])}`"

    if user_data.get('is_premium'):
        formatted_message += f"\n• 💎 Telegram Premium: {escape_markdown('Да' if user_data['is_premium'] else 'Нет')}"

    if user_data.get('added_to_attachment_menu'):
        formatted_message += f"\n• Меню вложений: {escape_markdown('Добавлен' if user_data['added_to_attachment_menu'] else 'Не добавлен')}"

    # Для ботов - дополнительная информация
    if user_data['is_bot']:
        if user_data.get('can_join_groups') is not None:
            formatted_message += f"\n• Может присоединяться к группам: {'Да' if user_data['can_join_groups'] else 'Нет'}"
        if user_data.get('can_read_all_group_messages') is not None:
            formatted_message += f"\n• Читает все сообщения: {'Да' if user_data['can_read_all_group_messages'] else 'Нет'}"
        if user_data.get('supports_inline_queries') is not None:
            formatted_message += f"\n• Поддерживает inline: {'Да' if user_data['supports_inline_queries'] else 'Нет'}"
        if user_data.get('can_connect_to_business') is not None:
            formatted_message += f"\n• Бизнес подключение: {'Да' if user_data['can_connect_to_business'] else 'Нет'}"
        if user_data.get('has_main_web_app') is not None:
            formatted_message += f"\n• Есть Web App: {'Да' if user_data['has_main_web_app'] else 'Нет'}"

    # Информация о чате
    chat_title = escape_markdown_safe(chat.title or "Неизвестный чат")
    formatted_message += f"""

📍 **ДАННЫЕ ЧАТА:**
• Название: {chat_title}
• ID чата: `{escape_markdown(str(chat.id))}`
• Тип чата: `{escape_markdown(chat.type.value)}`"""

    # Добавляем дополнительные данные чата если доступны
    if hasattr(chat, 'username') and chat.username:
        formatted_message += f"\n• Username чата: @{escape_markdown(chat.username)}"

    if hasattr(chat, 'description') and chat.description:
        chat_desc = escape_markdown_safe(truncate_text(chat.description, 100))
        formatted_message += f"\n• Описание: {chat_desc}"

    # Информация о сообщении
    formatted_message += f"""

📝 **ДАННЫЕ СООБЩЕНИЯ:**
• ID сообщения: `{escape_markdown(str(edited_message.message_id))}`"""

    # Время редактирования
    if edited_message.edit_date:
        edit_time = edited_message.edit_date.strftime('%d.%m.%Y %H:%M:%S')
        formatted_message += f"\n• Время редактирования: `{escape_markdown(edit_time)}`"

    # Время отправки оригинального сообщения
    if edited_message.date:
        send_time = edited_message.date.strftime('%d.%m.%Y %H:%M:%S')
        formatted_message += f"\n• Время отправки: `{escape_markdown(send_time)}`"

    # Добавляем информацию о пересылке если есть
    if hasattr(edited_message, 'forward_origin') and edited_message.forward_origin:
        formatted_message += f"\n• Переслано: Да"

    # Информация о reply если есть
    if hasattr(edited_message, 'reply_to_message') and edited_message.reply_to_message:
        formatted_message += f"\n• Ответ на сообщение: `{escape_markdown(str(edited_message.reply_to_message.message_id))}`"

    # Добавляем информацию о медиа если есть
    if has_media:
        formatted_message += f"""

📎 **МЕДИА-ФАЙЛ:**
• Тип: {media_type.upper()}"""

        if media_type == 'photo':
            formatted_message += f"\n• Количество размеров: {escape_markdown(str(media_info['count']))}"
            largest = media_info['sizes'][-1]  # Последний - самый большой
            formatted_message += f"\n• Разрешение: {escape_markdown(str(largest['width']))}x{escape_markdown(str(largest['height']))}"
        elif media_type == 'video':
            if media_info.get('duration'):
                formatted_message += f"\n• Длительность: {escape_markdown(str(media_info['duration']))} сек"
            if media_info.get('width') and media_info.get('height'):
                formatted_message += f"\n• Разрешение: {escape_markdown(str(media_info['width']))}x{escape_markdown(str(media_info['height']))}"
            if media_info.get('file_size'):
                file_size_mb = media_info['file_size'] / 1024 / 1024
                formatted_message += f"\n• Размер файла: {escape_markdown(f'{file_size_mb:.1f}')} MB"
        elif media_type == 'document':
            if media_info.get('file_name'):
                formatted_message += f"\n• Имя файла: {escape_markdown_safe(media_info['file_name'])}"
            if media_info.get('mime_type'):
                formatted_message += f"\n• Тип файла: {escape_markdown(media_info['mime_type'])}"
            if media_info.get('file_size'):
                file_size_mb = media_info['file_size'] / 1024 / 1024
                formatted_message += f"\n• Размер файла: {escape_markdown(f'{file_size_mb:.1f}')} MB"
        elif media_type == 'audio':
            if media_info.get('title'):
                formatted_message += f"\n• Название: {escape_markdown_safe(media_info['title'])}"
            if media_info.get('performer'):
                formatted_message += f"\n• Исполнитель: {escape_markdown_safe(media_info['performer'])}"
            if media_info.get('duration'):
                formatted_message += f"\n• Длительность: {escape_markdown(str(media_info['duration']))} сек"
            if media_info.get('file_size'):
                file_size_mb = media_info['file_size'] / 1024 / 1024
                formatted_message += f"\n• Размер файла: {escape_markdown(f'{file_size_mb:.1f}')} MB"
        elif media_type == 'voice':
            if media_info.get('duration'):
                formatted_message += f"\n• Длительность: {escape_markdown(str(media_info['duration']))} сек"
            if media_info.get('file_size'):
                file_size_kb = media_info['file_size'] / 1024
                formatted_message += f"\n• Размер файла: {escape_markdown(f'{file_size_kb:.1f}')} KB"

        formatted_message += f"\n• Пересылка: {'✅ Успешно' if media_forward_success else '❌ Не удалось'}"

    # Добавляем текст сообщения
    safe_text = escape_markdown(truncate_text(edited_text, 1000))
    if edited_text != 'Текст недоступен' or has_media:
        formatted_message += f"""

💬 **СОДЕРЖИМОЕ:**
{safe_text}
"""
    else:
        formatted_message += f"""

💬 **СОДЕРЖИМОЕ:**
{safe_text}
"""

    formatted_message += f"⚠️ **Действие:** {'Сообщение удалено из чата' if delete_success else 'Сообщение оставлено в чате (удаление отключено)'}"

    # Send notification to channel
    logger.info(f"Sending notification to channel {channel_id}")
    success = await safe_send_to_channel(channel_id, formatted_message, context, 'MarkdownV2')

    if success:
        logger.info(f"Successfully sent edited message notification to channel {channel_id}")
    else:
        logger.error(f"Failed to send notification to channel {channel_id} - check bot permissions")

        # Создаем простое текстовое сообщение как последний fallback
        try:
            simple_user_name = user_data.get('first_name', 'Unknown')
            if user_data.get('last_name'):
                simple_user_name += f" {user_data['last_name']}"

            simple_username = f"@{user_data['username']}" if user_data.get('username') else "без username"

            edit_time_simple = ""
            if edited_message.edit_date:
                edit_time_simple = f"Время редактирования: {edited_message.edit_date.strftime('%d.%m.%Y %H:%M:%S')}\n"

            action_text = "Сообщение удалено из чата" if delete_success else "Сообщение оставлено в чате (удаление отключено)"
            header_text = "УДАЛЕНО" if delete_success else "ОБНАРУЖЕНО"

            final_fallback_message = f"""🔄 ОТРЕДАКТИРОВАННОЕ СООБЩЕНИЕ {header_text}

👤 ПОЛЬЗОВАТЕЛЬ:
ID: {user_data['id']}
Имя: {simple_user_name}
Username: {simple_username}
Тип: {'Бот' if user_data['is_bot'] else 'Пользователь'}

📍 ЧАТ:
Название: {chat.title or 'Неизвестный чат'}
ID: {chat.id}
Тип: {chat.type.value}

📝 СООБЩЕНИЕ:
ID: {edited_message.message_id}
{edit_time_simple}"""

            # Add media info and content only if media forwarding failed
            if not media_forward_success and has_media:
                final_fallback_message += f"""Медиа: {media_type.upper()}
"""
                if media_type == 'photo':
                    largest = media_info['sizes'][-1]
                    final_fallback_message += f"Разрешение: {largest['width']}x{largest['height']}\n"
                elif media_type == 'video' and media_info.get('duration'):
                    final_fallback_message += f"Длительность: {media_info['duration']} сек\n"
                elif media_type == 'document' and media_info.get('file_name'):
                    final_fallback_message += f"Файл: {media_info['file_name']}\n"

                final_fallback_message += f"""Пересылка медиа: Не удалось

Содержимое: {edited_text[:500]}...

⚠️ Действие: {action_text}"""
            else:
                final_fallback_message += f"""Содержимое: {edited_text[:500]}...

⚠️ Действие: {action_text}"""

            await context.bot.send_message(
                chat_id=channel_id,
                text=final_fallback_message
            )
            logger.info(f"Sent final fallback message to channel {channel_id}")
        except Exception as final_error:
            logger.error(f"Final fallback also failed for channel {channel_id}: {final_error}")
            logger.error("Check if bot is properly added to the channel and has required permissions")


async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle edited messages in group chats"""
    logger.info("handle_edited_message called")
    
    # Check if this update contains an edited message
    if not update.edited_message:
        logger.debug("No edited_message in update, skipping")
        return
    
    edited_message = update.edited_message
    
    logger.info(f"Processing edited message {edited_message.message_id} in chat {edited_message.chat.id}")
    
    chat = edited_message.chat
    user = edited_message.from_user
    
    logger.info(f"Chat type: {chat.type}, Chat ID: {chat.id}")
    logger.info(f"User: {user.id} (@{user.username if user.username else 'no_username'})")
    
    # Only process group/supergroup messages
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        logger.info(f"Ignoring edited message from non-group chat {chat.id} (type: {chat.type})")
        return
    
    # Ignore messages from bots
    if user.is_bot:
        logger.info(f"Ignoring edited message from bot {user.id}")
        return
    
    # Убираем проверку на админов - обрабатываем сообщения от всех пользователей
    # Если нужно игнорировать админов, раскомментируйте блок ниже:
    """
    # Check if user is admin in the chat
    try:
        is_admin = await is_user_admin(chat.id, user.id, context)
        logger.info(f"User {user.id} admin status: {is_admin}")
        if is_admin:
            logger.info(f"Ignoring edited message from admin {user.id} in chat {chat.id}")
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        # Продолжаем обработку, если не можем проверить статус админа
    """
    
    # Get channel for this chat
    try:
        channel_id = db.get_chat_channel(chat.id)
        logger.info(f"Channel ID for chat {chat.id}: {channel_id}")
        if not channel_id:
            logger.warning(f"No channel configured for chat {chat.id}")
            return
    except Exception as e:
        logger.error(f"Error getting channel for chat {chat.id}: {e}")
        return

    # Check if message deletion is enabled for this chat
    try:
        delete_enabled = db.get_delete_messages_setting(chat.id)
        logger.info(f"Delete messages setting for chat {chat.id}: {delete_enabled}")
    except Exception as e:
        logger.error(f"Error getting delete setting for chat {chat.id}: {e}")
        delete_enabled = True  # Default to enabled if error

    # Check maximum edit time setting for this chat
    try:
        max_edit_time = db.get_max_edit_time_setting(chat.id)
        logger.info(f"Max edit time setting for chat {chat.id}: {max_edit_time} minutes")
    except Exception as e:
        logger.error(f"Error getting max edit time setting for chat {chat.id}: {e}")
        max_edit_time = 20  # Default to 20 minutes if error

    # Check if the edit time exceeds the maximum allowed time
    if max_edit_time == 0:
        # No time limit - process all edits immediately (delete right away)
        logger.info(f"No time limit for chat {chat.id} - processing edit immediately for message {edited_message.message_id}")
        # Continue to message processing below
    elif max_edit_time > 0:
        try:
            # Calculate time difference between original message and edit
            if edited_message.date and edited_message.edit_date:
                time_diff = edited_message.edit_date - edited_message.date
                max_allowed_time = timedelta(minutes=max_edit_time)

                if time_diff <= max_allowed_time:
                    logger.info(f"Edit time within limit for message {edited_message.message_id}: "
                              f"{time_diff.total_seconds()/60:.1f} minutes vs {max_edit_time} minutes limit")
                    return  # Ignore this edit - it is within the allowed time
                else:
                    logger.info(f"Edit time exceeded limit: {time_diff.total_seconds()/60:.1f} minutes - processing deletion")
            else:
                logger.warning(f"Missing date information for message {edited_message.message_id}")
        except Exception as e:
            logger.error(f"Error checking edit time for message {edited_message.message_id}: {e}")
            # Continue processing even if time check fails

    # Get edited message text and check for media
    edited_text = edited_message.text or edited_message.caption or 'Текст недоступен'
    logger.info(f"Edited message text: {edited_text[:100]}...")

    # Check if message contains media
    has_media = False
    media_type = None
    media_info = {}

    if hasattr(edited_message, 'photo') and edited_message.photo:
        has_media = True
        media_type = 'photo'
        media_info = {
            'type': 'photo',
            'count': len(edited_message.photo),
            'sizes': [{'file_id': p.file_id, 'width': p.width, 'height': p.height} for p in edited_message.photo]
        }
    elif hasattr(edited_message, 'video') and edited_message.video:
        has_media = True
        media_type = 'video'
        media_info = {
            'type': 'video',
            'file_id': edited_message.video.file_id,
            'duration': getattr(edited_message.video, 'duration', None),
            'width': getattr(edited_message.video, 'width', None),
            'height': getattr(edited_message.video, 'height', None),
            'file_size': getattr(edited_message.video, 'file_size', None)
        }
    elif hasattr(edited_message, 'document') and edited_message.document:
        has_media = True
        media_type = 'document'
        media_info = {
            'type': 'document',
            'file_id': edited_message.document.file_id,
            'file_name': getattr(edited_message.document, 'file_name', None),
            'mime_type': getattr(edited_message.document, 'mime_type', None),
            'file_size': getattr(edited_message.document, 'file_size', None)
        }
    elif hasattr(edited_message, 'audio') and edited_message.audio:
        has_media = True
        media_type = 'audio'
        media_info = {
            'type': 'audio',
            'file_id': edited_message.audio.file_id,
            'duration': getattr(edited_message.audio, 'duration', None),
            'title': getattr(edited_message.audio, 'title', None),
            'performer': getattr(edited_message.audio, 'performer', None),
            'file_size': getattr(edited_message.audio, 'file_size', None)
        }
    elif hasattr(edited_message, 'voice') and edited_message.voice:
        has_media = True
        media_type = 'voice'
        media_info = {
            'type': 'voice',
            'file_id': edited_message.voice.file_id,
            'duration': getattr(edited_message.voice, 'duration', None),
            'file_size': getattr(edited_message.voice, 'file_size', None)
        }

    logger.info(f"Message has media: {has_media}, type: {media_type}")
    if has_media:
        logger.info(f"Media info: {media_info}")

    logger.info(f"Processing edited message from user {user.id} in chat {chat.id}")

    # Delete the edited message from group chat if enabled
    delete_success = False
    if delete_enabled:
        try:
            delete_success = await safe_delete_message(context, chat.id, edited_message.message_id)
            if delete_success:
                logger.info(f"Deleted edited message {edited_message.message_id} from chat {chat.id}")
            else:
                logger.warning(f"Failed to delete edited message {edited_message.message_id} from chat {chat.id}")
        except Exception as e:
            logger.error(f"Error deleting message: {e}")

        # Forward media to channel only if deletion is enabled
        media_forward_success = False
        if has_media:
            try:
                logger.info(f"Attempting to forward media message to channel {channel_id}")
                forwarded_msg_id = await forward_message_to_channel(
                    from_chat_id=chat.id,
                    message_id=edited_message.message_id,
                    to_chat_id=channel_id,
                    context=context
                )

                if forwarded_msg_id:
                    media_forward_success = True
                    logger.info(f"Successfully forwarded media message to channel {channel_id}, forwarded message ID: {forwarded_msg_id}")
                else:
                    logger.warning(f"Failed to forward media message to channel {channel_id}")
                    # Try to send media separately as fallback
                    if await send_media_to_channel(edited_message, channel_id, context, edited_text):
                        media_forward_success = True
                        logger.info(f"Successfully sent media via fallback method to channel {channel_id}")
            except Exception as e:
                logger.error(f"Error forwarding media message: {e}")
                # Try to send media separately as fallback
                try:
                    if await send_media_to_channel(edited_message, channel_id, context, edited_text):
                        media_forward_success = True
                        logger.info(f"Successfully sent media via fallback method to channel {channel_id}")
                except Exception as fallback_error:
                    logger.error(f"Fallback media sending also failed: {fallback_error}")

        # Send notification to channel only if deletion was successful
        await send_channel_notification(edited_message, chat, user, edited_text, has_media, media_type, media_info, media_forward_success, delete_success, channel_id, context)
    else:
        logger.info(f"Message deletion disabled for chat {chat.id}, skipping deletion and channel notification")
        # If deletion is disabled, we don't send anything to channel
        return



async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle new chat members - specifically when the bot is added to a group"""
    chat = update.effective_chat
    bot_user = context.bot.username
    
    # Check if our bot was added
    for member in update.message.new_chat_members:
        if member.username == bot_user:
            logger.info(f"Bot added to chat {chat.id} via new_chat_members event")
            
            # Try to add chat to database
            user_id = update.effective_user.id if update.effective_user else None
            success = db.add_chat(chat.id, chat.title, chat.type.value, user_id)
            
            if success:
                logger.info(f"Successfully added chat {chat.id} to database")
                
                # Send notification to admin if we have user_id
                if user_id:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"✅ Бот успешно добавлен в чат *{escape_markdown(chat.title)}*\n\n"
                                 f"🆔 ID чата: `{chat.id}`\n"
                                 f"📋 Тип: {chat.type.value}\n\n"
                                 f"Используйте команду /chats чтобы настроить бота",
                            parse_mode='MarkdownV2'
                        )
                    except Exception as e:
                        logger.error(f"Failed to send notification to user {user_id}: {e}")
            else:
                logger.error(f"Failed to add chat {chat.id} to database")
            break