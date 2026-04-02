"""
utils/backtester.py — Replays historical data through the full trading pipeline.

Instead of waiting 5 minutes between cycles, the backtester loads historical
candle data and fast-forwards through it. At each simulated cycle it runs the
same pipeline the live bot uses (indicators → regime → grid → momentum →
hybrid decision → risk check) and then simulates whether orders would have
filled based on actual price movement in the NEXT candle(s).

This tells you: "If I had run this bot over the last 30 days, how much
money would I have made or lost?"

Usage:
    from utils.backtester import Backtester
    bt = Backtester()
    summary, equity_curve = bt.run_backtest("PEPE-USD", days_back=7)
"""

import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from execution.coinbase_client import CoinbaseClient
from data.fetcher import DataFetcher
from data.indicators import add_indicators
from ml.regime_classifier import RegimeClassifier
from ml.momentum_predictor import MomentumPredictor
from strategies.grid_strategy import GridStrategy
from strategies.hybrid_strategy import HybridStrategy
from utils.risk_manager import RiskManager
from utils.logger import logger


class Backtester:
    """
    Replays the full trading pipeline on historical data.

    How it works:
        1. Fetches all 5-minute candles for the requested period
        2. Walks through them with a sliding window of 100 candles
        3. At each step, runs the full pipeline (regime, grid, momentum, hybrid)
        4. Simulates whether grid/scalp orders would have filled
        5. Tracks equity, trades, wins, losses, and drawdown

    The backtester does NOT place real orders — it is purely a simulator.
    """

    # How many candles we need for indicator warmup (must match live bot)
    WINDOW_SIZE = 100

    # How many candles to skip between cycles
    # 1 = every candle (every 5 min), 6 = every 30 min, 12 = every hour
    CYCLE_EVERY_N_CANDLES = 1

    # Scalp: how many candles to look ahead for target/stop hit
    SCALP_LOOKAHEAD = 12  # 12 candles = 1 hour at 5-min granularity

    # Trading fee (Coinbase spot fee — 0.6% taker for low-volume accounts)
    FEE_PCT = 0.006

    def __init__(self):
        """Initialize the backtester with shared pipeline objects."""
        logger.info("Backtester initializing...")

        self.client = CoinbaseClient()
        self.fetcher = DataFetcher(self.client)
        self.classifier = RegimeClassifier()
        self.risk_mgr = RiskManager()

        logger.info("Backtester initialized — ready to run.")

    # ==================================================================
    #  MAIN ENTRY POINT
    # ==================================================================

    def run_backtest(
        self,
        symbol: str = "PEPE-USD",
        days_back: int = 7,
        initial_capital: float = 1000.0,
    ) -> tuple[dict, pd.Series]:
        """
        Run a full backtest over historical data.

        Args:
            symbol:          Trading pair (e.g. "PEPE-USD").
            days_back:       How many days of history to test (max ~30).
            initial_capital: Starting USD balance for the simulation.

        Returns:
            (summary_dict, equity_curve_series)
            summary_dict has all the key metrics.
            equity_curve is a pandas Series indexed by timestamp.
        """
        logger.info(
            f"Starting backtest: {symbol}, {days_back} days, "
            f"${initial_capital:.2f} starting capital"
        )
        bt_start_time = time.time()

        # ----- Step 1: Fetch all historical candles -----
        print(f"\n  Fetching {days_back} days of 5-minute candles for {symbol}...")
        all_candles = self._fetch_historical_candles(symbol, days_back)

        if len(all_candles) < self.WINDOW_SIZE + 10:
            logger.error(
                f"Not enough candles for backtest! Got {len(all_candles)}, "
                f"need at least {self.WINDOW_SIZE + 10}"
            )
            return {"error": "Not enough historical data"}, pd.Series(dtype=float)

        print(f"  Got {len(all_candles)} candles "
              f"({all_candles['timestamp'].iloc[0]} to "
              f"{all_candles['timestamp'].iloc[-1]})")

        # ----- Step 2: Initialize simulation state -----
        cash = initial_capital
        coin_holdings = 0.0          # How many coins we hold
        peak_equity = initial_capital
        start_of_day_equity = initial_capital

        # Tracking lists
        equity_timestamps = []
        equity_values = []

        # Counters
        total_cycles = 0
        grid_cycles = 0
        scalp_trades = 0
        scalp_wins = 0
        scalp_losses = 0
        wait_cycles = 0
        risk_stops = 0

        grid_profit_total = 0.0
        scalp_profit_total = 0.0

        # ----- Step 3: Walk through candles with sliding window -----
        max_index = len(all_candles) - 1
        step_index = self.WINDOW_SIZE  # Start after warmup period

        num_steps = (max_index - step_index) // self.CYCLE_EVERY_N_CANDLES
        progress_interval = max(1, num_steps // 20)  # Print 20 progress dots

        print(f"  Simulating {num_steps} trading cycles...\n  [", end="", flush=True)

        while step_index <= max_index - 1:
            total_cycles += 1

            # Progress bar
            if total_cycles % progress_interval == 0:
                print("=", end="", flush=True)

            # ----- Get the window of candles for this cycle -----
            window_df = all_candles.iloc[step_index - self.WINDOW_SIZE : step_index + 1].copy()
            window_df = window_df.reset_index(drop=True)

            # ----- Add indicators -----
            try:
                df = add_indicators(window_df)
            except Exception:
                step_index += self.CYCLE_EVERY_N_CANDLES
                continue

            if len(df) < 10:
                step_index += self.CYCLE_EVERY_N_CANDLES
                continue

            current_price = df.iloc[-1]["close"]

            # ----- Calculate current equity -----
            current_equity = cash + (coin_holdings * current_price)
            if current_equity > peak_equity:
                peak_equity = current_equity

            # Record equity
            equity_timestamps.append(df.iloc[-1]["timestamp"])
            equity_values.append(current_equity)

            # ----- Risk checks -----
            daily_loss_hit = self.risk_mgr.check_daily_loss(
                current_equity, start_of_day_equity
            )
            drawdown_hit = self.risk_mgr.check_drawdown(
                current_equity, peak_equity
            )

            if daily_loss_hit or drawdown_hit:
                risk_stops += 1
                step_index += self.CYCLE_EVERY_N_CANDLES
                continue

            # ----- Run the full pipeline -----
            regime_result = self.classifier.classify(df)

            grid = GridStrategy(df, regime_result, capital_usd=current_equity)
            grid_levels = grid.calculate_grid_levels()

            predictor = MomentumPredictor(df)
            momentum_result = predictor.get_momentum_score()

            hybrid = HybridStrategy(df, regime_result, grid_levels, momentum_result)
            decision = hybrid.decide_and_execute_plan()

            dec = decision["decision"]

            # ----- Simulate the decision -----
            if dec == "GRID":
                grid_cycles += 1

                # Simulate grid fills using the NEXT candle
                if step_index + 1 <= max_index:
                    next_candle = all_candles.iloc[step_index + 1]
                    profit = self._simulate_grid_fill(
                        grid_levels, next_candle, current_equity
                    )
                    cash += profit
                    grid_profit_total += profit

            elif dec == "SCALP":
                scalp_trades += 1
                scalp_plan = decision["details"]

                # Simulate scalp using future candles
                lookahead_end = min(
                    step_index + 1 + self.SCALP_LOOKAHEAD, max_index + 1
                )
                future_candles = all_candles.iloc[step_index + 1 : lookahead_end]

                profit, won = self._simulate_scalp_fill(
                    scalp_plan, future_candles, current_equity
                )
                cash += profit
                scalp_profit_total += profit

                if won:
                    scalp_wins += 1
                else:
                    scalp_losses += 1

            else:  # WAIT
                wait_cycles += 1

            # Advance to next cycle
            step_index += self.CYCLE_EVERY_N_CANDLES

        print("]  Done!\n")

        # ----- Step 4: Final equity -----
        final_price = all_candles.iloc[-1]["close"]
        final_equity = cash + (coin_holdings * final_price)

        # ----- Step 5: Build the equity curve -----
        equity_curve = pd.Series(
            data=equity_values,
            index=pd.DatetimeIndex(equity_timestamps),
            name="equity",
        )

        # ----- Step 6: Calculate summary metrics -----
        total_profit = final_equity - initial_capital
        total_return_pct = (total_profit / initial_capital) * 100

        # Max drawdown from equity curve
        if len(equity_curve) > 0:
            rolling_peak = equity_curve.cummax()
            drawdowns = (equity_curve - rolling_peak) / rolling_peak * 100
            max_drawdown_pct = abs(drawdowns.min())
            max_drawdown_usd = abs((equity_curve - rolling_peak).min())
        else:
            max_drawdown_pct = 0.0
            max_drawdown_usd = 0.0

        # Win rate (scalp only — grid is always net positive if fills happen)
        scalp_win_rate = (
            (scalp_wins / scalp_trades) * 100 if scalp_trades > 0 else 0.0
        )

        # Sharpe-like ratio (daily returns)
        if len(equity_curve) > 1:
            # Resample to get one value per hour to smooth
            hourly = equity_curve.resample("1h").last().dropna()
            if len(hourly) > 1:
                returns = hourly.pct_change().dropna()
                if returns.std() > 0:
                    # Annualize: ~8760 hours/year
                    sharpe = (returns.mean() / returns.std()) * np.sqrt(8760)
                else:
                    sharpe = 0.0
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        elapsed = time.time() - bt_start_time

        summary = {
            "symbol": symbol,
            "days_back": days_back,
            "initial_capital": initial_capital,
            "final_equity": round(final_equity, 4),
            "total_profit_usd": round(total_profit, 4),
            "total_return_pct": round(total_return_pct, 4),
            "max_drawdown_pct": round(max_drawdown_pct, 4),
            "max_drawdown_usd": round(max_drawdown_usd, 4),
            "sharpe_ratio": round(sharpe, 4),
            "total_cycles": total_cycles,
            "grid_cycles": grid_cycles,
            "scalp_trades": scalp_trades,
            "scalp_wins": scalp_wins,
            "scalp_losses": scalp_losses,
            "scalp_win_rate_pct": round(scalp_win_rate, 2),
            "wait_cycles": wait_cycles,
            "risk_stops": risk_stops,
            "grid_profit_usd": round(grid_profit_total, 4),
            "scalp_profit_usd": round(scalp_profit_total, 4),
            "candles_processed": len(all_candles),
            "backtest_time_seconds": round(elapsed, 1),
            "start_date": str(all_candles["timestamp"].iloc[0]),
            "end_date": str(all_candles["timestamp"].iloc[-1]),
        }

        logger.info(
            f"Backtest complete — {total_cycles} cycles, "
            f"P&L: ${total_profit:+.4f} ({total_return_pct:+.2f}%), "
            f"max DD: {max_drawdown_pct:.2f}%"
        )

        return summary, equity_curve

    # ==================================================================
    #  HISTORICAL DATA FETCHER (batched)
    # ==================================================================

    def _fetch_historical_candles(
        self, symbol: str, days_back: int
    ) -> pd.DataFrame:
        """
        Fetch many days of 5-minute candles by making multiple API calls
        (Coinbase allows max 300 candles per request).

        Returns a single DataFrame sorted oldest → newest.
        """
        all_frames = []
        batch_size = 300          # Max candles per API call
        candle_seconds = 300      # 5-minute candles = 300 seconds each

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days_back)

        current_end = end_time

        batch_num = 0
        while current_end > start_time:
            batch_num += 1
            current_start = current_end - timedelta(
                seconds=candle_seconds * batch_size
            )

            # Don't go before our requested start
            if current_start < start_time:
                current_start = start_time

            # Convert to unix timestamp strings for the SDK
            start_str = str(int(current_start.timestamp()))
            end_str = str(int(current_end.timestamp()))

            try:
                response = self.client.client.get_candles(
                    product_id=symbol,
                    start=start_str,
                    end=end_str,
                    granularity="FIVE_MINUTE",
                )

                candles = []
                for c in response.candles:
                    candles.append({
                        "timestamp": datetime.fromtimestamp(
                            int(c.start), tz=timezone.utc
                        ),
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                        "volume": float(c.volume),
                    })

                if candles:
                    all_frames.append(pd.DataFrame(candles))
                    logger.debug(
                        f"  Batch {batch_num}: got {len(candles)} candles"
                    )

            except Exception as e:
                logger.warning(f"  Batch {batch_num} failed: {e}")

            # Move the window back
            current_end = current_start - timedelta(seconds=1)

            # Small pause to avoid rate limiting
            time.sleep(0.15)

        if not all_frames:
            logger.error("No candle data retrieved!")
            return pd.DataFrame()

        # Combine all batches into one big DataFrame
        combined = pd.concat(all_frames, ignore_index=True)

        # Remove duplicates (overlapping batches) and sort
        combined = combined.drop_duplicates(subset=["timestamp"])
        combined = combined.sort_values("timestamp").reset_index(drop=True)

        logger.info(
            f"Historical data: {len(combined)} candles over "
            f"{days_back} days for {symbol}"
        )
        return combined

    # ==================================================================
    #  GRID FILL SIMULATOR
    # ==================================================================

    def _simulate_grid_fill(
        self,
        grid_levels: dict,
        next_candle: pd.Series,
        current_equity: float,
    ) -> float:
        """
        Simulate which grid orders would have filled in the next candle.

        Logic:
            - If next candle's LOW dips to a buy level → buy fills
            - If next candle's HIGH reaches a sell level → sell fills
            - Each matched buy+sell pair earns the spread minus fees

        Returns:
            Net profit (USD) from grid fills this cycle.
        """
        next_low = next_candle["low"]
        next_high = next_candle["high"]

        buys_filled = 0
        sells_filled = 0

        # Count how many buy levels the low touched
        for level in grid_levels["buy_levels"]:
            if next_low <= level["price"]:
                buys_filled += 1

        # Count how many sell levels the high touched
        for level in grid_levels["sell_levels"]:
            if next_high >= level["price"]:
                sells_filled += 1

        # Matched pairs = the minimum of buys and sells that filled
        matched_pairs = min(buys_filled, sells_filled)

        if matched_pairs == 0:
            return 0.0

        # Profit per pair = capital_per_level × spacing_pct, minus fees
        capital_per_level = grid_levels["capital_per_level"]
        spacing_pct = grid_levels["grid_spacing_pct"] / 100

        # Gross profit per pair: buy low, sell high across the spacing
        gross_per_pair = capital_per_level * spacing_pct

        # Fees: pay fee on both the buy and the sell
        fee_per_pair = capital_per_level * self.FEE_PCT * 2

        net_per_pair = gross_per_pair - fee_per_pair
        total_profit = net_per_pair * matched_pairs

        return total_profit

    # ==================================================================
    #  SCALP FILL SIMULATOR
    # ==================================================================

    def _simulate_scalp_fill(
        self,
        scalp_plan: dict,
        future_candles: pd.DataFrame,
        current_equity: float,
    ) -> tuple[float, bool]:
        """
        Simulate a scalp trade by looking at future candles.

        Logic:
            - For BUY: check if HIGH hits target or LOW hits stop
            - For SELL: check if LOW hits target or HIGH hits stop
            - First one to trigger wins
            - If neither triggers within SCALP_LOOKAHEAD candles, close at
              the last candle's close price

        Returns:
            (profit_usd, won_bool)
        """
        if future_candles.empty:
            return 0.0, False

        side = scalp_plan.get("side", "BUY")
        entry_price = scalp_plan["entry_price"]
        target_price = scalp_plan["target_price"]
        stop_price = scalp_plan["stop_price"]

        # Position size: 25% of max position (same as live bot)
        from config import settings
        scalp_usd = min(settings.MAX_POSITION_SIZE_USD * 0.25, current_equity * 0.25)
        scalp_coins = scalp_usd / entry_price

        # Entry fee
        entry_fee = scalp_usd * self.FEE_PCT

        # Walk through future candles
        for _, candle in future_candles.iterrows():
            if side == "BUY":
                # Check target (high reaches target)
                if candle["high"] >= target_price:
                    exit_value = scalp_coins * target_price
                    exit_fee = exit_value * self.FEE_PCT
                    profit = exit_value - scalp_usd - entry_fee - exit_fee
                    return profit, True

                # Check stop (low hits stop)
                if candle["low"] <= stop_price:
                    exit_value = scalp_coins * stop_price
                    exit_fee = exit_value * self.FEE_PCT
                    profit = exit_value - scalp_usd - entry_fee - exit_fee
                    return profit, False

            else:  # SELL
                # Check target (low reaches target — price going down)
                if candle["low"] <= target_price:
                    # Profit = sold high, buy back low
                    sell_revenue = scalp_coins * entry_price
                    buyback_cost = scalp_coins * target_price
                    fees = (sell_revenue + buyback_cost) * self.FEE_PCT
                    profit = sell_revenue - buyback_cost - fees
                    return profit, True

                # Check stop (high hits stop — price going up against us)
                if candle["high"] >= stop_price:
                    sell_revenue = scalp_coins * entry_price
                    buyback_cost = scalp_coins * stop_price
                    fees = (sell_revenue + buyback_cost) * self.FEE_PCT
                    profit = sell_revenue - buyback_cost - fees
                    return profit, False

        # Timeout — close at last candle's close price
        last_close = future_candles.iloc[-1]["close"]

        if side == "BUY":
            exit_value = scalp_coins * last_close
            exit_fee = exit_value * self.FEE_PCT
            profit = exit_value - scalp_usd - entry_fee - exit_fee
        else:
            sell_revenue = scalp_coins * entry_price
            buyback_cost = scalp_coins * last_close
            fees = (sell_revenue + buyback_cost) * self.FEE_PCT
            profit = sell_revenue - buyback_cost - fees

        won = profit > 0
        return profit, won
