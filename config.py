"""
config.py — Loads all settings from .env into easy-to-use Python variables.

Usage anywhere in the project:
    from config import settings
    print(settings.COINBASE_API_KEY)
"""

import os
from dotenv import load_dotenv

# Load .env file from the project root
load_dotenv()


class Settings:
    """Central configuration loaded from environment variables."""

    def __init__(self):
        # --- Coinbase API ---
        self.COINBASE_API_KEY: str = os.getenv("COINBASE_API_KEY", "")
        self.COINBASE_API_SECRET: str = os.getenv(
            "COINBASE_API_SECRET", ""
        ).replace("\\n", "\n")  # Handle escaped newlines in .env

        # --- Trading pairs ---
        raw_pairs = os.getenv("TRADING_PAIRS", "DOGE-USD")
        self.TRADING_PAIRS: list[str] = [
            p.strip() for p in raw_pairs.split(",") if p.strip()
        ]

        # --- Position sizing ---
        self.MAX_POSITION_SIZE_USD: float = float(
            os.getenv("MAX_POSITION_SIZE_USD", "100.0")
        )

        # --- Paper trading mode ---
        self.PAPER_TRADING: bool = (
            os.getenv("PAPER_TRADING", "true").lower() == "true"
        )

        # --- Risk Management ---
        self.MAX_POSITION_PCT: float = float(
            os.getenv("MAX_POSITION_PCT", "25.0")
        )
        self.DAILY_LOSS_LIMIT_PCT: float = float(
            os.getenv("DAILY_LOSS_LIMIT_PCT", "5.0")
        )
        self.MAX_DRAWDOWN_PCT: float = float(
            os.getenv("MAX_DRAWDOWN_PCT", "15.0")
        )

        # --- Telegram Alerts ---
        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
        self.ENABLE_TELEGRAM_ALERTS: bool = (
            os.getenv("ENABLE_TELEGRAM_ALERTS", "false").lower() == "true"
        )

        # --- Logging ---
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    def validate(self) -> bool:
        """Check that critical settings are filled in (not placeholder values)."""
        if not self.COINBASE_API_KEY or "YOUR_ORG_ID" in self.COINBASE_API_KEY:
            return False
        if (
            not self.COINBASE_API_SECRET
            or "YOUR_PRIVATE_KEY_HERE" in self.COINBASE_API_SECRET
        ):
            return False
        return True

    def __repr__(self) -> str:
        return (
            f"Settings(\n"
            f"  TRADING_PAIRS={self.TRADING_PAIRS},\n"
            f"  MAX_POSITION_SIZE_USD={self.MAX_POSITION_SIZE_USD},\n"
            f"  PAPER_TRADING={self.PAPER_TRADING},\n"
            f"  ENABLE_TELEGRAM_ALERTS={self.ENABLE_TELEGRAM_ALERTS},\n"
            f"  LOG_LEVEL={self.LOG_LEVEL},\n"
            f"  API_KEY={'***SET***' if self.validate() else '***NOT SET***'}\n"
            f")"
        )


# Single global instance — import this everywhere
settings = Settings()
