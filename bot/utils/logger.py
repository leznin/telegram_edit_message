"""
Logging configuration for the Telegram bot
"""

import logging
import os
from bot.utils.config import Config


def setup_logging() -> None:
    """Setup logging configuration"""

    # Create logs directory if it doesn't exist
    log_dir = "/home/finalword/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # Console handler only
            logging.StreamHandler()
        ]
    )
    
    # Set specific logger levels
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('mysql.connector').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name"""
    return logging.getLogger(name)