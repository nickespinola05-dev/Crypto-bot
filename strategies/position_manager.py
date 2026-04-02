"""
strategies/position_manager.py — Tracks what we own and what it's worth.

The position manager answers:
    - What coins do I hold right now?
    - How much USD is deployed across all positions?
    - What's my total account equity (cash + coins)?
    - What's my all-time peak equity (for drawdown tracking)?

It reads LIVE data from Coinbase — not from files or memory.

Usage:
    from strategies.position_manager import PositionManager
    pm = PositionManager(client)
    positions = pm.get_current_positions()
    equity = pm.get_account_equity()
"""

from config import settings
from utils.logger import logger


class PositionManager:
    """
    Tracks live positions and account equity from Coinbase.
    """

    def __init__(self, client):
        """
        Args:
            client: An initialized CoinbaseClient instance.
        """
        self.client = client
        self.peak_equity = 0.0  # Will be updated as we track equity

        logger.info("PositionManager initialized")

    @property
    def live_equity(self) -> float:
        """Always fetch fresh equity from Coinbase — no caching."""
        eq = self.get_account_equity()
        return eq["total_equity"]

    # ------------------------------------------------------------------
    #  CURRENT POSITIONS
    # ------------------------------------------------------------------

    # Stablecoins that should be counted as cash, not as coin positions
    CASH_CURRENCIES = {"USD", "USDC", "USDT", "DAI", "GUSD", "USDP"}

    def get_current_positions(self) -> dict:
        """
        Get all non-zero coin positions with their current USD values.

        Returns:
            dict of symbol → {
                "currency": str,
                "size_coins": float,
                "value_usd": float,
            }

        Note: We estimate USD value by fetching the latest candle price.
              Entry price tracking will be added when we start placing orders.
        """
        accounts = self.client.get_accounts()
        positions = {}

        for acct in accounts:
            currency = acct["currency"]
            available = float(acct["available"])
            hold = float(acct["hold"])
            total_coins = available + hold

            # Skip cash/stablecoins (counted separately in equity) and zero balances
            if currency in self.CASH_CURRENCIES or total_coins <= 0:
                continue

            # Try to get a current price for this coin
            # Try USDC pair first (what we actually trade), then fall back to USD
            current_price = 0.0
            for quote in ("USDC", "USD"):
                product_id = f"{currency}-{quote}"
                try:
                    candles = self.client.get_candles(
                        product_id=product_id,
                        granularity="ONE_MINUTE",
                        num_candles=1,
                    )
                    if candles and candles[-1]["close"] > 0:
                        current_price = candles[-1]["close"]
                        break
                except Exception:
                    continue

            value_usd = total_coins * current_price

            # Use the actual trading pair key (prefer USDC)
            position_key = f"{currency}-USDC" if current_price > 0 else f"{currency}-USD"
            positions[position_key] = {
                "currency": currency,
                "size_coins": total_coins,
                "current_price": current_price,
                "value_usd": round(value_usd, 6),
            }

        logger.info(f"Found {len(positions)} non-zero positions")
        return positions

    # ------------------------------------------------------------------
    #  TOTAL EXPOSURE
    # ------------------------------------------------------------------

    def calculate_total_exposure(self, positions: dict | None = None) -> float:
        """
        Total USD value currently deployed in coins (not counting cash).

        Args:
            positions: Pre-fetched positions dict, or None to fetch fresh.

        Returns:
            Total USD exposure across all coin positions.
        """
        if positions is None:
            positions = self.get_current_positions()

        total = sum(pos["value_usd"] for pos in positions.values())
        logger.info(f"Total coin exposure: ${total:.4f}")
        return total

    # ------------------------------------------------------------------
    #  ACCOUNT EQUITY
    # ------------------------------------------------------------------

    def get_account_equity(self, positions: dict | None = None) -> dict:
        """
        Calculate total account value: cash + all coin positions.

        Cash includes USD fiat AND stablecoins (USDC, USDT, etc.)
        since they are pegged ~$1.00 each.

        Returns:
            dict with:
                cash_usd:        float (USD + stablecoin balances)
                coin_value_usd:  float (total value of all coins)
                total_equity:    float (cash + coins)
        """
        # Sum all cash-like currencies (USD + stablecoins) in one API call
        cash = 0.0
        accounts = self.client.get_accounts()
        for acct in accounts:
            if acct["currency"] in self.CASH_CURRENCIES:
                bal = float(acct["available"]) + float(acct["hold"])
                if bal > 0:
                    cash += bal
                    logger.debug(f"Cash component: {acct['currency']} = ${bal:.4f}")

        if positions is None:
            positions = self.get_current_positions()

        coin_value = sum(pos["value_usd"] for pos in positions.values())
        total = cash + coin_value

        logger.info(
            f"Account equity: ${total:.4f} "
            f"(cash: ${cash:.2f} + coins: ${coin_value:.4f})"
        )

        result = {
            "cash_usd": round(cash, 4),
            "coin_value_usd": round(coin_value, 6),
            "total_equity": round(total, 4),
        }

        # Debug: always confirm what the API returned
        print(f"[DEBUG] Live equity loaded: ${result['total_equity']:.2f}")

        return result

    # ------------------------------------------------------------------
    #  PEAK EQUITY TRACKING
    # ------------------------------------------------------------------

    def update_peak_equity(self, current_equity: float) -> float:
        """
        Update and return the all-time peak equity.

        Call this every cycle so the risk manager can track drawdown.

        Args:
            current_equity: Current total account equity.

        Returns:
            The peak equity (highest value ever seen).
        """
        if current_equity > self.peak_equity:
            old_peak = self.peak_equity
            self.peak_equity = current_equity
            if old_peak > 0:
                logger.info(
                    f"New peak equity: ${current_equity:.4f} "
                    f"(was ${old_peak:.4f})"
                )

        return self.peak_equity
