"""
utils/telegram_alerts.py — Sends trading alerts to your phone via Telegram.

How it works:
    1. You create a free Telegram bot (via @BotFather)
    2. You get a bot token and your chat ID
    3. Put them in .env
    4. This class sends messages to that bot whenever something happens

The bot sends you 4 types of alerts:
    - Decision alerts  (what the bot decided: GRID / SCALP / WAIT)
    - Order alerts     (what orders were placed or simulated)
    - Risk alerts      (when a safety limit is breached or extreme volatility)
    - Daily summaries  (your P&L and equity at the end of each day)

Usage:
    from utils.telegram_alerts import TelegramAlerts
    alerts = TelegramAlerts()
    alerts.send_decision_alert("GRID", "PEPE-USD", {...})
"""

import requests
from datetime import datetime, timezone

from config import settings
from utils.logger import logger


class TelegramAlerts:
    """
    Sends formatted trading alerts to a Telegram chat.

    Uses the Telegram Bot API via simple HTTP requests (no extra library).
    If ENABLE_TELEGRAM_ALERTS is False or credentials are missing,
    all methods silently do nothing (so the bot runs fine without Telegram).
    """

    def __init__(self):
        """Load Telegram credentials from config."""
        self.enabled = settings.ENABLE_TELEGRAM_ALERTS
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID

        # Check if properly configured
        if self.enabled:
            if not self.bot_token or not self.chat_id:
                logger.warning(
                    "Telegram alerts ENABLED but token/chat_id missing! "
                    "Alerts will be skipped. Fill TELEGRAM_BOT_TOKEN and "
                    "TELEGRAM_CHAT_ID in your .env file."
                )
                self.enabled = False
            else:
                logger.info("TelegramAlerts initialized — alerts are ON")
        else:
            logger.info("TelegramAlerts initialized — alerts are OFF")

    # ------------------------------------------------------------------
    #  CORE: Send a message
    # ------------------------------------------------------------------

    def _send_message(self, text: str) -> bool:
        """
        Send a text message to the configured Telegram chat.

        Args:
            text: The message to send (supports Telegram MarkdownV2 or plain text).

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.debug("Telegram message sent successfully")
                return True
            else:
                logger.warning(
                    f"Telegram API error: {response.status_code} — "
                    f"{response.text[:200]}"
                )
                return False
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")
            return False

    # ------------------------------------------------------------------
    #  ALERT 1: Decision Alert
    # ------------------------------------------------------------------

    def send_decision_alert(
        self,
        decision: str,
        symbol: str,
        details: dict,
    ) -> bool:
        """
        Send an alert about the hybrid strategy decision.

        Args:
            decision: "GRID", "SCALP", or "WAIT"
            symbol:   Trading pair (e.g. "PEPE-USD")
            details:  The details dict from the hybrid decision
        """
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")
        mode = "PAPER" if settings.PAPER_TRADING else "LIVE"

        if decision == "GRID":
            icon = "|||"
            detail_lines = (
                f"  Spacing: {details.get('grid_spacing_pct', 0):.2f}%\n"
                f"  Capital: ${details.get('total_capital', 0):.2f}\n"
                f"  Est profit: ${details.get('est_profit_per_cycle', 0):.4f}"
            )
        elif decision == "SCALP":
            icon = ">>>"
            direction = details.get("direction", "?").upper()
            detail_lines = (
                f"  Side: {details.get('side', '?')}\n"
                f"  Direction: {direction}\n"
                f"  Entry: ${details.get('entry_price', 0):.10f}\n"
                f"  Target: ${details.get('target_price', 0):.10f}\n"
                f"  Stop: ${details.get('stop_price', 0):.10f}"
            )
        else:
            icon = "..."
            detail_lines = (
                f"  Momentum: {details.get('current_momentum', 0):.2f}\n"
                f"  Direction: {details.get('current_direction', '?')}"
            )

        msg = (
            f"<b>{icon} {decision} — {symbol}</b>\n"
            f"[{mode}] {now}\n\n"
            f"{detail_lines}"
        )
        return self._send_message(msg)

    # ------------------------------------------------------------------
    #  ALERT 2: Order Alert
    # ------------------------------------------------------------------

    def send_order_alert(self, exec_result: dict, symbol: str) -> bool:
        """
        Send an alert about orders that were placed/simulated.

        Args:
            exec_result: The dict returned by OrderExecutor.execute_plan()
            symbol:      Trading pair
        """
        action = exec_result["action"]
        orders = exec_result["orders"]
        mode = "PAPER" if exec_result["paper_mode"] else "LIVE"

        if not orders:
            # Don't spam for WAIT/no orders
            return False

        # Count order types
        buys = sum(1 for o in orders if o.get("side") == "BUY")
        sells = sum(1 for o in orders if o.get("side") == "SELL")

        total_usd = sum(o.get("size_usd", 0) or 0 for o in orders)

        msg = (
            f"<b>Orders — {symbol}</b>\n"
            f"[{mode}] Action: {action}\n\n"
            f"  {buys} buys + {sells} sells\n"
            f"  Total: ${total_usd:,.4f}\n"
            f"  Status: {exec_result['summary']}"
        )
        return self._send_message(msg)

    # ------------------------------------------------------------------
    #  ALERT 3: Daily Summary
    # ------------------------------------------------------------------

    def send_daily_summary(
        self,
        daily_pnl: float,
        current_equity: float,
        peak_equity: float,
        total_cycles: int,
    ) -> bool:
        """
        Send a daily performance summary.

        Args:
            daily_pnl:      Today's profit/loss in USD.
            current_equity:  Current total account value.
            peak_equity:     All-time high account value.
            total_cycles:    How many cycles the bot has completed today.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mode = "PAPER" if settings.PAPER_TRADING else "LIVE"
        pnl_icon = "+" if daily_pnl >= 0 else ""

        msg = (
            f"<b>Daily Summary — {now}</b>\n"
            f"[{mode}]\n\n"
            f"  P&amp;L today: {pnl_icon}${daily_pnl:,.4f}\n"
            f"  Equity: ${current_equity:,.4f}\n"
            f"  Peak: ${peak_equity:,.4f}\n"
            f"  Cycles today: {total_cycles}"
        )
        return self._send_message(msg)

    # ------------------------------------------------------------------
    #  ALERT 4: Risk Alert
    # ------------------------------------------------------------------

    def send_risk_alert(self, message: str) -> bool:
        """
        Send an urgent risk/safety alert.

        Args:
            message: Description of what happened.
        """
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")
        mode = "PAPER" if settings.PAPER_TRADING else "LIVE"

        msg = (
            f"<b>RISK ALERT</b>\n"
            f"[{mode}] {now}\n\n"
            f"  {message}"
        )
        return self._send_message(msg)

    # ------------------------------------------------------------------
    #  ALERT 5: Startup Alert
    # ------------------------------------------------------------------

    def send_startup_alert(self) -> bool:
        """Send a message when the bot starts up."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        mode = "PAPER" if settings.PAPER_TRADING else "LIVE"
        pairs = ", ".join(settings.TRADING_PAIRS)

        msg = (
            f"<b>Bot Started</b>\n"
            f"[{mode}] {now}\n\n"
            f"  Pairs: {pairs}\n"
            f"  Max position: ${settings.MAX_POSITION_SIZE_USD:.2f}\n"
            f"  Cycle: every 5 min"
        )
        return self._send_message(msg)
