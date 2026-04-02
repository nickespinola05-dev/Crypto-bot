"""
utils/risk_manager.py — Protects your capital with hard safety limits.

The risk manager is the bouncer at the door. Before ANY trade goes through,
it checks three things:

    1. Daily loss limit  — Have we lost too much today? Stop trading.
    2. Position size     — Is this trade too big for one coin? Block it.
    3. Max drawdown      — Have we dropped too far from our peak? Shut down.

If ANY check fails, the trade is blocked. No exceptions. This is how
professional traders survive — not by winning every trade, but by
controlling losses.

Usage:
    from utils.risk_manager import RiskManager
    rm = RiskManager()
    if rm.check_daily_loss(current_equity=95, start_of_day_equity=100):
        print("Daily loss limit hit! Stop trading!")
"""

from config import settings
from utils.logger import logger


class RiskManager:
    """
    Enforces risk limits to protect capital.

    All thresholds come from config (which loads from .env):
        MAX_POSITION_PCT     — max % of capital in one coin (default 25%)
        DAILY_LOSS_LIMIT_PCT — max daily loss before stopping (default 5%)
        MAX_DRAWDOWN_PCT     — max drop from peak before shutdown (default 15%)
    """

    def __init__(self):
        self.max_position_pct = settings.MAX_POSITION_PCT
        self.daily_loss_limit_pct = settings.DAILY_LOSS_LIMIT_PCT
        self.max_drawdown_pct = settings.MAX_DRAWDOWN_PCT

        logger.info(
            f"RiskManager initialized — "
            f"max position: {self.max_position_pct}%, "
            f"daily loss limit: {self.daily_loss_limit_pct}%, "
            f"max drawdown: {self.max_drawdown_pct}%"
        )

    # ------------------------------------------------------------------
    #  CHECK 1: Daily Loss
    # ------------------------------------------------------------------

    def check_daily_loss(
        self, current_equity: float, start_of_day_equity: float
    ) -> bool:
        """
        Has the account lost more than the daily limit?

        Args:
            current_equity:       Total account value right now (USD).
            start_of_day_equity:  Total account value at start of trading day.

        Returns:
            True if daily loss limit is BREACHED (stop trading!).
            False if we're still within limits (safe to continue).
        """
        if start_of_day_equity <= 0:
            return False

        loss_pct = ((start_of_day_equity - current_equity) / start_of_day_equity) * 100

        if loss_pct >= self.daily_loss_limit_pct:
            logger.warning(
                f"DAILY LOSS LIMIT BREACHED! "
                f"Lost {loss_pct:.2f}% (limit: {self.daily_loss_limit_pct}%) — "
                f"${start_of_day_equity:.2f} → ${current_equity:.2f}"
            )
            return True

        logger.debug(
            f"Daily loss check OK — loss: {loss_pct:.2f}% "
            f"(limit: {self.daily_loss_limit_pct}%)"
        )
        return False

    # ------------------------------------------------------------------
    #  CHECK 2: Position Size
    # ------------------------------------------------------------------

    def check_position_size(
        self,
        proposed_usd: float,
        current_exposure_usd: float,
        total_capital: float,
    ) -> bool:
        """
        Would this trade put too much capital into one coin?

        Args:
            proposed_usd:         How much USD this new trade would cost.
            current_exposure_usd: How much USD is already in this coin.
            total_capital:        Total account equity.

        Returns:
            True if the trade is SAFE (within limits).
            False if the trade would EXCEED the position limit (block it!).
        """
        if total_capital <= 0:
            return False

        new_exposure = current_exposure_usd + proposed_usd
        exposure_pct = (new_exposure / total_capital) * 100
        max_allowed = self.get_max_position_usd(total_capital)

        if new_exposure > max_allowed:
            logger.warning(
                f"POSITION SIZE BLOCKED! "
                f"New exposure ${new_exposure:.2f} ({exposure_pct:.1f}%) "
                f"exceeds limit ${max_allowed:.2f} ({self.max_position_pct}%)"
            )
            return False

        logger.debug(
            f"Position size check OK — "
            f"${new_exposure:.2f} ({exposure_pct:.1f}%) "
            f"within limit ${max_allowed:.2f} ({self.max_position_pct}%)"
        )
        return True

    # ------------------------------------------------------------------
    #  CHECK 3: Max Drawdown
    # ------------------------------------------------------------------

    def check_drawdown(
        self, current_equity: float, peak_equity: float
    ) -> bool:
        """
        Has the account fallen too far from its highest point?

        Args:
            current_equity: Total account value right now.
            peak_equity:    Highest account value ever recorded.

        Returns:
            True if max drawdown is BREACHED (shut down!).
            False if we're still within limits (safe to continue).
        """
        if peak_equity <= 0:
            return False

        drawdown_pct = ((peak_equity - current_equity) / peak_equity) * 100

        if drawdown_pct >= self.max_drawdown_pct:
            logger.warning(
                f"MAX DRAWDOWN BREACHED! "
                f"Down {drawdown_pct:.2f}% from peak (limit: {self.max_drawdown_pct}%) — "
                f"peak ${peak_equity:.2f} → current ${current_equity:.2f}"
            )
            return True

        logger.debug(
            f"Drawdown check OK — down {drawdown_pct:.2f}% "
            f"(limit: {self.max_drawdown_pct}%)"
        )
        return False

    # ------------------------------------------------------------------
    #  HELPER: Max position in dollars
    # ------------------------------------------------------------------

    def get_max_position_usd(self, total_capital: float) -> float:
        """
        How many USD can we put into a single coin?

        Args:
            total_capital: Total account equity.

        Returns:
            Maximum USD allowed for one coin position.
        """
        return total_capital * (self.max_position_pct / 100)

    # ------------------------------------------------------------------
    #  FULL RISK REPORT
    # ------------------------------------------------------------------

    def get_risk_summary(
        self,
        current_equity: float,
        start_of_day_equity: float,
        peak_equity: float,
        current_exposure_usd: float,
    ) -> dict:
        """
        Run all checks and return a complete risk summary.

        Returns:
            dict with all risk metrics and whether any limit is breached.
        """
        # Calculate all metrics
        daily_pnl_usd = current_equity - start_of_day_equity
        daily_pnl_pct = (
            (daily_pnl_usd / start_of_day_equity) * 100
            if start_of_day_equity > 0
            else 0.0
        )

        drawdown_usd = peak_equity - current_equity
        drawdown_pct = (
            (drawdown_usd / peak_equity) * 100 if peak_equity > 0 else 0.0
        )

        exposure_pct = (
            (current_exposure_usd / current_equity) * 100
            if current_equity > 0
            else 0.0
        )

        max_position = self.get_max_position_usd(current_equity)

        # Run all checks
        daily_loss_hit = self.check_daily_loss(current_equity, start_of_day_equity)
        drawdown_hit = self.check_drawdown(current_equity, peak_equity)
        any_breach = daily_loss_hit or drawdown_hit

        return {
            "current_equity": round(current_equity, 2),
            "start_of_day_equity": round(start_of_day_equity, 2),
            "peak_equity": round(peak_equity, 2),
            "daily_pnl_usd": round(daily_pnl_usd, 4),
            "daily_pnl_pct": round(daily_pnl_pct, 4),
            "drawdown_usd": round(drawdown_usd, 4),
            "drawdown_pct": round(drawdown_pct, 4),
            "current_exposure_usd": round(current_exposure_usd, 4),
            "exposure_pct": round(exposure_pct, 4),
            "max_position_usd": round(max_position, 2),
            "max_position_pct": self.max_position_pct,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "daily_loss_breached": daily_loss_hit,
            "drawdown_breached": drawdown_hit,
            "any_breach": any_breach,
            "trading_allowed": not any_breach,
        }
