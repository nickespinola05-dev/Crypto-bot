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
    NUM_LEVELS = 5

    # ATR multiplier: grid_spacing = ATR% * this value
    # Example: if ATR% = 1.5% and multiplier = 1.0, spacing = 1.5%
    ATR_MULTIPLIER_RANGING = 1.0    # Tight grid when ranging
    ATR_MULTIPLIER_TRENDING = 1.5   # Wider grid when trending (safety buffer)

    # Min/max spacing to prevent crazy values
    MIN_SPACING_PCT = 0.15  # Tighter grid = more fills in calm markets
    MAX_SPACING_PCT = 5.0   # Never wider than 5%

    # What fraction of max capital to use per coin
    # With 3 coins at 0.30 each, we deploy ~90% total (10% safety reserve)
    CAPITAL_FRACTION = 0.30

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
        # B1 sits very close to market (0.05% below) for fast fills
        # B2-B5 fan out at the normal grid spacing from B1
        buy_levels = []
        b1_offset_pct = 0.05  # B1 is just 0.05% below market — almost guaranteed fill
        for i in range(1, self.NUM_LEVELS + 1):
            if i == 1:
                level_price = self.current_price * (1 - b1_offset_pct / 100)
            else:
                # B2 starts one full spacing below B1, B3 two spacings below B1, etc.
                level_price = self.current_price * (1 - b1_offset_pct / 100 - (spacing_pct / 100) * (i - 1))
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
        # S1 sits close to market (0.05% above) — mirrors B1
        # S2-S5 fan out at normal grid spacing
        sell_levels = []
        s1_offset_pct = 0.05
        for i in range(1, self.NUM_LEVELS + 1):
            if i == 1:
                level_price = self.current_price * (1 + s1_offset_pct / 100)
            else:
                level_price = self.current_price * (1 + s1_offset_pct / 100 + (spacing_pct / 100) * (i - 1))
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

        # ----- Step 5: Estimate profit per full cycle -----
        # A "cycle" = all 5 buys fill, then all 5 sells fill
        total_buy_cost = sum(b["size_usd"] for b in buy_levels)
        total_sell_revenue = sum(s["size_usd"] for s in sell_levels)
        est_profit = total_sell_revenue - total_buy_cost
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
            "est_profit_per_cycle": round(est_profit, 4),
            "est_profit_pct": round(est_profit_pct, 4),
        }

        logger.info(
            f"Grid calculated — spacing: {spacing_pct:.2f}%, "
            f"{self.NUM_LEVELS} buy + {self.NUM_LEVELS} sell levels, "
            f"est. profit/cycle: ${est_profit:.4f} ({est_profit_pct:.2f}%)"
        )
        return result
