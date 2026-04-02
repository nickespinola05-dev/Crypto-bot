"""
ml/momentum_predictor.py — Scores how strong and directional the current momentum is.

This answers: "Is the price about to move hard in one direction?"
    - score 0.0 = no momentum at all (dead market)
    - score 1.0 = extremely strong momentum (breakout happening NOW)
    - direction = which way it's heading

The regime classifier (Step 3) tells us IF the market is trending.
The momentum predictor tells us HOW STRONG and WHICH DIRECTION.

Together they decide: should we scalp, and which way?

Usage:
    from ml.momentum_predictor import MomentumPredictor
    predictor = MomentumPredictor(df)
    result = predictor.get_momentum_score()
    # result = {"score": 0.78, "direction": "bullish", "confidence": "high", ...}
"""

import pandas as pd
import numpy as np

from utils.logger import logger


class MomentumPredictor:
    """
    Scores momentum strength and direction using technical indicators.

    Rule-based v1 — uses 5 signals, each contributing to the score:

        1. MACD Histogram direction & growth  (is momentum building?)
        2. RSI position                       (bullish > 50, bearish < 50)
        3. Volume Ratio                       (is smart money participating?)
        4. Price vs EMA10                     (is price leading its average?)
        5. EMA10 vs EMA30 crossover           (are fast/slow MAs aligned?)

    Each signal adds 0.0 to 0.2 to the score (total max = 1.0).
    Direction is determined by which way the majority of signals point.
    """

    def __init__(self, df: pd.DataFrame):
        """
        Args:
            df: DataFrame with indicators already added (from add_indicators).
        """
        if df.empty:
            logger.warning("Empty DataFrame passed to MomentumPredictor!")
        self.df = df
        logger.info("MomentumPredictor initialized")

    def get_momentum_score(self) -> dict:
        """
        Calculate the momentum score and direction.

        Returns:
            dict with keys:
                score:       float 0.0–1.0 (how strong the momentum is)
                direction:   "bullish" / "bearish" / "neutral"
                confidence:  "high" / "medium" / "low"
                signals:     dict of individual signal details
                summary:     human-readable one-line summary
        """
        if self.df.empty or len(self.df) < 5:
            return {
                "score": 0.0,
                "direction": "neutral",
                "confidence": "low",
                "signals": {},
                "summary": "Not enough data for momentum analysis",
            }

        latest = self.df.iloc[-1]
        signals = {}
        bullish_points = 0.0
        bearish_points = 0.0

        # ----- Signal 1: MACD Histogram (0.0–0.2 points) -----
        macd_hist = latest["macd_hist"]
        # Check if histogram is growing over last 5 bars
        recent_hist = self.df["macd_hist"].iloc[-5:]
        hist_growing = abs(recent_hist.iloc[-1]) > abs(recent_hist.iloc[0])

        if macd_hist > 0 and hist_growing:
            bullish_points += 0.2
            macd_vote = "bullish"
        elif macd_hist < 0 and hist_growing:
            bearish_points += 0.2
            macd_vote = "bearish"
        elif macd_hist > 0:
            bullish_points += 0.1
            macd_vote = "weak bullish"
        elif macd_hist < 0:
            bearish_points += 0.1
            macd_vote = "weak bearish"
        else:
            macd_vote = "neutral"

        signals["macd_hist"] = {
            "value": round(macd_hist, 10),
            "growing": hist_growing,
            "vote": macd_vote,
        }

        # ----- Signal 2: RSI Position (0.0–0.2 points) -----
        rsi = latest["rsi_14"]

        if rsi > 65:
            bullish_points += 0.2
            rsi_vote = "strong bullish"
        elif rsi > 50:
            bullish_points += 0.1
            rsi_vote = "bullish"
        elif rsi < 35:
            bearish_points += 0.2
            rsi_vote = "strong bearish"
        elif rsi < 50:
            bearish_points += 0.1
            rsi_vote = "bearish"
        else:
            rsi_vote = "neutral"

        signals["rsi"] = {
            "value": round(rsi, 1),
            "vote": rsi_vote,
        }

        # ----- Signal 3: Volume Ratio (0.0–0.2 points) -----
        vol_ratio = latest["volume_ratio"]

        if vol_ratio > 1.5:
            # High volume — strong signal, direction from price action
            if latest["close"] > latest["open"]:
                bullish_points += 0.2
                vol_vote = "strong bullish (high vol + green candle)"
            else:
                bearish_points += 0.2
                vol_vote = "strong bearish (high vol + red candle)"
        elif vol_ratio > 1.2:
            if latest["close"] > latest["open"]:
                bullish_points += 0.1
                vol_vote = "bullish (above-avg volume)"
            else:
                bearish_points += 0.1
                vol_vote = "bearish (above-avg volume)"
        else:
            vol_vote = "neutral (low volume)"

        signals["volume"] = {
            "value": round(vol_ratio, 2),
            "vote": vol_vote,
        }

        # ----- Signal 4: Price vs EMA10 (0.0–0.2 points) -----
        price = latest["close"]
        ema10 = latest["ema_10"]
        price_vs_ema_pct = ((price - ema10) / ema10) * 100

        if price_vs_ema_pct > 0.5:
            bullish_points += 0.2
            ema_vote = "bullish (price well above EMA10)"
        elif price_vs_ema_pct > 0:
            bullish_points += 0.1
            ema_vote = "bullish (price above EMA10)"
        elif price_vs_ema_pct < -0.5:
            bearish_points += 0.2
            ema_vote = "bearish (price well below EMA10)"
        elif price_vs_ema_pct < 0:
            bearish_points += 0.1
            ema_vote = "bearish (price below EMA10)"
        else:
            ema_vote = "neutral"

        signals["price_vs_ema10"] = {
            "value": round(price_vs_ema_pct, 3),
            "vote": ema_vote,
        }

        # ----- Signal 5: EMA10 vs EMA30 Crossover (0.0–0.2 points) -----
        ema10 = latest["ema_10"]
        ema30 = latest["ema_30"]
        ema_spread_pct = ((ema10 - ema30) / ema30) * 100

        if ema_spread_pct > 0.3:
            bullish_points += 0.2
            cross_vote = "bullish (EMA10 well above EMA30)"
        elif ema_spread_pct > 0:
            bullish_points += 0.1
            cross_vote = "bullish (EMA10 above EMA30)"
        elif ema_spread_pct < -0.3:
            bearish_points += 0.2
            cross_vote = "bearish (EMA10 well below EMA30)"
        elif ema_spread_pct < 0:
            bearish_points += 0.1
            cross_vote = "bearish (EMA10 below EMA30)"
        else:
            cross_vote = "neutral"

        signals["ema_crossover"] = {
            "value": round(ema_spread_pct, 3),
            "vote": cross_vote,
        }

        # ----- Combine into final score -----
        # The score is the MAX of bullish or bearish points
        score = max(bullish_points, bearish_points)
        score = round(min(score, 1.0), 2)  # Cap at 1.0

        # Direction from whichever side has more points
        if bullish_points > bearish_points:
            direction = "bullish"
        elif bearish_points > bullish_points:
            direction = "bearish"
        else:
            direction = "neutral"

        # Confidence based on how lopsided the score is
        spread = abs(bullish_points - bearish_points)
        if spread >= 0.4:
            confidence = "high"
        elif spread >= 0.2:
            confidence = "medium"
        else:
            confidence = "low"

        summary = (
            f"Momentum: {score:.2f}/1.00 {direction} ({confidence} confidence) — "
            f"bull={bullish_points:.1f} bear={bearish_points:.1f}"
        )

        logger.info(summary)

        return {
            "score": score,
            "direction": direction,
            "confidence": confidence,
            "bullish_points": round(bullish_points, 2),
            "bearish_points": round(bearish_points, 2),
            "signals": signals,
            "summary": summary,
        }
