"""
Command handlers for the Telegram bot
Handles /start and /chats commands in private messages
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatType
import logging

from bot.database.database import db
from bot.utils.helpers import format_chat_title, is_bot_admin

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Only respond to private messages
    if chat.type != ChatType.PRIVATE:
        return
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🤖 Я бот для мониторинга редактируемых сообщений в групповых чатах.\n\n"
        "📋 **Что я умею:**\n"
        "• Отслеживаю редактирование сообщений в групповых чатах\n"
        "• Пересылаю оригинал и отредактированную версию в указанный канал\n"
        "• Удаляю отредактированные сообщения из группы (можно отключить)\n\n"
        "⚙️ **Как настроить:**\n"
        "1. Добавьте меня в групповой чат как администратора\n"
        "2. Добавьте меня в канал как администратора\n"
        "3. Используйте команду /chats для настройки связи чат→канал\n"
        "4. В меню настроек можно включить/выключить удаление сообщений\n\n"
        "❗ **Важно:** Я должен быть администратором и в чате, и в канале!\n\n"
        "🔧 Используйте /chats для настройки"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown'
    )
    logger.info(f"Start command from user {user.id}")


async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /chats command"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Only respond to private messages
    if chat.type != ChatType.PRIVATE:
        return
    
    # Get user's chats from database
    user_chats = db.get_user_chats(user.id)
    
    if not user_chats:
        await update.message.reply_text(
            "📭 У вас пока нет активных чатов.\n\n"
            "Добавьте меня в групповой чат как администратора, "
            "и я автоматически добавлю его в список."
        )
        return
    
    # Create inline keyboard with chat buttons
    keyboard = []
    for chat_data in user_chats:
        chat_title = format_chat_title_from_data(chat_data)
        callback_data = f"setup_chat_{chat_data['chat_id']}"
        keyboard.append([InlineKeyboardButton(chat_title, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📋 **Ваши чаты где я администратор:**\n\n"
        "Выберите чат для настройки канала пересылки:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"Chats command from user {user.id}, found {len(user_chats)} chats")


async def setup_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle chat setup callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Store selected chat in user context
    context.user_data['selected_chat_id'] = chat_id

    # Get current settings for this chat
    delete_enabled = db.get_delete_messages_setting(chat_id)
    channel_id = db.get_chat_channel(chat_id)
    max_edit_time = db.get_max_edit_time_setting(chat_id)

    # Create menu with options
    keyboard = []

    # Channel setup button
    if channel_id:
        keyboard.append([InlineKeyboardButton("🔄 Изменить канал пересылки", callback_data=f"setup_channel_{chat_id}")])
    else:
        keyboard.append([InlineKeyboardButton("📺 Настроить канал пересылки", callback_data=f"setup_channel_{chat_id}")])

    # Toggle deletion button
    toggle_text = "🗑️ Отключить удаление сообщений" if delete_enabled else "✅ Включить удаление сообщений"
    keyboard.append([InlineKeyboardButton(toggle_text, callback_data=f"toggle_delete_{chat_id}")])

    # Edit time button
    time_text = f"⏱️ Время редактирования: {max_edit_time} мин" if max_edit_time > 0 else "⏱️ Время редактирования: без ограничений"
    keyboard.append([InlineKeyboardButton(time_text, callback_data=f"set_edit_time_{chat_id}")])

    # Back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад к списку чатов", callback_data="back_to_chats")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    status_text = f"📺 Канал: {'настроен' if channel_id else 'не настроен'}\n"
    status_text += f"🗑️ Удаление: {'включено' if delete_enabled else 'отключено'}\n"
    if max_edit_time == 0:
        status_text += "⏱️ Удаление: сразу при редактировании"
    else:
        status_text += f"⏱️ Лимит редактирования: {max_edit_time} мин"

    await query.edit_message_text(
        f"⚙️ **Настройки чата**\n\n"
        f"{status_text}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} opened settings for chat {chat_id}")


async def handle_channel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle channel setup from forwarded message"""
    user = update.effective_user
    message = update.message
    
    # Check if user is in channel setup mode
    if not context.user_data.get('waiting_for_channel'):
        return
    
    # Check if message is forwarded from a channel
    if not message.forward_from_chat or message.forward_from_chat.type != ChatType.CHANNEL:
        await message.reply_text(
            "❌ Пожалуйста, перешлите сообщение именно из канала, а не из чата."
        )
        return
    
    channel_id = message.forward_from_chat.id
    channel_title = message.forward_from_chat.title
    selected_chat_id = context.user_data.get('selected_chat_id')
    
    # Check if bot is admin in the channel
    if not await is_bot_admin(channel_id, context):
        await message.reply_text(
            f"❌ Я не являюсь администратором в канале \"{channel_title}\".\n\n"
            f"Добавьте меня как администратора и попробуйте снова."
        )
        return
    
    # Save chat-channel binding to database
    success = db.bind_chat_channel(selected_chat_id, channel_id, user.id)
    
    if success:
        # Create keyboard with "main menu" button
        keyboard = [[InlineKeyboardButton("🏠 На главную", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            f"✅ **Настройка завершена!**\n\n"
            f"📺 Канал: {channel_title}\n"
            f"🔗 Связан с выбранным чатом\n\n"
            f"Теперь все отредактированные сообщения будут пересылаться в этот канал.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info(f"Successfully bound chat {selected_chat_id} to channel {channel_id} for user {user.id}")
    else:
        await message.reply_text(
            "❌ Произошла ошибка при сохранении настроек. Попробуйте позже."
        )
        logger.error(f"Failed to bind chat {selected_chat_id} to channel {channel_id} for user {user.id}")
    
    # Clear user context
    context.user_data.clear()


async def setup_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle channel setup callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Store selected chat in user context
    context.user_data['selected_chat_id'] = chat_id
    context.user_data['waiting_for_channel'] = True

    await query.edit_message_text(
        f"✅ Чат выбран!\n\n"
        f"📺 Теперь перешлите любое сообщение из канала, куда я должен пересылать "
        f"отредактированные сообщения.\n\n"
        f"❗ **Важно:** Я должен быть администратором в этом канале!",
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} started channel setup for chat {chat_id}")


async def toggle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle toggle delete messages callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Get current setting
    current_setting = db.get_delete_messages_setting(chat_id)
    new_setting = not current_setting

    # Update setting
    success = db.set_delete_messages_setting(chat_id, new_setting)

    if success:
        status = "включено" if new_setting else "отключено"
        action = "включено" if new_setting else "отключено"

        # Create keyboard with "main menu" button
        keyboard = [[InlineKeyboardButton("🏠 На главную", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ **Настройка обновлена!**\n\n"
            f"🗑️ Удаление отредактированных сообщений: {status}\n\n"
            f"Используйте /chats чтобы вернуться к настройкам.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info(f"User {user.id} {'enabled' if new_setting else 'disabled'} message deletion for chat {chat_id}")
    else:
        await query.edit_message_text(
            "❌ Произошла ошибка при обновлении настроек. Попробуйте позже."
        )
        logger.error(f"Failed to toggle delete setting for chat {chat_id} by user {user.id}")


async def back_to_chats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle back to chats list callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Clear user context
    context.user_data.clear()

    # Get user's chats from database
    user_chats = db.get_user_chats(user.id)

    if not user_chats:
        await query.edit_message_text(
            "📭 У вас пока нет активных чатов.\n\n"
            "Добавьте меня в групповой чат как администратора, "
            "и я автоматически добавлю его в список."
        )
        return

    # Create inline keyboard with chat buttons
    keyboard = []
    for chat_data in user_chats:
        chat_title = format_chat_title_from_data(chat_data)
        callback_data = f"setup_chat_{chat_data['chat_id']}"
        keyboard.append([InlineKeyboardButton(chat_title, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "📋 **Ваши чаты где я администратор:**\n\n"
        "Выберите чат для настройки:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} returned to chats list")


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle main menu callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Clear user context
    context.user_data.clear()

    # Get user's chats from database
    user_chats = db.get_user_chats(user.id)

    if not user_chats:
        await query.edit_message_text(
            "📭 У вас пока нет активных чатов.\n\n"
            "Добавьте меня в групповой чат как администратора, "
            "и я автоматически добавлю его в список."
        )
        return

    # Create inline keyboard with chat buttons
    keyboard = []
    for chat_data in user_chats:
        chat_title = format_chat_title_from_data(chat_data)
        callback_data = f"setup_chat_{chat_data['chat_id']}"
        keyboard.append([InlineKeyboardButton(chat_title, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "📋 **Ваши чаты где я администратор:**\n\n"
        "Выберите чат для настройки:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} returned to main menu")


async def set_edit_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle set edit time callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Get current setting
    current_time = db.get_max_edit_time_setting(chat_id)

    # Create inline keyboard with time options
    keyboard = []

    # Common time options
    time_options = [
        (0, "Без ограничений"),
        (1, "1 минута"),
        (5, "5 минут"),
        (10, "10 минут"),
        (15, "15 минут"),
        (20, "20 минут")
    ]

    for minutes, label in time_options:
        button_text = f"✅ {label}" if minutes == current_time else label
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"set_time_{chat_id}_{minutes}")])

    # Custom time input option
    keyboard.append([InlineKeyboardButton("⌨️ Ввести вручную", callback_data=f"custom_time_{chat_id}")])

    # Back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад к настройкам", callback_data=f"setup_chat_{chat_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"⏱️ **Настройка времени редактирования**\n\n"
        f"Текущее значение: {current_time} мин\n\n"
        f"Выберите время для контроля редактирования сообщений "
        f"(от 0 до 20 минут).\n\n"
        f"• 0 минут = удалять СРАЗУ при любом редактировании\n"
        f"• 1-20 минут = удалять только если редактирование произошло ПОСЛЕ этого времени\n"
        f"• В пределах времени редактирование разрешено, сообщение остается",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} opened edit time settings for chat {chat_id}")


async def set_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle setting specific edit time"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id and minutes from callback data
    parts = query.data.split('_')
    chat_id = int(parts[2])
    minutes = int(parts[3])

    # Set the new time limit
    success = db.set_max_edit_time_setting(chat_id, minutes)

    if success:
        time_text = f"{minutes} мин" if minutes > 0 else "без ограничений"

        # Create keyboard with "back to settings" button
        keyboard = [[InlineKeyboardButton("⬅️ Назад к настройкам", callback_data=f"setup_chat_{chat_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ **Настройка обновлена!**\n\n"
            f"⏱️ Максимальное время редактирования: {time_text}\n\n"
            f"Используйте /chats чтобы вернуться к настройкам.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info(f"User {user.id} set edit time limit for chat {chat_id} to {minutes} minutes")
    else:
        await query.edit_message_text(
            "❌ Произошла ошибка при обновлении настроек. Попробуйте позже."
        )
        logger.error(f"Failed to set edit time limit for chat {chat_id} by user {user.id}")


async def custom_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom time input callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Store chat_id in user context
    context.user_data['waiting_for_custom_time'] = chat_id

    await query.edit_message_text(
        f"⌨️ **Ввод времени вручную**\n\n"
        f"Введите число от 0 до 20 (минуты):\n\n"
        f"• 0 = без ограничений\n"
        f"• Максимум 20 минут\n\n"
        f"Отправьте число в ответном сообщении:",
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} started custom time input for chat {chat_id}")


async def handle_custom_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom time input from user"""
    user = update.effective_user
    message = update.message

    # Check if user is waiting for custom time input
    if not context.user_data.get('waiting_for_custom_time'):
        return

    chat_id = context.user_data['waiting_for_custom_time']

    try:
        # Parse the input
        minutes = int(message.text.strip())

        # Validate range
        if minutes < 0 or minutes > 20:
            raise ValueError("Time out of range")

        # Set the time limit
        success = db.set_max_edit_time_setting(chat_id, minutes)

        if success:
            time_text = f"{minutes} мин" if minutes > 0 else "без ограничений"

            await message.reply_text(
                f"✅ **Настройка обновлена!**\n\n"
                f"⏱️ Максимальное время редактирования: {time_text}\n\n"
                f"Используйте /chats чтобы вернуться к настройкам.",
                parse_mode='Markdown'
            )
            logger.info(f"User {user.id} set custom edit time limit for chat {chat_id} to {minutes} minutes")
        else:
            await message.reply_text(
                "❌ Произошла ошибка при сохранении настроек. Попробуйте позже."
            )
            logger.error(f"Failed to save custom edit time for chat {chat_id} by user {user.id}")

    except ValueError:
        await message.reply_text(
            "❌ Пожалуйста, введите число от 0 до 20.\n\n"
            "Попробуйте еще раз или используйте /chats для возврата к меню."
        )
        return

    # Clear user context
    context.user_data.clear()


def format_chat_title_from_data(chat_data: dict) -> str:
    """Format chat title from database data"""
    title = chat_data.get('chat_title', f"Chat {chat_data['chat_id']}")
    return title[:50] + "..." if len(title) > 50 else title