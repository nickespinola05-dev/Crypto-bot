"""
utils/logger.py — Centralized logging using Loguru.

Usage anywhere in the project:
    from utils.logger import logger
    logger.info("Bot started")
    logger.warning("Low balance!")
    logger.error("Connection failed")
"""

import sys
from loguru import logger

from config import settings

# Remove the default handler so we can configure our own
logger.remove()

# --- Console handler (colored, human-readable) ---
logger.add(
    sys.stdout,
    level=settings.LOG_LEVEL,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    ),
    colorize=True,
)

# --- File handler (rotating log files) ---
logger.add(
    "logs/bot_{time:YYYY-MM-DD}.log",
    level="DEBUG",           # File always captures everything
    rotation="10 MB",        # New file after 10 MB
    retention="30 days",     # Auto-delete old logs
    compression="zip",       # Compress rotated files
    format=(
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} — {message}"
    ),
)

logger.info(f"Logger initialized — console level: {settings.LOG_LEVEL}")
