"""
Configuration module for the Telegram bot
Handles environment variables and application settings
"""

import os
from typing import Dict, Any
from dotenv import load_dotenv
import urllib.parse

# Load environment variables
load_dotenv()


class Config:
    """Configuration class for bot settings"""
    
    # Telegram Bot Token
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    # Webhook Configuration
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')
    WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', 8000))
    WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'bot.log')
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not cls.DATABASE_URL:
            raise ValueError("DATABASE_URL is required")
        if not cls.WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL is required for webhook mode")
        return True


def get_database_config() -> Dict[str, Any]:
    """Parse database URL and return connection config"""
    url = Config.DATABASE_URL
    parsed = urllib.parse.urlparse(url)
    
    return {
        'host': parsed.hostname,
        'port': parsed.port or 3306,
        'user': parsed.username,
        'password': parsed.password,
        'database': parsed.path[1:].split('?')[0],  # Remove leading '/' and query params
        'charset': 'utf8mb4',
        'autocommit': True,
        'use_unicode': True
    }