"""
Database module for Telegram bot
Handles all database operations including:
- Chats where bot is admin
- Chat-channel bindings
- Message edit logs
"""

import mysql.connector
from mysql.connector import Error
import aiomysql
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import asyncio
from bot.utils.config import get_database_config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database manager class for handling all database operations"""

    def __init__(self):
        self.connection = None  # For synchronous operations (migrations, etc.)
        self.pool = None  # For asynchronous operations
        self.connect()
        self.create_tables()
    
    def connect(self) -> None:
        """Establish database connection"""
        try:
            config = get_database_config()
            self.connection = mysql.connector.connect(**config)
            logger.info("Database connection established")
        except Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise
    
    async def create_async_pool(self):
        """Create asynchronous connection pool"""
        try:
            config = get_database_config()
            # Prepare config for aiomysql (different parameter names)
            async_config = {
                'host': config['host'],
                'port': config['port'],
                'user': config['user'],
                'password': config['password'],
                'db': config['database'],  # aiomysql uses 'db' instead of 'database'
                'minsize': 5,  # Minimum connections in pool
                'maxsize': 20,  # Maximum connections in pool
                'charset': 'utf8mb4',
                'autocommit': True,
                'use_unicode': True
            }

            self.pool = await aiomysql.create_pool(**async_config)
            logger.info("Asynchronous database connection pool created")
        except Exception as e:
            logger.error(f"Error creating async database pool: {e}")
            raise

    def create_tables(self) -> None:
        """Create all necessary tables"""
        try:
            cursor = self.connection.cursor()
            
            # Table for storing chats where bot is admin
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_chats (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    chat_id BIGINT UNIQUE NOT NULL,
                    chat_title VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
                    chat_type VARCHAR(50),
                    admin_user_id BIGINT NOT NULL,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    delete_messages_enabled BOOLEAN DEFAULT TRUE,
                    INDEX idx_chat_id (chat_id),
                    INDEX idx_admin_user_id (admin_user_id)
                ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            
            # Table for chat-channel bindings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_channel_bindings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    admin_user_id BIGINT NOT NULL,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    UNIQUE KEY unique_chat_channel (chat_id, channel_id),
                    INDEX idx_chat_id (chat_id),
                    INDEX idx_channel_id (channel_id),
                    INDEX idx_admin_user_id (admin_user_id)
                ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            
            # Add delete_messages_enabled column if it doesn't exist (migration)
            try:
                cursor.execute("""
                    ALTER TABLE bot_chats
                    ADD COLUMN delete_messages_enabled BOOLEAN DEFAULT TRUE
                """)
                self.connection.commit()
                logger.info("Migration: added delete_messages_enabled column")
            except Error as e:
                if "Duplicate column name" in str(e):
                    logger.info("Migration: delete_messages_enabled column already exists")
                else:
                    logger.warning(f"Migration warning for delete_messages_enabled: {e}")

            # Add max_edit_time_minutes column if it doesn't exist (migration)
            try:
                cursor.execute("""
                    ALTER TABLE bot_chats
                    ADD COLUMN max_edit_time_minutes INT DEFAULT 20
                """)
                self.connection.commit()
                logger.info("Migration: added max_edit_time_minutes column")
            except Error as e:
                if "Duplicate column name" in str(e):
                    logger.info("Migration: max_edit_time_minutes column already exists")
                else:
                    logger.warning(f"Migration warning for max_edit_time_minutes: {e}")

            # Table for chat moderators
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_moderators (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    moderator_user_id BIGINT NOT NULL,
                    moderator_username VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
                    moderator_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
                    added_by_user_id BIGINT NOT NULL,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    UNIQUE KEY unique_chat_moderator (chat_id, moderator_user_id),
                    INDEX idx_chat_id (chat_id),
                    INDEX idx_moderator_user_id (moderator_user_id),
                    INDEX idx_added_by_user_id (added_by_user_id),
                    FOREIGN KEY (chat_id) REFERENCES bot_chats(chat_id) ON DELETE CASCADE
                ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)

            # Add moderator_username and moderator_name columns if they don't exist (migration)
            try:
                cursor.execute("""
                    ALTER TABLE chat_moderators
                    ADD COLUMN moderator_username VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """)
                self.connection.commit()
                logger.info("Migration: added moderator_username column")
            except Error as e:
                if "Duplicate column name" in str(e):
                    logger.info("Migration: moderator_username column already exists")
                else:
                    logger.warning(f"Migration warning for moderator_username: {e}")

            try:
                cursor.execute("""
                    ALTER TABLE chat_moderators
                    ADD COLUMN moderator_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """)
                self.connection.commit()
                logger.info("Migration: added moderator_name column")
            except Error as e:
                if "Duplicate column name" in str(e):
                    logger.info("Migration: moderator_name column already exists")
                else:
                    logger.warning(f"Migration warning for moderator_name: {e}")

            # Run migration for existing moderators
            try:
                self.migrate_moderator_info()
            except Exception as e:
                logger.warning(f"Migration warning for moderator info: {e}")

            self.connection.commit()
            logger.info("Database tables created successfully")
            
        except Error as e:
            logger.error(f"Error creating tables: {e}")
            raise
        finally:
            cursor.close()
    
    def add_chat(self, chat_id: int, chat_title: str, chat_type: str, admin_user_id: int) -> bool:
        """Add a new chat where bot is admin (only for groups and supergroups)"""
        try:
            # Explicitly reject channels - they should only be managed via chat_channel_bindings
            if chat_type.lower() == 'channel':
                logger.warning(f"Attempted to add channel {chat_id} to bot_chats table - channels are not allowed")
                return False
                
            cursor = self.connection.cursor()
            query = """
                INSERT INTO bot_chats (chat_id, chat_title, chat_type, admin_user_id)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                chat_title = VALUES(chat_title),
                is_active = TRUE
            """
            cursor.execute(query, (chat_id, chat_title, chat_type, admin_user_id))
            self.connection.commit()
            logger.info(f"Chat {chat_id} ({chat_type}) added/updated for admin {admin_user_id}")
            return True
            
        except Error as e:
            logger.error(f"Error adding chat: {e}")
            return False
        finally:
            cursor.close()
    
    def get_user_chats(self, admin_user_id: int) -> List[Dict[str, Any]]:
        """Get all active chats for a specific admin user"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            query = """
                SELECT chat_id, chat_title, chat_type, added_date
                FROM bot_chats
                WHERE admin_user_id = %s AND is_active = TRUE
                ORDER BY added_date DESC
            """
            cursor.execute(query, (admin_user_id,))
            chats = cursor.fetchall()
            return chats
            
        except Error as e:
            logger.error(f"Error getting user chats: {e}")
            return []
        finally:
            cursor.close()
    
    def bind_chat_channel(self, chat_id: int, channel_id: int, admin_user_id: int) -> bool:
        """Bind a chat to a channel"""
        try:
            cursor = self.connection.cursor()
            query = """
                INSERT INTO chat_channel_bindings (chat_id, channel_id, admin_user_id)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                is_active = TRUE,
                created_date = CURRENT_TIMESTAMP
            """
            cursor.execute(query, (chat_id, channel_id, admin_user_id))
            self.connection.commit()
            logger.info(f"Chat {chat_id} bound to channel {channel_id}")
            return True
            
        except Error as e:
            logger.error(f"Error binding chat to channel: {e}")
            return False
        finally:
            cursor.close()

    async def bind_chat_channel_async(self, chat_id: int, channel_id: int, admin_user_id: int) -> bool:
        """Bind a chat to a channel (asynchronous version)"""
        if not self.pool:
            logger.error("Async pool not initialized")
            return False

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = """
                        INSERT INTO chat_channel_bindings (chat_id, channel_id, admin_user_id)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        is_active = TRUE,
                        created_date = CURRENT_TIMESTAMP
                    """
                    await cursor.execute(query, (chat_id, channel_id, admin_user_id))
                    logger.info(f"Chat {chat_id} bound to channel {channel_id}")
                    return True
        except Exception as e:
            logger.error(f"Error binding chat to channel: {e}")
            return False

    def get_chat_channel(self, chat_id: int) -> Optional[int]:
        """Get bound channel for a chat"""
        try:
            cursor = self.connection.cursor()
            query = """
                SELECT channel_id
                FROM chat_channel_bindings
                WHERE chat_id = %s AND is_active = TRUE
                LIMIT 1
            """
            cursor.execute(query, (chat_id,))
            result = cursor.fetchone()
            return result[0] if result else None
            
        except Error as e:
            logger.error(f"Error getting chat channel: {e}")
            return None
        finally:
            cursor.close()

    async def get_chat_channel_async(self, chat_id: int) -> Optional[int]:
        """Get channel ID for a chat (asynchronous version)"""
        if not self.pool:
            logger.error("Async pool not initialized")
            return None

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = """
                        SELECT channel_id
                        FROM chat_channel_bindings
                        WHERE chat_id = %s AND is_active = TRUE
                        LIMIT 1
                    """
                    await cursor.execute(query, (chat_id,))
                    result = await cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting chat channel: {e}")
            return None

    def is_chat_admin(self, chat_id: int, user_id: int) -> bool:
        """Check if user is admin of the chat in bot's database"""
        try:
            cursor = self.connection.cursor()
            query = """
                SELECT 1 FROM bot_chats
                WHERE chat_id = %s AND admin_user_id = %s AND is_active = TRUE
            """
            cursor.execute(query, (chat_id, user_id))
            result = cursor.fetchone()
            return result is not None
            
        except Error as e:
            logger.error(f"Error checking chat admin: {e}")
            return False
        finally:
            cursor.close()
    
    def deactivate_chat(self, chat_id: int) -> bool:
        """Deactivate a chat (when bot is removed)"""
        try:
            cursor = self.connection.cursor()
            query = "UPDATE bot_chats SET is_active = FALSE WHERE chat_id = %s"
            cursor.execute(query, (chat_id,))
            self.connection.commit()
            logger.info(f"Chat {chat_id} deactivated")
            return True
            
        except Error as e:
            logger.error(f"Error deactivating chat: {e}")
            return False
        finally:
            cursor.close()
    
    def remove_chat_channel_binding(self, chat_id: int) -> bool:
        """Deactivate channel bindings for a chat (when bot is removed)"""
        try:
            cursor = self.connection.cursor()
            
            # First check if there are any active bindings
            check_query = "SELECT COUNT(*) FROM chat_channel_bindings WHERE chat_id = %s AND is_active = TRUE"
            cursor.execute(check_query, (chat_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Deactivate all bindings for this chat instead of deleting
                update_query = "UPDATE chat_channel_bindings SET is_active = FALSE WHERE chat_id = %s AND is_active = TRUE"
                cursor.execute(update_query, (chat_id,))
                self.connection.commit()
                logger.info(f"Deactivated {count} channel binding(s) for chat {chat_id}")
                return True
            else:
                logger.debug(f"No active channel bindings found for chat {chat_id}")
                return False
                
        except Error as e:
            logger.error(f"Error removing channel bindings for chat {chat_id}: {e}")
            return False
        finally:
            cursor.close()
    
    def deactivate_channel_bindings(self, channel_id: int) -> bool:
        """Deactivate channel bindings when bot is removed from channel"""
        try:
            cursor = self.connection.cursor()
            
            # First check if there are any active bindings for this channel
            check_query = "SELECT COUNT(*) FROM chat_channel_bindings WHERE channel_id = %s AND is_active = TRUE"
            cursor.execute(check_query, (channel_id,))
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Deactivate all bindings for this channel
                update_query = "UPDATE chat_channel_bindings SET is_active = FALSE WHERE channel_id = %s AND is_active = TRUE"
                cursor.execute(update_query, (channel_id,))
                self.connection.commit()
                logger.info(f"Deactivated {count} binding(s) for channel {channel_id}")
                return True
            else:
                logger.debug(f"No active bindings found for channel {channel_id}")
                return False
                
        except Error as e:
            logger.error(f"Error deactivating channel bindings for channel {channel_id}: {e}")
            return False
        finally:
            cursor.close()
    
    def get_delete_messages_setting(self, chat_id: int) -> bool:
        """Get the delete messages setting for a chat"""
        try:
            cursor = self.connection.cursor()
            query = """
                SELECT delete_messages_enabled
                FROM bot_chats
                WHERE chat_id = %s AND is_active = TRUE
            """
            cursor.execute(query, (chat_id,))
            result = cursor.fetchone()
            # Default to True if not found
            return result[0] if result else True

        except Error as e:
            logger.error(f"Error getting delete messages setting for chat {chat_id}: {e}")
            return True  # Default to enabled
        finally:
            cursor.close()

    async def get_delete_messages_setting_async(self, chat_id: int) -> bool:
        """Get the delete messages setting for a chat (asynchronous version)"""
        if not self.pool:
            logger.error("Async pool not initialized")
            return True  # Default to enabled

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = """
                        SELECT delete_messages_enabled
                        FROM bot_chats
                        WHERE chat_id = %s AND is_active = TRUE
                    """
                    await cursor.execute(query, (chat_id,))
                    result = await cursor.fetchone()
                    # Default to True if not found
                    return result[0] if result else True
        except Exception as e:
            logger.error(f"Error getting delete messages setting for chat {chat_id}: {e}")
            return True  # Default to enabled

    def set_delete_messages_setting(self, chat_id: int, enabled: bool) -> bool:
        """Set the delete messages setting for a chat"""
        try:
            cursor = self.connection.cursor()
            query = """
                UPDATE bot_chats
                SET delete_messages_enabled = %s
                WHERE chat_id = %s AND is_active = TRUE
            """
            cursor.execute(query, (enabled, chat_id))
            self.connection.commit()
            logger.info(f"Set delete messages setting for chat {chat_id} to {enabled}")
            return True

        except Error as e:
            logger.error(f"Error setting delete messages setting for chat {chat_id}: {e}")
            return False
        finally:
            cursor.close()

    def get_max_edit_time_setting(self, chat_id: int) -> int:
        """Get the maximum edit time setting for a chat in minutes"""
        try:
            cursor = self.connection.cursor()
            query = """
                SELECT max_edit_time_minutes
                FROM bot_chats
                WHERE chat_id = %s AND is_active = TRUE
            """
            cursor.execute(query, (chat_id,))
            result = cursor.fetchone()
            # Default to 20 minutes if not found
            return result[0] if result else 20

        except Error as e:
            logger.error(f"Error getting max edit time setting for chat {chat_id}: {e}")
            return 20  # Default to 20 minutes
        finally:
            cursor.close()

    async def get_max_edit_time_setting_async(self, chat_id: int) -> int:
        """Get the maximum edit time setting for a chat in minutes (asynchronous version)"""
        if not self.pool:
            logger.error("Async pool not initialized")
            return 20  # Default to 20 minutes

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = """
                        SELECT max_edit_time_minutes
                        FROM bot_chats
                        WHERE chat_id = %s AND is_active = TRUE
                    """
                    await cursor.execute(query, (chat_id,))
                    result = await cursor.fetchone()
                    # Default to 20 minutes if not found
                    return result[0] if result else 20
        except Exception as e:
            logger.error(f"Error getting max edit time setting for chat {chat_id}: {e}")
            return 20  # Default to 20 minutes

    def set_max_edit_time_setting(self, chat_id: int, minutes: int) -> bool:
        """Set the maximum edit time setting for a chat in minutes"""
        try:
            # Validate minutes range (0-20 minutes)
            if minutes < 0:
                minutes = 0
            elif minutes > 20:
                minutes = 20

            cursor = self.connection.cursor()
            query = """
                UPDATE bot_chats
                SET max_edit_time_minutes = %s
                WHERE chat_id = %s AND is_active = TRUE
            """
            cursor.execute(query, (minutes, chat_id))
            self.connection.commit()
            logger.info(f"Set max edit time setting for chat {chat_id} to {minutes} minutes")
            return True

        except Error as e:
            logger.error(f"Error setting max edit time setting for chat {chat_id}: {e}")
            return False
        finally:
            cursor.close()

    def add_moderator(self, chat_id: int, moderator_user_id: int, added_by_user_id: int,
                     moderator_username: Optional[str] = None, moderator_name: Optional[str] = None) -> bool:
        """Add a moderator to a chat"""
        try:
            cursor = self.connection.cursor()
            query = """
                INSERT INTO chat_moderators (chat_id, moderator_user_id, moderator_username, moderator_name, added_by_user_id)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                is_active = TRUE,
                added_by_user_id = VALUES(added_by_user_id),
                moderator_username = VALUES(moderator_username),
                moderator_name = VALUES(moderator_name),
                added_date = CURRENT_TIMESTAMP
            """
            cursor.execute(query, (chat_id, moderator_user_id, moderator_username, moderator_name, added_by_user_id))
            self.connection.commit()
            logger.info(f"Moderator {moderator_user_id} ({moderator_name}, @{moderator_username}) added to chat {chat_id} by {added_by_user_id}")
            return True

        except Error as e:
            logger.error(f"Error adding moderator: {e}")
            return False
        finally:
            cursor.close()

    def remove_moderator(self, chat_id: int, moderator_user_id: int) -> bool:
        """Remove a moderator from a chat"""
        try:
            cursor = self.connection.cursor()
            query = """
                UPDATE chat_moderators
                SET is_active = FALSE
                WHERE chat_id = %s AND moderator_user_id = %s
            """
            cursor.execute(query, (chat_id, moderator_user_id))
            self.connection.commit()
            logger.info(f"Moderator {moderator_user_id} removed from chat {chat_id}")
            return True

        except Error as e:
            logger.error(f"Error removing moderator: {e}")
            return False
        finally:
            cursor.close()

    def is_moderator(self, chat_id: int, user_id: int) -> bool:
        """Check if user is a moderator in the chat"""
        try:
            cursor = self.connection.cursor()
            query = """
                SELECT 1 FROM chat_moderators
                WHERE chat_id = %s AND moderator_user_id = %s AND is_active = TRUE
            """
            cursor.execute(query, (chat_id, user_id))
            result = cursor.fetchone()
            return result is not None

        except Error as e:
            logger.error(f"Error checking moderator status: {e}")
            return False
        finally:
            cursor.close()

    async def is_moderator_async(self, chat_id: int, user_id: int) -> bool:
        """Check if user is a moderator in the chat (asynchronous version)"""
        if not self.pool:
            logger.error("Async pool not initialized")
            return False

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = """
                        SELECT 1 FROM chat_moderators
                        WHERE chat_id = %s AND moderator_user_id = %s AND is_active = TRUE
                    """
                    await cursor.execute(query, (chat_id, user_id))
                    result = await cursor.fetchone()
                    return result is not None
        except Exception as e:
            logger.error(f"Error checking moderator status: {e}")
            return False

    def get_chat_moderators(self, chat_id: int) -> List[Dict[str, Any]]:
        """Get all moderators for a chat"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            query = """
                SELECT moderator_user_id, moderator_username, moderator_name, added_by_user_id, added_date
                FROM chat_moderators
                WHERE chat_id = %s AND is_active = TRUE
                ORDER BY added_date DESC
            """
            cursor.execute(query, (chat_id,))
            moderators = cursor.fetchall()
            return moderators

        except Error as e:
            logger.error(f"Error getting chat moderators: {e}")
            return []
        finally:
            cursor.close()

    def get_user_moderated_chats(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all chats where user is a moderator"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            query = """
                SELECT cm.chat_id, bc.chat_title, cm.moderator_username, cm.moderator_name, cm.added_date
                FROM chat_moderators cm
                JOIN bot_chats bc ON cm.chat_id = bc.chat_id
                WHERE cm.moderator_user_id = %s AND cm.is_active = TRUE AND bc.is_active = TRUE
                ORDER BY cm.added_date DESC
            """
            cursor.execute(query, (user_id,))
            chats = cursor.fetchall()
            return chats

        except Error as e:
            logger.error(f"Error getting user moderated chats: {e}")
            return []
        finally:
            cursor.close()

    def migrate_moderator_info(self) -> bool:
        """Migrate existing moderators to include username and name fields"""
        try:
            cursor = self.connection.cursor()

            # Update existing moderators that have NULL values for username and name
            # Set default values - these can be updated later when more info is available
            update_query = """
                UPDATE chat_moderators
                SET moderator_username = NULL,
                    moderator_name = CONCAT('Пользователь ', moderator_user_id)
                WHERE moderator_username IS NULL OR moderator_name IS NULL
            """
            cursor.execute(update_query)
            updated_count = cursor.rowcount

            self.connection.commit()
            logger.info(f"Migration completed: updated {updated_count} moderator records")
            return True

        except Error as e:
            logger.error(f"Error migrating moderator info: {e}")
            return False
        finally:
            cursor.close()

    def update_moderator_info(self, chat_id: int, moderator_user_id: int,
                             username: Optional[str] = None, name: Optional[str] = None) -> bool:
        """Update username and name for an existing moderator"""
        try:
            cursor = self.connection.cursor()

            # Build update query based on what fields are provided
            update_fields = []
            values = []

            if username is not None:
                update_fields.append("moderator_username = %s")
                values.append(username)

            if name is not None:
                update_fields.append("moderator_name = %s")
                values.append(name)

            if not update_fields:
                logger.warning("No fields to update for moderator info")
                return False

            # Add WHERE conditions
            values.extend([chat_id, moderator_user_id])

            query = f"""
                UPDATE chat_moderators
                SET {', '.join(update_fields)}
                WHERE chat_id = %s AND moderator_user_id = %s AND is_active = TRUE
            """

            cursor.execute(query, values)
            self.connection.commit()

            affected_rows = cursor.rowcount
            logger.info(f"Updated moderator info for user {moderator_user_id} in chat {chat_id}: {affected_rows} rows affected")
            return affected_rows > 0

        except Error as e:
            logger.error(f"Error updating moderator info: {e}")
            return False
        finally:
            cursor.close()

    def close(self) -> None:
        """Close database connection"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logger.info("Database connection closed")


# Global database instance
db = DatabaseManager()