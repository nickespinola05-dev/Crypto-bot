"""
strategies/grid_strategy.py — Dynamic grid strategy engine.

The grid strategy places buy orders below the current price and sell orders
above it. When price bounces between levels, we capture profit on each cycle.

Grid spacing adapts to volatility:
    - High volatility (big ATR%) → wider spacing (avoid getting stopped out)
    - Low volatility (small ATR%) → tighter spacing (more frequent fills)

Usage:
    from strategies.grid_strategy import GridStrategy
    grid = GridStrategy(df, regime_result, capital_usd=100.0)
    levels = grid.calculate_grid_levels()
"""

import pandas as pd

from config import settings
from utils.logger import logger


class GridStrategy:
    """
    Calculates dynamic grid levels based on price action and volatility.

    The grid adapts in two ways:
        1. Spacing scales with ATR% (volatile = wider grid)
        2. In TRENDING regime, the grid shifts in the trend direction
           and widens slightly as a safety buffer
    """

    # How many grid lines on each side of the current price
    # Fewer levels = more capital per order = faster fills
    NUM_LEVELS = 3

    # ATR multiplier: grid_spacing = ATR% * this value
    ATR_MULTIPLIER_RANGING = 1.2    # Slightly wider than ATR when ranging
    ATR_MULTIPLIER_TRENDING = 1.8   # Wider when trending

    # Min/max spacing to prevent crazy values
    # Min = 0.50%: with 0.40% maker fees per side (0.80% round-trip),
    # counter-sell at buy+1.0% gives 0.20% net profit per round-trip.
    # Fills often because B1 is only 0.50% below market.
    MIN_SPACING_PCT = 0.50  # Just above fees — optimized for fill frequency
    MAX_SPACING_PCT = 4.0   # Cap for extreme volatility

    # Estimated Coinbase fee per side (maker ~0.40%)
    # Limit orders = maker fees on both buy and sell
    FEE_PER_SIDE_PCT = 0.40

    # What fraction of max capital to use per coin
    # 3 coins × 0.28 = 84% deployed, 16% reserve
    CAPITAL_FRACTION = 0.28

    def __init__(
        self,
        df: pd.DataFrame,
        regime_result: dict,
        capital_usd: float | None = None,
    ):
        """
        Args:
            df:             DataFrame with indicators already added.
            regime_result:  Output from RegimeClassifier.classify().
            capital_usd:    Total USD available. Defaults to config value.
        """
        self.df = df
        self.regime = regime_result["regime"]
        self.confidence = regime_result["confidence"]

        # Use provided capital or fall back to config
        if capital_usd is not None:
            self.capital_usd = capital_usd
        else:
            self.capital_usd = settings.MAX_POSITION_SIZE_USD

        # Pull key values from the latest candle
        latest = df.iloc[-1]
        self.current_price = latest["close"]
        self.atr_pct = latest["atr_pct"]
        self.bb_width = latest["bb_width"]

        logger.info(
            f"GridStrategy created — price: ${self.current_price:.10f}, "
            f"ATR%: {self.atr_pct:.3f}%, regime: {self.regime}"
        )

    def calculate_grid_levels(self) -> dict:
        """
        Calculate the full grid: buy levels, sell levels, spacing, and
        estimated profit per cycle.

        Returns:
            dict with keys:
                current_price:           float
                regime:                  str ("RANGING" or "TRENDING")
                grid_spacing_pct:        float (spacing as percentage)
                grid_spacing_usd:        float (spacing in USD)
                buy_levels:              list of 5 dicts (level, price, size_usd, size_coins)
                sell_levels:             list of 5 dicts (level, price, size_usd, size_coins)
                capital_per_level:       float (USD allocated to each grid line)
                total_capital_deployed:  float (total USD across all buy levels)
                est_profit_per_cycle:    float (profit if ALL 5 buy+sell pairs fill once)
                est_profit_pct:          float (profit as % of deployed capital)
        """
        # ----- Step 1: Calculate dynamic grid spacing -----
        if self.regime == "TRENDING":
            multiplier = self.ATR_MULTIPLIER_TRENDING
        else:
            multiplier = self.ATR_MULTIPLIER_RANGING

        spacing_pct = self.atr_pct * multiplier

        # Clamp to min/max bounds
        spacing_pct = max(self.MIN_SPACING_PCT, min(self.MAX_SPACING_PCT, spacing_pct))

        # Convert to dollar amount
        spacing_usd = self.current_price * (spacing_pct / 100)

        # ----- Step 2: Calculate position sizing -----
        # Total capital for this coin = max position * fraction
        total_for_coin = self.capital_usd * self.CAPITAL_FRACTION

        # Split equally across the 5 buy levels
        capital_per_level = total_for_coin / self.NUM_LEVELS

        # ----- Step 3: Calculate buy levels (below current price) -----
        # Each level is one full grid spacing apart.
        # B1 sits one spacing below market — far enough to profit after fees.
        buy_levels = []
        for i in range(1, self.NUM_LEVELS + 1):
            # B1 = 1 spacing below, B2 = 2 spacings below, etc.
            level_price = self.current_price * (1 - (spacing_pct / 100) * i)
            coins_at_level = capital_per_level / level_price
            buy_levels.append(
                {
                    "level": i,
                    "price": level_price,
                    "size_usd": capital_per_level,
                    "size_coins": coins_at_level,
                }
            )

        # ----- Step 4: Calculate sell levels (above current price) -----
        # S1 = 1 spacing above, S2 = 2 spacings above, etc.
        # Each sell is paired with the matching buy for profit calculation.
        sell_levels = []
        for i in range(1, self.NUM_LEVELS + 1):
            level_price = self.current_price * (1 + (spacing_pct / 100) * i)
            # Sell the same number of coins we'd buy at the matching buy level
            coins_at_level = buy_levels[i - 1]["size_coins"]
            sell_levels.append(
                {
                    "level": i,
                    "price": level_price,
                    "size_usd": coins_at_level * level_price,
                    "size_coins": coins_at_level,
                }
            )

        # ----- Step 5: Estimate profit per full cycle (FEE-AWARE) -----
        # A "cycle" = all 5 buys fill, then all 5 sells fill
        total_buy_cost = sum(b["size_usd"] for b in buy_levels)
        total_sell_revenue = sum(s["size_usd"] for s in sell_levels)

        # Subtract estimated fees: fee on each buy + fee on each sell
        total_fees = (total_buy_cost + total_sell_revenue) * (self.FEE_PER_SIDE_PCT / 100)
        est_profit = total_sell_revenue - total_buy_cost - total_fees
        est_profit_pct = (est_profit / total_buy_cost) * 100 if total_buy_cost > 0 else 0

        result = {
            "current_price": self.current_price,
            "regime": self.regime,
            "grid_spacing_pct": round(spacing_pct, 4),
            "grid_spacing_usd": spacing_usd,
            "buy_levels": buy_levels,
            "sell_levels": sell_levels,
            "capital_per_level": round(capital_per_level, 2),
            "total_capital_deployed": round(total_buy_cost, 2),
            "est_fees_per_cycle": round(total_fees, 4),
            "est_profit_per_cycle": round(est_profit, 4),
            "est_profit_pct": round(est_profit_pct, 4),
        }

        logger.info(
            f"Grid calculated — spacing: {spacing_pct:.2f}%, "
            f"{self.NUM_LEVELS} buy + {self.NUM_LEVELS} sell levels, "
            f"est. profit/cycle: ${est_profit:.4f} ({est_profit_pct:.2f}%) "
            f"[after ~${total_fees:.4f} in fees]"
        )
        return result
