"""
data/indicators.py — Calculates technical indicators on candle DataFrames.

These indicators will be used by the ML regime classifier to decide
whether the market is RANGING (good for grid) or TRENDING (good for scalping).

Usage:
    from data.indicators import add_indicators
    df = fetcher.get_recent_candles("PEPE-USD")
    df = add_indicators(df)
"""

import pandas as pd
import numpy as np

from utils.logger import logger


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add all technical indicators to a candle DataFrame.

    Input must have columns: timestamp, open, high, low, close, volume
    Returns the same DataFrame with new indicator columns added.
    """
    df = df.copy()  # Don't modify the original

    # --- Moving Averages ---
    df["sma_10"] = df["close"].rolling(window=10).mean()
    df["sma_30"] = df["close"].rolling(window=30).mean()
    df["ema_10"] = df["close"].ewm(span=10, adjust=False).mean()
    df["ema_30"] = df["close"].ewm(span=30, adjust=False).mean()

    # --- RSI (Relative Strength Index, 14-period) ---
    df["rsi_14"] = _calculate_rsi(df["close"], period=14)

    # --- ATR (Average True Range, 14-period) ---
    df["atr_14"] = _calculate_atr(df, period=14)

    # --- ATR as percentage of price (normalized volatility) ---
    df["atr_pct"] = (df["atr_14"] / df["close"]) * 100

    # --- Bollinger Bands (20-period, 2 std dev) ---
    bb_mid = df["close"].rolling(window=20).mean()
    bb_std = df["close"].rolling(window=20).std()
    df["bb_upper"] = bb_mid + (bb_std * 2)
    df["bb_mid"] = bb_mid
    df["bb_lower"] = bb_mid - (bb_std * 2)

    # --- Bollinger Band Width (how wide the bands are — key for regime) ---
    df["bb_width"] = ((df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]) * 100

    # --- MACD ---
    ema_12 = df["close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # --- Volume Moving Average ---
    df["volume_sma_20"] = df["volume"].rolling(window=20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma_20"]

    # --- ADX (Average Directional Index — trend strength) ---
    df["adx_14"] = _calculate_adx(df, period=14)

    # Drop rows with NaN values from rolling calculations
    rows_before = len(df)
    df = df.dropna().reset_index(drop=True)
    rows_dropped = rows_before - len(df)

    logger.info(
        f"Indicators added — {len(df)} rows remain "
        f"({rows_dropped} dropped due to warmup period)"
    )
    return df


# ======================================================================
#  PRIVATE HELPER FUNCTIONS (the math behind the indicators)
# ======================================================================


def _calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index — measures overbought/oversold (0–100)."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — measures volatility in price units."""
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(span=period, adjust=False).mean()
    return atr


def _calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength (0–100)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Directional Movement
    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Smoothed values
    atr = true_range.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

    # ADX
    dx = (100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))).fillna(0)
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx
