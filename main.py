"""
Main entry point for the Telegram bot
Initializes bot, registers handlers, and starts webhook server
"""

import sys
import signal
import asyncio
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, ContextTypes
import uvicorn
import logging
import json

# Import bot modules
from bot.utils.logger import setup_logging
from bot.utils.config import Config
from bot.handlers.commands import (
    start_command,
    chats_command,
    setup_chat_callback,
    handle_channel_setup,
    setup_channel_callback,
    toggle_delete_callback,
    back_to_chats_callback,
    main_menu_callback,
    set_edit_time_callback,
    set_time_callback,
    custom_time_callback,
    handle_custom_time_input,
    help_callback,
    manage_moderators_callback,
    add_moderator_options_callback,
    add_moderator_manual_callback,
    add_moderator_forward_callback,
    remove_moderator_callback,
    confirm_remove_moderator_callback,
    handle_moderator_id_input,
    handle_moderator_forward,
    moderator_info_callback
)
from bot.handlers.messages import handle_edited_message, handle_new_chat_members
from bot.handlers.status import handle_my_chat_member

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class with webhook support"""
    
    def __init__(self):
        """Initialize the bot"""
        # Validate configuration
        Config.validate()
        
        # Create application without updater for webhook mode
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).updater(None).build()
        
        # Register handlers
        self._register_handlers()
        
        # Create FastAPI app
        self.app = FastAPI(title="Telegram Bot Webhook")
        self._setup_webhook_routes()
        
        logger.info("Bot initialized successfully")
    
    def _register_handlers(self):
        """Register all bot handlers"""
        from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters

        # Use built-in FORWARDED filter - it should support both old and new formats
        forwarded_messages = filters.FORWARDED
        
        # Command handlers (private chats only)
        self.application.add_handler(
            CommandHandler("start", start_command, filters.ChatType.PRIVATE)
        )
        self.application.add_handler(
            CommandHandler("chats", chats_command, filters.ChatType.PRIVATE)
        )
        
        # Callback query handlers
        self.application.add_handler(
            CallbackQueryHandler(setup_chat_callback, pattern="^setup_chat_")
        )
        self.application.add_handler(
            CallbackQueryHandler(setup_channel_callback, pattern="^setup_channel_")
        )
        self.application.add_handler(
            CallbackQueryHandler(toggle_delete_callback, pattern="^toggle_delete_")
        )
        self.application.add_handler(
            CallbackQueryHandler(back_to_chats_callback, pattern="^back_to_chats$")
        )
        self.application.add_handler(
            CallbackQueryHandler(main_menu_callback, pattern="^main_menu$")
        )
        self.application.add_handler(
            CallbackQueryHandler(help_callback, pattern="^help$")
        )
        self.application.add_handler(
            CallbackQueryHandler(set_edit_time_callback, pattern="^set_edit_time_")
        )
        self.application.add_handler(
            CallbackQueryHandler(set_time_callback, pattern="^set_time_")
        )
        self.application.add_handler(
            CallbackQueryHandler(custom_time_callback, pattern="^custom_time_")
        )
        self.application.add_handler(
            CallbackQueryHandler(manage_moderators_callback, pattern="^manage_moderators_")
        )
        self.application.add_handler(
            CallbackQueryHandler(add_moderator_options_callback, pattern="^add_moderator_options_")
        )
        self.application.add_handler(
            CallbackQueryHandler(add_moderator_manual_callback, pattern="^add_moderator_manual_")
        )
        self.application.add_handler(
            CallbackQueryHandler(add_moderator_forward_callback, pattern="^add_moderator_forward_")
        )
        self.application.add_handler(
            CallbackQueryHandler(remove_moderator_callback, pattern="^remove_moderator_")
        )
        self.application.add_handler(
            CallbackQueryHandler(confirm_remove_moderator_callback, pattern="^confirm_remove_moderator_")
        )
        self.application.add_handler(
            CallbackQueryHandler(moderator_info_callback, pattern="^moderator_info$")
        )

        # Message handler for channel setup (private chats, forwarded messages)
        # IMPORTANT: This must be registered BEFORE moderator forward handler
        self.application.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & forwarded_messages,
                handle_channel_setup
            )
        )

        # Message handler for moderator forward (private chats, forwarded messages for moderator addition)
        self.application.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & forwarded_messages,
                handle_moderator_forward
            )
        )

        # Message handler for custom time input (private chats, text messages)
        self.application.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & filters.TEXT & (~forwarded_messages),
                handle_custom_time_input
            )
        )

        # Message handler for moderator ID input (private chats, text messages)
        self.application.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & filters.TEXT & (~forwarded_messages),
                handle_moderator_id_input
            )
        )
        
        # Обработчик для edited_message (webhook mode)
        # Создаем кастомный обработчик для edited_message в webhook режиме
        from telegram.ext import BaseHandler
        
        class EditedMessageHandler(BaseHandler):
            """Custom handler for edited messages in webhook mode"""
            
            def __init__(self):
                # В новых версиях BaseHandler требует callback
                super().__init__(handle_edited_message)
            
            def check_update(self, update):
                """Check if this update contains an edited message"""
                return update.edited_message is not None
        
        # Добавляем обработчик для edited_message
        self.application.add_handler(EditedMessageHandler())
        
        # Bot status handlers
        self.application.add_handler(
            MessageHandler(
                filters.StatusUpdate.NEW_CHAT_MEMBERS,
                handle_new_chat_members
            )
        )
        # My chat member handler (preferred for bot status changes)
        from telegram.ext import ChatMemberHandler
        self.application.add_handler(
            ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
        )
        
        logger.info("All handlers registered")
    
    def _setup_webhook_routes(self):
        """Setup webhook routes"""
        
        @self.app.post("/webhook")
        async def webhook_handler(request: Request):
            """Handle incoming webhook updates"""
            try:
                # Get request body
                body = await request.body()
                
                # Parse JSON
                try:
                    data = json.loads(body.decode('utf-8'))
                    logger.debug(f"Received webhook data: {data}")
                except json.JSONDecodeError:
                    logger.error("Failed to parse webhook JSON")
                    raise HTTPException(status_code=400, detail="Invalid JSON")
                
                # Create Update object
                update = Update.de_json(data, self.application.bot)
                if not update:
                    logger.error("Failed to create Update object")
                    raise HTTPException(status_code=400, detail="Invalid update")
                
                # Log update type for debugging
                if update.edited_message:
                    logger.info(f"Received edited_message update for chat {update.edited_message.chat.id}")
                elif update.message:
                    logger.info(f"Received message update for chat {update.message.chat.id}")
                    # Log forwarded message details
                    if hasattr(update.message, 'forward_origin') or hasattr(update.message, 'forward_from_chat'):
                        logger.info(f"Forwarded message detected: forward_origin={hasattr(update.message, 'forward_origin')}, forward_from_chat={hasattr(update.message, 'forward_from_chat')}")
                
                # Process update
                await self.application.process_update(update)
                
                return {"status": "ok"}
                
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {"status": "healthy", "bot": "running"}
    
    async def start(self):
        """Start the bot with webhook"""
        try:
            logger.info("Starting bot with webhook...")

            # Initialize database async pool
            from bot.database.database import db
            await db.create_async_pool()

            # Initialize application
            await self.application.initialize()
            await self.application.start()
            
            # Set webhook
            webhook_url = Config.WEBHOOK_URL
            await self.application.bot.set_webhook(
                url=webhook_url,
                allowed_updates=['message', 'edited_message', 'callback_query', 'my_chat_member']
            )
            
            logger.info(f"Webhook set to: {webhook_url}")
            logger.info("Bot started successfully")
            
            # Start FastAPI server with concurrency support
            config = uvicorn.Config(
                app=self.app,
                host=Config.WEBHOOK_HOST,
                port=Config.WEBHOOK_PORT,
                log_level="info",
                workers=1,  # Single worker for webhook mode (Telegram requirement)
                loop="asyncio",
                # Enable concurrent request handling
                access_log=True,
                # Increase timeout for database operations
                timeout_keep_alive=30,
                # Configure for better concurrency
                backlog=2048,  # Maximum number of pending connections
                # Use multiple threads for I/O operations
                limit_concurrency=100,  # Maximum concurrent connections
                limit_max_requests=10000  # Restart worker after this many requests
            )
            server = uvicorn.Server(config)
            await server.serve()
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise
    
    async def stop(self):
        """Stop the bot gracefully"""
        logger.info("Stopping bot...")

        # Close database connections
        try:
            from bot.database.database import db
            if db.pool:
                db.pool.close()
                await db.pool.wait_closed()
                logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")

        # Delete webhook
        try:
            await self.application.bot.delete_webhook()
            logger.info("Webhook deleted")
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")

        # Stop application
        await self.application.stop()
        await self.application.shutdown()
        logger.info("Bot stopped")


async def main():
    """Main function"""
    bot = TelegramBot()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        await bot.stop()


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)