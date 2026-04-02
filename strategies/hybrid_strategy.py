"""
strategies/hybrid_strategy.py — The master brain that switches between strategies.

This is the core of the bot. It combines:
    - Regime classifier (RANGING vs TRENDING)
    - Grid strategy (profit from sideways bouncing)
    - Momentum predictor (which direction, how strong)

And decides: should we run the GRID, SCALP a breakout, or WAIT?

Decision logic:
    RANGING regime                       → GRID  (place buy/sell grid)
    TRENDING + momentum > 0.65           → SCALP (ride the breakout)
    TRENDING + momentum <= 0.65          → WAIT  (trend exists but too weak)

Usage:
    from strategies.hybrid_strategy import HybridStrategy
    hybrid = HybridStrategy(df, regime_result, grid_levels, momentum_result)
    decision = hybrid.decide_and_execute_plan()
"""

import pandas as pd

from utils.logger import logger


class HybridStrategy:
    """
    Master decision engine — picks the right strategy for the current market.
    """

    # Minimum momentum score to activate scalping
    SCALP_THRESHOLD = 0.65

    def __init__(
        self,
        df: pd.DataFrame,
        regime_result: dict,
        grid_levels: dict,
        momentum_result: dict,
    ):
        """
        Args:
            df:              DataFrame with indicators.
            regime_result:   Output from RegimeClassifier.classify().
            grid_levels:     Output from GridStrategy.calculate_grid_levels().
            momentum_result: Output from MomentumPredictor.get_momentum_score().
        """
        self.df = df
        self.regime = regime_result["regime"]
        self.regime_confidence = regime_result["confidence"]
        self.grid_levels = grid_levels
        self.momentum = momentum_result

        self.current_price = df.iloc[-1]["close"]
        self.atr_pct = df.iloc[-1]["atr_pct"]

        logger.info(
            f"HybridStrategy created — regime: {self.regime}, "
            f"momentum: {self.momentum['score']:.2f} {self.momentum['direction']}"
        )

    def decide_and_execute_plan(self) -> dict:
        """
        Make the master decision: GRID, SCALP, or WAIT.

        Returns:
            dict with keys:
                decision:     "GRID" / "SCALP" / "WAIT"
                reason:       human-readable explanation of why
                details:      strategy-specific data (grid levels OR scalp plan)
        """
        score = self.momentum["score"]
        direction = self.momentum["direction"]

        # ----- Decision 1: RANGING → run the grid -----
        if self.regime == "RANGING":
            decision = {
                "decision": "GRID",
                "reason": (
                    f"Market is RANGING (confidence: {self.regime_confidence:.0%}). "
                    f"Grid strategy is ideal — price is bouncing in a range. "
                    f"Momentum score {score:.2f} is irrelevant in ranging mode."
                ),
                "details": {
                    "strategy": "grid",
                    "grid_spacing_pct": self.grid_levels["grid_spacing_pct"],
                    "num_buy_levels": len(self.grid_levels["buy_levels"]),
                    "num_sell_levels": len(self.grid_levels["sell_levels"]),
                    "total_capital": self.grid_levels["total_capital_deployed"],
                    "est_profit_per_cycle": self.grid_levels["est_profit_per_cycle"],
                },
            }
            logger.info(
                f"Decision: GRID — ranging market, "
                f"grid spacing {self.grid_levels['grid_spacing_pct']:.2f}%"
            )
            return decision

        # ----- Decision 2: TRENDING + strong momentum → scalp -----
        if self.regime == "TRENDING" and score >= self.SCALP_THRESHOLD:
            scalp_plan = self._build_scalp_plan(direction)
            decision = {
                "decision": "SCALP",
                "reason": (
                    f"Market is TRENDING (confidence: {self.regime_confidence:.0%}) "
                    f"with strong {direction} momentum (score: {score:.2f}). "
                    f"Switching to aggressive scalping to ride the breakout."
                ),
                "details": scalp_plan,
            }
            logger.info(
                f"Decision: SCALP — {direction} breakout, "
                f"momentum {score:.2f}, "
                f"target: ${scalp_plan['target_price']:.10f}"
            )
            return decision

        # ----- Decision 3: TRENDING but weak momentum → wait -----
        decision = {
            "decision": "WAIT",
            "reason": (
                f"Market is TRENDING (confidence: {self.regime_confidence:.0%}) "
                f"but momentum is too weak (score: {score:.2f}, "
                f"threshold: {self.SCALP_THRESHOLD}). "
                f"Not safe to grid (could trend against us) and not strong enough "
                f"to scalp. Waiting for a clearer signal."
            ),
            "details": {
                "strategy": "none",
                "waiting_for": (
                    f"momentum score >= {self.SCALP_THRESHOLD} to scalp, "
                    f"or regime shift to RANGING to grid"
                ),
                "current_momentum": score,
                "current_direction": direction,
            },
        }
        logger.info(
            f"Decision: WAIT — trending but momentum only {score:.2f} "
            f"(need >= {self.SCALP_THRESHOLD})"
        )
        return decision

    def _build_scalp_plan(self, direction: str) -> dict:
        """
        Build a scalp trade plan: entry, target, and stop loss.

        Uses ATR to set realistic targets:
            - Entry:  current price
            - Target: 2x ATR in the momentum direction
            - Stop:   1x ATR against the momentum direction
        This gives a 2:1 reward-to-risk ratio.
        """
        atr_usd = self.current_price * (self.atr_pct / 100)

        if direction == "bullish":
            entry_price = self.current_price
            target_price = self.current_price + (atr_usd * 2)
            stop_price = self.current_price - (atr_usd * 1)
            side = "BUY"
        else:
            # Bearish — we don't short (spot only), so we SELL existing holdings
            # or skip. For now, we plan a "sell high, buy back lower" approach.
            entry_price = self.current_price
            target_price = self.current_price - (atr_usd * 2)
            stop_price = self.current_price + (atr_usd * 1)
            side = "SELL"

        potential_profit_pct = abs(target_price - entry_price) / entry_price * 100
        potential_loss_pct = abs(stop_price - entry_price) / entry_price * 100

        return {
            "strategy": "scalp",
            "side": side,
            "direction": direction,
            "entry_price": entry_price,
            "target_price": target_price,
            "stop_price": stop_price,
            "risk_reward_ratio": "2:1",
            "potential_profit_pct": round(potential_profit_pct, 3),
            "potential_loss_pct": round(potential_loss_pct, 3),
            "atr_used": round(atr_usd, 10),
        }
