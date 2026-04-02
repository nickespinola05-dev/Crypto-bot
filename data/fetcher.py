"""
data/fetcher.py — Fetches market data from Coinbase and returns clean DataFrames.

Usage:
    from execution.coinbase_client import CoinbaseClient
    from data.fetcher import DataFetcher

    cb = CoinbaseClient()
    fetcher = DataFetcher(cb)
    df = fetcher.get_recent_candles("PEPE-USD")
    print(df.tail())
"""

import pandas as pd

from config import settings
from utils.logger import logger


class DataFetcher:
    """Fetches and cleans market data from Coinbase."""

    def __init__(self, client):
        """
        Args:
            client: An initialized CoinbaseClient instance.
        """
        self.client = client
        logger.info("DataFetcher initialized")

    def get_recent_candles(
        self,
        symbol: str,
        granularity: str = "FIVE_MINUTE",
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        Fetch recent candles and return a clean pandas DataFrame.

        Args:
            symbol:      Trading pair, e.g. "PEPE-USD", "DOGE-USD"
            granularity: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
                         ONE_HOUR, SIX_HOUR, ONE_DAY
            limit:       Number of candles to fetch (max 300)

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            Sorted oldest → newest, with timestamp as a proper datetime.
        """
        logger.info(f"Fetching {limit} candles for {symbol} ({granularity})...")

        # Get raw candle data from our Coinbase client
        raw_candles = self.client.get_candles(
            product_id=symbol,
            granularity=granularity,
            num_candles=limit,
        )

        # Convert to DataFrame
        df = pd.DataFrame(raw_candles)

        # Convert timestamp string to proper datetime
        df["timestamp"] = pd.to_datetime(df["time"])
        df = df.drop(columns=["time"])

        # Reorder columns so timestamp is first
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        # Sort by time (oldest first) and reset the index
        df = df.sort_values("timestamp").reset_index(drop=True)

        logger.info(
            f"Got {len(df)} candles for {symbol} — "
            f"latest close: ${df['close'].iloc[-1]:.8f}"
        )
        return df

    def get_all_symbols(self) -> list[str]:
        """Return the list of trading pairs from config."""
        return settings.TRADING_PAIRS
