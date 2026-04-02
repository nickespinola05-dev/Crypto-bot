"""
execution/coinbase_client.py — Thin wrapper around the official Coinbase Advanced Trade SDK.

Step 1 capabilities (READ-ONLY — no orders yet):
    - Connect to Coinbase using API key + secret
    - Get account balances
    - Get recent candles (OHLCV) for any trading pair
    - Test connection with a simple health check

Usage:
    from execution.coinbase_client import CoinbaseClient
    cb = CoinbaseClient()
    cb.test_connection()
"""

from datetime import datetime, timedelta, timezone

from coinbase.rest import RESTClient

from config import settings
from utils.logger import logger


class CoinbaseClient:
    """Read-only Coinbase Advanced Trade client (no orders yet)."""

    def __init__(self):
        """Initialize the REST client with credentials from config."""
        if not settings.validate():
            logger.warning(
                "Coinbase API credentials are not set! "
                "Fill in your .env file before calling any API methods."
            )

        self.client = RESTClient(
            api_key=settings.COINBASE_API_KEY,
            api_secret=settings.COINBASE_API_SECRET,
        )
        logger.info("CoinbaseClient initialized")

    # ------------------------------------------------------------------
    #  ACCOUNT / BALANCE
    # ------------------------------------------------------------------

    def get_accounts(self, limit: int = 49) -> list[dict]:
        """
        Fetch all accounts (wallets) and return them as a list of dicts.
        Each dict has: name, currency, available_balance, hold.
        """
        response = self.client.get_accounts(limit=limit)
        accounts = []
        for acct in response.accounts:
            accounts.append(
                {
                    "name": acct.name,
                    "currency": acct.currency,
                    "available": acct.available_balance.get("value", "0"),
                    "hold": acct.hold.get("value", "0") if acct.hold else "0",
                }
            )
        return accounts

    def get_balance(self, currency: str = "USD") -> float:
        """Get the available balance for a specific currency (e.g. 'USD')."""
        accounts = self.get_accounts()
        for acct in accounts:
            if acct["currency"].upper() == currency.upper():
                return float(acct["available"])
        return 0.0

    # ------------------------------------------------------------------
    #  MARKET DATA — CANDLES
    # ------------------------------------------------------------------

    def get_candles(
        self,
        product_id: str = "BTC-USD",
        granularity: str = "ONE_HOUR",
        num_candles: int = 100,
    ) -> list[dict]:
        """
        Fetch recent OHLCV candles for a trading pair.

        Args:
            product_id:  e.g. "DOGE-USD", "SHIB-USD", "BTC-USD"
            granularity: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
                         ONE_HOUR, SIX_HOUR, ONE_DAY
            num_candles: How many candles to fetch (max 300 per request)

        Returns:
            List of dicts with keys: time, open, high, low, close, volume
            Sorted oldest → newest.
        """
        # Calculate the time window needed
        granularity_seconds = {
            "ONE_MINUTE": 60,
            "FIVE_MINUTE": 300,
            "FIFTEEN_MINUTE": 900,
            "ONE_HOUR": 3600,
            "SIX_HOUR": 21600,
            "ONE_DAY": 86400,
        }
        seconds_per_candle = granularity_seconds.get(granularity, 3600)
        now = datetime.now(timezone.utc)
        start = now - timedelta(seconds=seconds_per_candle * num_candles)

        # API expects Unix timestamp strings
        start_str = str(int(start.timestamp()))
        end_str = str(int(now.timestamp()))

        response = self.client.get_candles(
            product_id=product_id,
            start=start_str,
            end=end_str,
            granularity=granularity,
        )

        candles = []
        for c in response.candles:
            candles.append(
                {
                    "time": datetime.fromtimestamp(
                        int(c.start), tz=timezone.utc
                    ).isoformat(),
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume),
                }
            )

        # SDK returns newest-first; reverse to oldest-first
        candles.sort(key=lambda x: x["time"])
        logger.info(
            f"Fetched {len(candles)} candles for {product_id} ({granularity})"
        )
        return candles

    # ------------------------------------------------------------------
    #  HEALTH CHECK
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        """
        Quick connection test — prints USD balance and first few accounts.
        Returns True if successful, False otherwise.
        """
        logger.info("Testing Coinbase connection...")
        try:
            accounts = self.get_accounts()
            usd_balance = self.get_balance("USD")

            logger.info(f"Connection OK — USD balance: ${usd_balance:.2f}")
            logger.info(f"Total accounts/wallets found: {len(accounts)}")

            # Show non-zero balances
            for acct in accounts:
                if float(acct["available"]) > 0:
                    logger.info(
                        f"  {acct['currency']}: {acct['available']} available"
                    )

            return True

        except Exception as e:
            logger.error(f"Connection FAILED: {e}")
            return False


# ------------------------------------------------------------------
#  Quick standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    client = CoinbaseClient()
    client.test_connection()
