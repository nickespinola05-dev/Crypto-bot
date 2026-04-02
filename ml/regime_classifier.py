"""
ml/regime_classifier.py — Detects whether the market is RANGING or TRENDING.

This is the brain that decides which strategy to use:
    RANGING  → activate the grid strategy (buy low, sell high in a range)
    TRENDING → activate the momentum scalper (ride the breakout)

For now this uses a rule-based approach with the technical indicators.
In a later step we'll upgrade it to a trained ML model.

Usage:
    from ml.regime_classifier import RegimeClassifier
    classifier = RegimeClassifier()
    regime = classifier.classify(df_with_indicators)
"""

import pandas as pd
import numpy as np

from utils.logger import logger


class RegimeClassifier:
    """
    Classifies market regime as RANGING or TRENDING.

    Logic (rule-based v1):
        We score 4 indicators. Each votes TRENDING or RANGING.
        The majority vote wins.

        1. ADX > 25         → TRENDING    (strong directional movement)
           ADX <= 25        → RANGING     (weak / sideways)

        2. BB Width > 4%    → TRENDING    (bands expanding = breakout)
           BB Width <= 4%   → RANGING     (bands tight = consolidation)

        3. |RSI - 50| > 20  → TRENDING    (overbought/oversold = momentum)
           |RSI - 50| <= 20 → RANGING     (RSI near middle = no conviction)

        4. |MACD hist| growing over last 5 bars → TRENDING
           |MACD hist| flat or shrinking        → RANGING
    """

    # Thresholds (we'll tune these later with real data)
    ADX_THRESHOLD = 25.0
    BB_WIDTH_THRESHOLD = 4.0
    RSI_DISTANCE_THRESHOLD = 20.0

    def __init__(self):
        logger.info("RegimeClassifier initialized (rule-based v1)")

    def classify(self, df: pd.DataFrame) -> dict:
        """
        Classify the current market regime from a DataFrame with indicators.

        Args:
            df: DataFrame from add_indicators() — must have:
                adx_14, bb_width, rsi_14, macd_hist columns

        Returns:
            dict with keys:
                regime:      "RANGING" or "TRENDING"
                confidence:  0.0 to 1.0 (what fraction of indicators agree)
                scores:      dict of individual indicator votes
                details:     human-readable explanation
        """
        if df.empty:
            logger.warning("Empty DataFrame passed to classifier!")
            return {
                "regime": "RANGING",
                "confidence": 0.0,
                "scores": {},
                "details": "No data available",
            }

        # Use the most recent row for classification
        latest = df.iloc[-1]
        votes = {}

        # ----- Vote 1: ADX (trend strength) -----
        adx_val = latest["adx_14"]
        votes["adx"] = {
            "vote": "TRENDING" if adx_val > self.ADX_THRESHOLD else "RANGING",
            "value": round(adx_val, 2),
            "reason": (
                f"ADX={adx_val:.1f} {'>' if adx_val > self.ADX_THRESHOLD else '<='} "
                f"{self.ADX_THRESHOLD} threshold"
            ),
        }

        # ----- Vote 2: Bollinger Band Width -----
        bb_val = latest["bb_width"]
        votes["bb_width"] = {
            "vote": "TRENDING" if bb_val > self.BB_WIDTH_THRESHOLD else "RANGING",
            "value": round(bb_val, 2),
            "reason": (
                f"BB Width={bb_val:.2f}% {'>' if bb_val > self.BB_WIDTH_THRESHOLD else '<='} "
                f"{self.BB_WIDTH_THRESHOLD}% threshold"
            ),
        }

        # ----- Vote 3: RSI distance from 50 -----
        rsi_val = latest["rsi_14"]
        rsi_distance = abs(rsi_val - 50)
        votes["rsi"] = {
            "vote": "TRENDING" if rsi_distance > self.RSI_DISTANCE_THRESHOLD else "RANGING",
            "value": round(rsi_val, 2),
            "reason": (
                f"RSI={rsi_val:.1f}, distance from 50={rsi_distance:.1f} "
                f"{'>' if rsi_distance > self.RSI_DISTANCE_THRESHOLD else '<='} "
                f"{self.RSI_DISTANCE_THRESHOLD} threshold"
            ),
        }

        # ----- Vote 4: MACD histogram momentum -----
        # Check if |MACD hist| is growing over last 5 bars
        if len(df) >= 5:
            recent_hist = df["macd_hist"].iloc[-5:].abs()
            macd_growing = recent_hist.iloc[-1] > recent_hist.iloc[0]
        else:
            macd_growing = False

        votes["macd"] = {
            "vote": "TRENDING" if macd_growing else "RANGING",
            "value": round(latest["macd_hist"], 8),
            "reason": (
                f"MACD histogram {'growing' if macd_growing else 'shrinking/flat'} "
                f"over last 5 bars"
            ),
        }

        # ----- Count the votes -----
        trending_votes = sum(
            1 for v in votes.values() if v["vote"] == "TRENDING"
        )
        total_votes = len(votes)
        confidence = trending_votes / total_votes

        if trending_votes > total_votes / 2:
            regime = "TRENDING"
        else:
            regime = "RANGING"

        # Build human-readable summary
        details_lines = [f"  {name}: {v['vote']} — {v['reason']}" for name, v in votes.items()]
        details = "\n".join(details_lines)

        result = {
            "regime": regime,
            "confidence": round(confidence, 2),
            "scores": votes,
            "details": details,
        }

        logger.info(
            f"Regime: {regime} (confidence: {confidence:.0%} — "
            f"{trending_votes}/{total_votes} indicators say TRENDING)"
        )
        return result
