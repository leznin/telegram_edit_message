"""
Logging configuration for the Telegram bot
"""

import logging
import logging.handlers
import os
from datetime import datetime
from bot.utils.config import Config


def setup_logging() -> None:
    """Setup logging configuration"""
    
    # Create logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # Console handler
            logging.StreamHandler(),
            # File handler with time-based rotation (30 days = ~1 month)
            logging.handlers.TimedRotatingFileHandler(
                filename=os.path.join(log_dir, Config.LOG_FILE),
                when='D',  # Rotate daily
                interval=30,  # Every 30 days
                backupCount=1,  # Keep only 1 backup file (older logs are deleted)
                encoding='utf-8'
            )
        ]
    )
    
    # Set specific logger levels
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('mysql.connector').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name"""
    return logging.getLogger(name)