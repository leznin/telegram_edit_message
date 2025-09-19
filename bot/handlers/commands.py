"""
Command handlers for the Telegram bot
Handles /start and /chats commands in private messages
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatType
import logging

from bot.database.database import db
from bot.utils.helpers import format_chat_title, is_bot_admin, escape_markdown_safe

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Only respond to private messages
    if chat.type != ChatType.PRIVATE:
        return
    
    welcome_text = f"👋 Привет, {user.first_name}!\n\n🤖 Мониторю редактируемые сообщения в чатах"

    # Create inline keyboard with action buttons
    keyboard = [
        [InlineKeyboardButton("⚙️ Настроить чаты", callback_data="main_menu")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
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

    # Check user role for moderator visibility
    is_admin = db.is_chat_admin(chat_id, user.id)
    is_moderator = db.is_moderator(chat_id, user.id)

    # Add moderator button only for chat admins
    if is_admin:
        moderators = db.get_chat_moderators(chat_id)
        moderator_text = f"👥 Модераторы: {len(moderators)} чел."
        keyboard.append([InlineKeyboardButton(moderator_text, callback_data=f"manage_moderators_{chat_id}")])
    elif is_moderator or is_admin:
        # Show moderator status for moderators and admins (since admins have same privileges)
        if is_admin:
            keyboard.append([InlineKeyboardButton("👨‍💼 Вы администратор", callback_data="moderator_info")])
        else:
            keyboard.append([InlineKeyboardButton("👨‍💼 Вы модератор", callback_data="moderator_info")])

    # Back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад к списку чатов", callback_data="back_to_chats")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    status_text = f"📺 Канал: {'настроен' if channel_id else 'не настроен'}\n"
    status_text += f"🗑️ Удаление: {'включено' if delete_enabled else 'отключено'}\n"
    if max_edit_time == 0:
        status_text += "⏱️ Удаление: сразу при редактировании"
    else:
        status_text += f"⏱️ Лимит редактирования: {max_edit_time} мин"

    # Add moderator/admin status info
    if is_moderator:
        status_text += "\n👨‍💼 Вы имеете права модератора - редактирование без ограничений"
    elif is_admin:
        status_text += "\n👨‍💼 Вы имеете права администратора - редактирование без ограничений"
    else:
        status_text += "\n👤 Обычный пользователь"

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

    logger.info(f"handle_channel_setup called for user {user.id}")

    # Check if user is in channel setup mode
    if not context.user_data.get('waiting_for_channel'):
        logger.info(f"User {user.id} not in channel setup mode")
        return

    # Don't interfere with moderator forward mode
    if context.user_data.get('waiting_for_moderator_forward'):
        return

    # Check if message is forwarded from a channel
    # Support both old and new forward formats
    forward_chat = None
    if hasattr(message, 'forward_origin') and message.forward_origin:
        # New format (forward_origin)
        if hasattr(message.forward_origin, 'chat') and message.forward_origin.chat:
            forward_chat = message.forward_origin.chat
    elif hasattr(message, 'forward_from_chat'):
        # Old format (forward_from_chat)
        forward_chat = message.forward_from_chat

    if not forward_chat or forward_chat.type != ChatType.CHANNEL:
        await message.reply_text(
            "❌ Пожалуйста, перешлите сообщение именно из канала, а не из чата."
        )
        return
    
    channel_id = forward_chat.id
    channel_title = forward_chat.title
    selected_chat_id = context.user_data.get('selected_chat_id')
    
    # Check if bot is admin in the channel
    if not await is_bot_admin(channel_id, context):
        await message.reply_text(
            f"❌ Я не являюсь администратором в канале \"{channel_title}\".\n\n"
            f"Добавьте меня как администратора и попробуйте снова."
        )
        return
    
    # Save chat-channel binding to database
    success = await db.bind_chat_channel_async(selected_chat_id, channel_id, user.id)
    
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


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle help callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    help_text = (
        "📋 **Как настроить бота:**\n\n"
        "1. Добавьте меня в групповой чат как администратора\n"
        "2. Добавьте меня в канал как администратора\n"
        "3. Нажмите \"⚙️ Настроить чаты\" для связи чат→канал\n\n"
        "❗ **Важно:** Я должен быть администратором везде!"
    )

    # Create keyboard with back button
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"Help shown to user {user.id}")


async def manage_moderators_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle manage moderators callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Check if user is admin of this chat
    if not db.is_chat_admin(chat_id, user.id):
        await query.edit_message_text(
            "❌ У вас нет прав для управления модераторами этого чата."
        )
        return

    # Get current moderators
    moderators = db.get_chat_moderators(chat_id)

    # Create keyboard
    keyboard = []

    # List current moderators
    if moderators:
        for moderator in moderators:
            moderator_id = moderator['moderator_user_id']
            moderator_username = moderator.get('moderator_username')
            moderator_name = moderator.get('moderator_name')

            # Create display name
            display_parts = []

            # Check if moderator_name already contains username in parentheses
            name_has_username = False
            if moderator_name and moderator_username:
                # Check if username is already in the name (e.g., "Qwerty (@s3s3s)")
                name_has_username = f"(@{moderator_username})" in moderator_name

            if moderator_name:
                display_parts.append(moderator_name)

            # Only add separate username if it's not already in the name
            if moderator_username and not name_has_username:
                display_parts.append(f"@{moderator_username}")

            if not display_parts:
                display_parts.append(f"ID: {moderator_id}")

            display_name = " | ".join(display_parts)
            if len(display_name) > 30:  # Truncate if too long
                display_name = display_name[:27] + "..."

            keyboard.append([
                InlineKeyboardButton(
                    f"👤 {display_name}",
                    callback_data=f"remove_moderator_{chat_id}_{moderator_id}"
                )
            ])

    # Add new moderator button
    keyboard.append([InlineKeyboardButton("➕ Добавить модератора", callback_data=f"add_moderator_options_{chat_id}")])

    # Back button
    keyboard.append([InlineKeyboardButton("⬅️ Назад к настройкам", callback_data=f"setup_chat_{chat_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if moderators:
        moderator_list = []
        for mod in moderators:
            moderator_id = mod['moderator_user_id']
            moderator_username = mod.get('moderator_username')
            moderator_name = mod.get('moderator_name')

            # Create display info
            display_parts = []

            # Check if moderator_name already contains username in parentheses
            name_has_username = False
            if moderator_name and moderator_username:
                # Check if username is already in the name (e.g., "Qwerty (@s3s3s)")
                name_has_username = f"(@{moderator_username})" in moderator_name

            if moderator_name:
                display_parts.append(f"Имя: {escape_markdown_safe(moderator_name)}")

            # Only add separate username field if it's not already in the name
            if moderator_username and not name_has_username:
                display_parts.append(f"Username: @{escape_markdown_safe(moderator_username)}")

            display_parts.append(f"ID: `{moderator_id}`")

            moderator_list.append("• " + " | ".join(display_parts))

        text = f"👥 **Управление модераторами**\n\nТекущие модераторы:\n" + "\n".join(moderator_list) + "\n\nВыберите действие:"
    else:
        text = f"👥 **Управление модераторами**\n\nВ этом чате пока нет модераторов.\n\nВыберите действие:"

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} opened moderator management for chat {chat_id}")


async def add_moderator_options_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle add moderator options callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Check if user is admin of this chat
    if not db.is_chat_admin(chat_id, user.id):
        await query.edit_message_text(
            "❌ У вас нет прав для добавления модераторов."
        )
        return

    # Create keyboard with two options
    keyboard = [
        [InlineKeyboardButton("🔢 Ввести ID вручную", callback_data=f"add_moderator_manual_{chat_id}")],
        [InlineKeyboardButton("📨 Переслать сообщение", callback_data=f"add_moderator_forward_{chat_id}")],
        [InlineKeyboardButton("⬅️ Назад к управлению", callback_data=f"manage_moderators_{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"👤 **Добавление модератора**\n\n"
        f"Выберите способ добавления пользователя как модератора:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} opened moderator addition options for chat {chat_id}")


async def remove_moderator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle remove moderator callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id and moderator_id from callback data
    parts = query.data.split('_')
    chat_id = int(parts[2])
    moderator_id = int(parts[3])

    # Check if user is admin of this chat
    if not db.is_chat_admin(chat_id, user.id):
        await query.edit_message_text(
            "❌ У вас нет прав для удаления модераторов."
        )
        return

    # Create confirmation keyboard
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_remove_moderator_{chat_id}_{moderator_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"manage_moderators_{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"⚠️ **Подтверждение удаления**\n\n"
        f"Вы действительно хотите удалить пользователя `{moderator_id}` из списка модераторов?\n\n"
        f"Этот пользователь потеряет право редактировать сообщения без ограничений.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} requested to remove moderator {moderator_id} from chat {chat_id}")


async def confirm_remove_moderator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle confirm remove moderator callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id and moderator_id from callback data
    parts = query.data.split('_')
    chat_id = int(parts[3])
    moderator_id = int(parts[4])

    # Check if user is admin of this chat
    if not db.is_chat_admin(chat_id, user.id):
        await query.edit_message_text(
            "❌ У вас нет прав для удаления модераторов."
        )
        return

    # Remove moderator
    success = db.remove_moderator(chat_id, moderator_id)

    if success:
        # Create keyboard with back button
        keyboard = [[InlineKeyboardButton("⬅️ Назад к управлению", callback_data=f"manage_moderators_{chat_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ **Модератор удален!**\n\n"
            f"Пользователь `{moderator_id}` больше не является модератором этого чата.\n\n"
            f"Он потерял право редактировать сообщения без ограничений.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.info(f"User {user.id} successfully removed moderator {moderator_id} from chat {chat_id}")
    else:
        await query.edit_message_text(
            "❌ Произошла ошибка при удалении модератора. Попробуйте позже."
        )
        logger.error(f"Failed to remove moderator {moderator_id} from chat {chat_id} by user {user.id}")


# Handler for moderator ID input
async def handle_moderator_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle moderator ID input from user"""
    user = update.effective_user
    message = update.message

    # Check if user is waiting for moderator ID input
    if not context.user_data.get('waiting_for_moderator_id'):
        return

    chat_id = context.user_data['waiting_for_moderator_id']

    try:
        # Parse the input
        moderator_id = int(message.text.strip())

        # Validate ID (basic check)
        if moderator_id <= 0:
            raise ValueError("Invalid user ID")

        # Check if user is admin of this chat
        if not db.is_chat_admin(chat_id, user.id):
            await message.reply_text(
                "❌ У вас нет прав для добавления модераторов."
            )
            return

        # Check if user is already a moderator
        if db.is_moderator(chat_id, moderator_id):
            await message.reply_text(
                f"❌ Пользователь `{moderator_id}` уже является модератором этого чата.",
                parse_mode='Markdown'
            )
            return

        # Add moderator (username and name will be None for manual ID input)
        success = db.add_moderator(chat_id, moderator_id, user.id, None, None)

        if success:
            # Create keyboard with back button to moderator management
            keyboard = [[InlineKeyboardButton("⬅️ Назад к управлению модераторами", callback_data=f"manage_moderators_{chat_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await message.reply_text(
                f"✅ **Модератор добавлен!**\n\n"
                f"Пользователь `{moderator_id}` теперь является модератором этого чата.\n\n"
                f"Он может редактировать сообщения без ограничений.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            logger.info(f"User {user.id} successfully added moderator {moderator_id} to chat {chat_id}")
        else:
            await message.reply_text(
                "❌ Произошла ошибка при добавлении модератора. Попробуйте позже."
            )
            logger.error(f"Failed to add moderator {moderator_id} to chat {chat_id} by user {user.id}")

    except ValueError:
        await message.reply_text(
            "❌ Пожалуйста, введите корректный ID пользователя (число).\n\n"
            "Попробуйте еще раз или используйте /chats для возврата к меню."
        )
        return

    # Clear user context
    context.user_data.clear()


async def add_moderator_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle manual moderator ID input callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Check if user is admin of this chat
    if not db.is_chat_admin(chat_id, user.id):
        await query.edit_message_text(
            "❌ У вас нет прав для добавления модераторов."
        )
        return

    # Store chat_id in user context
    context.user_data['waiting_for_moderator_id'] = chat_id

    await query.edit_message_text(
        f"👤 **Добавление модератора**\n\n"
        f"Отправьте ID пользователя, которого хотите добавить как модератора.\n\n"
        f"ID можно узнать через бота @userinfobot или посмотреть в логах бота.",
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} started manual moderator addition for chat {chat_id}")


async def add_moderator_forward_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forward message for moderator addition callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Extract chat_id from callback data
    chat_id = int(query.data.split('_')[-1])

    # Check if user is admin of this chat
    if not db.is_chat_admin(chat_id, user.id):
        await query.edit_message_text(
            "❌ У вас нет прав для добавления модераторов."
        )
        return

    # Store chat_id in user context
    context.user_data['waiting_for_moderator_forward'] = chat_id

    await query.edit_message_text(
        f"📨 **Добавление модератора через пересылку**\n\n"
        f"Перешлите любое сообщение от пользователя, которого хотите добавить как модератора.\n\n"
        f"❗ **Важно:** Сообщение должно быть переслано из личного чата или группы, а не из канала.",
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} started forward moderator addition for chat {chat_id}")


async def handle_moderator_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forwarded message for moderator addition"""
    user = update.effective_user
    message = update.message

    logger.info(f"handle_moderator_forward called for user {user.id}")

    # Check if user is waiting for moderator forward
    if not context.user_data.get('waiting_for_moderator_forward'):
        logger.info(f"User {user.id} not waiting for moderator forward")
        return

    # Don't interfere with channel setup mode
    if context.user_data.get('waiting_for_channel'):
        return

    chat_id = context.user_data['waiting_for_moderator_forward']

    # Check if user is admin of this chat
    if not db.is_chat_admin(chat_id, user.id):
        await message.reply_text(
            "❌ У вас нет прав для добавления модераторов."
        )
        return

    # Check if message is forwarded and get user info
    moderator_user = None

    # Try new format first (forward_origin.sender_user)
    if hasattr(message, 'forward_origin') and message.forward_origin:
        if hasattr(message.forward_origin, 'sender_user') and message.forward_origin.sender_user:
            moderator_user = message.forward_origin.sender_user
            logger.info(f"Using forward_origin.sender_user format for user {moderator_user.id}")

    # Fallback to old format (forward_from)
    if not moderator_user and hasattr(message, 'forward_from') and message.forward_from:
        moderator_user = message.forward_from
        logger.info(f"Using forward_from format for user {moderator_user.id}")

    # If still no user info, error
    if not moderator_user:
        logger.warning(f"No user info found in forwarded message. forward_origin: {getattr(message, 'forward_origin', None)}, forward_from: {getattr(message, 'forward_from', None)}")
        await message.reply_text(
            "❌ Не удалось получить информацию о пользователе из пересланного сообщения.\n\n"
            "Убедитесь, что пересылаете сообщение от пользователя (не от канала или бота).\n"
            "Попробуйте другой способ или введите ID вручную."
        )
        return

    # Get user ID from forwarded message
    try:
        moderator_id = moderator_user.id
        moderator_name = moderator_user.first_name or "Пользователь"

        if hasattr(moderator_user, 'last_name') and moderator_user.last_name:
            moderator_name += f" {moderator_user.last_name}"

        if hasattr(moderator_user, 'username') and moderator_user.username:
            moderator_name += f" (@{moderator_user.username})"

        logger.info(f"Extracted moderator info: ID={moderator_id}, Name='{moderator_name}'")

    except Exception as e:
        logger.error(f"Error extracting user info from moderator_user object: {e}")
        logger.error(f"moderator_user object: {moderator_user}")
        await message.reply_text(
            "❌ Произошла ошибка при обработке данных пользователя.\n\n"
            "Попробуйте ввести ID пользователя вручную."
        )
        return

    # Check if user is already a moderator
    is_already_moderator = await db.is_moderator_async(chat_id, moderator_id)
    if is_already_moderator:
        await message.reply_text(
            f"❌ Пользователь {escape_markdown_safe(moderator_name)} (ID: `{moderator_id}`) уже является модератором этого чата.",
            parse_mode='Markdown'
        )
        return

    # Add moderator with username and name
    success = db.add_moderator(chat_id, moderator_id, user.id, moderator_user.username, moderator_name)

    if success:
        # Create keyboard with back button to moderator management
        keyboard = [[InlineKeyboardButton("⬅️ Назад к управлению модераторами", callback_data=f"manage_moderators_{chat_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            f"✅ **Модератор добавлен!**\n\n"
            f"👤 Пользователь: {escape_markdown_safe(moderator_name)}\n"
            f"🆔 ID: `{moderator_id}`\n\n"
            f"Теперь этот пользователь может редактировать сообщения без ограничений.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info(f"User {user.id} successfully added moderator {moderator_id} via forward for chat {chat_id}")
    else:
        await message.reply_text(
            "❌ Произошла ошибка при добавлении модератора. Попробуйте позже."
        )
        logger.error(f"Failed to add moderator {moderator_id} via forward for chat {chat_id} by user {user.id}")

    # Clear user context
    context.user_data.clear()


async def moderator_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle moderator info callback"""
    query = update.callback_query
    user = query.from_user

    await query.answer()

    # Find chats where user is moderator
    moderated_chats = db.get_user_moderated_chats(user.id)

    # Also check for admin chats
    admin_chats = db.get_user_chats(user.id)

    if moderated_chats or admin_chats:
        text = f"👨‍💼 **Информация о правах**\n\n"

        if moderated_chats:
            chat_list = []
            for chat in moderated_chats:
                chat_title = chat['chat_title']
                chat_id = chat['chat_id']
                moderator_username = chat.get('moderator_username')
                moderator_name = chat.get('moderator_name')

                # Create display info
                display_parts = [f"{chat_title} (ID: `{chat_id}`)"]

                # Check if moderator_name already contains username in parentheses
                name_has_username = False
                if moderator_name and moderator_username:
                    # Check if username is already in the name (e.g., "Qwerty (@s3s3s)")
                    name_has_username = f"(@{moderator_username})" in moderator_name

                if moderator_name:
                    display_parts.append(f"Ваш ник: {escape_markdown_safe(moderator_name)}")

                # Only add separate username field if it's not already in the name
                if moderator_username and not name_has_username:
                    display_parts.append(f"Ваш username: @{escape_markdown_safe(moderator_username)}")

                chat_list.append("• " + " | ".join(display_parts))

            text += f"**Вы модератор в следующих чатах:**\n" + "\n".join(chat_list) + "\n\n"

        if admin_chats:
            admin_chat_list = "\n".join([f"• {chat['chat_title']} (ID: `{chat['chat_id']}`)" for chat in admin_chats])
            text += f"**Вы администратор в следующих чатах:**\n{admin_chat_list}\n\n"

        text += f"**Ваши права:**\n" \
                f"✅ Неограниченное редактирование сообщений\n" \
                f"✅ Ваши отредактированные сообщения не удаляются\n" \
                f"✅ Ваши изменения не пересылаются в канал\n\n" \
                f"Вы можете редактировать сообщения в любое время без последствий."
    else:
        text = f"👨‍💼 **Информация о правах**\n\n" \
               f"У вас нет активных прав модератора или администратора ни в одном чате.\n\n" \
               f"Обратитесь к администратору чата для получения прав."

    # Create keyboard with back button (we need to find a way to get back to the original chat)
    # For now, just go to main menu
    keyboard = [[InlineKeyboardButton("🏠 На главную", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"User {user.id} viewed moderator information")


def format_chat_title_from_data(chat_data: dict) -> str:
    """Format chat title from database data"""
    title = chat_data.get('chat_title', f"Chat {chat_data['chat_id']}")
    return title[:50] + "..." if len(title) > 50 else title