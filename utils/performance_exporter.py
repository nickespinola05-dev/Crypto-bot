"""
utils/performance_exporter.py — Export paper-trading performance data.

Pulls live data from Coinbase via the bot's existing classes, runs the
full pipeline for each trading pair, and writes two files:

    exports/performance_summary.txt  — human-readable report
    exports/trades.csv               — every simulated order row

Usage (from main.py):
    python main.py --export
"""

import os
import csv
import numpy as np
from datetime import datetime, timezone

from config import settings
from execution.coinbase_client import CoinbaseClient
from data.fetcher import DataFetcher
from data.indicators import add_indicators
from ml.regime_classifier import RegimeClassifier
from ml.momentum_predictor import MomentumPredictor
from strategies.grid_strategy import GridStrategy
from strategies.hybrid_strategy import HybridStrategy
from strategies.position_manager import PositionManager
from utils.risk_manager import RiskManager
from utils.logger import logger


class PerformanceExporter:
    """
    Collects a snapshot of the bot's current state — positions, equity,
    risk metrics, and the decisions the pipeline would make right now —
    then writes everything to human-readable + CSV files.
    """

    def __init__(self):
        # Build all the objects we need (same as main.py)
        self.client = CoinbaseClient()
        self.client.test_connection()
        self.fetcher = DataFetcher(self.client)
        self.classifier = RegimeClassifier()
        self.risk_mgr = RiskManager()
        self.pos_mgr = PositionManager(self.client)

        # Where we write files
        self.export_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
        os.makedirs(self.export_dir, exist_ok=True)

    # ==================================================================
    #  PUBLIC — run the full export
    # ==================================================================

    def export(self) -> dict:
        """
        Run the pipeline for every trading pair, collect results,
        and write performance_summary.txt + trades.csv.

        Returns a dict with paths to the two files.
        """
        now = datetime.now(timezone.utc)
        logger.info("Performance export started...")

        # ----- Account-level data -----
        positions = self.pos_mgr.get_current_positions()
        equity_info = self.pos_mgr.get_account_equity(positions)
        exposure = self.pos_mgr.calculate_total_exposure(positions)
        current_equity = equity_info["total_equity"]
        peak_equity = self.pos_mgr.update_peak_equity(current_equity)
        risk = self.risk_mgr.get_risk_summary(
            current_equity=current_equity,
            start_of_day_equity=current_equity,
            peak_equity=peak_equity,
            current_exposure_usd=exposure,
        )

        # ----- Per-coin pipeline run -----
        all_trades = []       # list of dicts for CSV rows
        coin_summaries = []   # list of dicts for the TXT report
        total_grid_cycles = 0
        total_scalp_trades = 0
        total_wait_cycles = 0
        total_est_profit = 0.0

        for symbol in settings.TRADING_PAIRS:
            try:
                result = self._run_pipeline_for_symbol(symbol, now)
                coin_summaries.append(result["summary"])
                all_trades.extend(result["trades"])
                total_grid_cycles += result["summary"]["grid_count"]
                total_scalp_trades += result["summary"]["scalp_count"]
                total_wait_cycles += result["summary"]["wait_count"]
                total_est_profit += result["summary"]["est_profit"]
            except Exception as e:
                logger.error(f"Export pipeline failed for {symbol}: {e}")
                coin_summaries.append({
                    "symbol": symbol, "error": str(e),
                    "grid_count": 0, "scalp_count": 0, "wait_count": 0,
                    "est_profit": 0.0,
                })

        # ----- Equity curve from first pair (for Sharpe estimate) -----
        sharpe = self._estimate_sharpe(settings.TRADING_PAIRS[0])

        # ----- Scalp win/loss from trade list -----
        scalp_trades = [t for t in all_trades if t["strategy"] == "SCALP"]
        scalp_wins = sum(1 for t in scalp_trades if t["est_profit"] > 0)
        scalp_losses = len(scalp_trades) - scalp_wins
        scalp_win_rate = (scalp_wins / len(scalp_trades) * 100) if scalp_trades else 0.0

        # ----- Build the master summary -----
        master = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "mode": "PAPER" if settings.PAPER_TRADING else "LIVE",
            "trading_pairs": settings.TRADING_PAIRS,
            "cash_usd": equity_info["cash_usd"],
            "coin_value_usd": equity_info["coin_value_usd"],
            "total_equity": current_equity,
            "peak_equity": peak_equity,
            "exposure_usd": exposure,
            "exposure_pct": risk["exposure_pct"],
            "daily_pnl_usd": risk["daily_pnl_usd"],
            "daily_pnl_pct": risk["daily_pnl_pct"],
            "drawdown_usd": risk["drawdown_usd"],
            "drawdown_pct": risk["drawdown_pct"],
            "sharpe_estimate": sharpe,
            "total_grid_cycles": total_grid_cycles,
            "total_scalp_trades": total_scalp_trades,
            "total_wait_cycles": total_wait_cycles,
            "total_est_profit": total_est_profit,
            "scalp_wins": scalp_wins,
            "scalp_losses": scalp_losses,
            "scalp_win_rate": scalp_win_rate,
            "trading_allowed": risk["trading_allowed"],
            "coin_summaries": coin_summaries,
            "positions": positions,
        }

        # ----- Write files -----
        txt_path = self._write_summary_txt(master)
        csv_path = self._write_trades_csv(all_trades)

        logger.info(f"Export complete — {txt_path}, {csv_path}")
        return {"summary_path": txt_path, "csv_path": csv_path, "master": master}

    # ==================================================================
    #  PRIVATE — run pipeline for one symbol
    # ==================================================================

    def _run_pipeline_for_symbol(self, symbol: str, now: datetime) -> dict:
        """
        Fetch candles, compute indicators, run regime + momentum + grid
        + hybrid, and return a summary dict + list of simulated trade rows.
        """
        df_raw = self.fetcher.get_recent_candles(symbol, granularity="FIVE_MINUTE", limit=100)
        df = add_indicators(df_raw)

        if df.empty or len(df) < 10:
            raise ValueError(f"Not enough data for {symbol} ({len(df)} rows)")

        latest = df.iloc[-1]
        regime_result = self.classifier.classify(df)
        grid = GridStrategy(df, regime_result, capital_usd=settings.MAX_POSITION_SIZE_USD)
        grid_levels = grid.calculate_grid_levels()
        predictor = MomentumPredictor(df)
        momentum_result = predictor.get_momentum_score()
        hybrid = HybridStrategy(df, regime_result, grid_levels, momentum_result)
        decision = hybrid.decide_and_execute_plan()

        dec = decision["decision"]
        details = decision["details"]
        ts = now.strftime("%Y-%m-%d %H:%M:%S")

        trades = []

        if dec == "GRID":
            # Each grid level becomes a simulated order row
            for lv in grid_levels["buy_levels"]:
                trades.append({
                    "timestamp": ts,
                    "symbol": symbol,
                    "strategy": "GRID",
                    "side": "BUY",
                    "price": lv["price"],
                    "size_usd": lv["size_usd"],
                    "size_coins": lv["size_coins"],
                    "est_profit": grid_levels["est_profit_per_cycle"] / len(grid_levels["buy_levels"]),
                    "status": "simulated",
                })
            for lv in grid_levels["sell_levels"]:
                trades.append({
                    "timestamp": ts,
                    "symbol": symbol,
                    "strategy": "GRID",
                    "side": "SELL",
                    "price": lv["price"],
                    "size_usd": lv["size_usd"],
                    "size_coins": lv["size_coins"],
                    "est_profit": grid_levels["est_profit_per_cycle"] / len(grid_levels["sell_levels"]),
                    "status": "simulated",
                })

        elif dec == "SCALP":
            side = details.get("side", "BUY")
            entry = details.get("entry_price", latest["close"])
            target = details.get("target_price", entry)
            potential = (target - entry) / entry * 100 if entry > 0 else 0
            trades.append({
                "timestamp": ts,
                "symbol": symbol,
                "strategy": "SCALP",
                "side": side,
                "price": entry,
                "size_usd": settings.MAX_POSITION_SIZE_USD,
                "size_coins": settings.MAX_POSITION_SIZE_USD / entry if entry > 0 else 0,
                "est_profit": details.get("potential_profit_pct", potential),
                "status": "simulated",
            })

        summary = {
            "symbol": symbol,
            "price": latest["close"],
            "regime": regime_result["regime"],
            "regime_confidence": regime_result["confidence"],
            "momentum_score": momentum_result["score"],
            "momentum_direction": momentum_result["direction"],
            "decision": dec,
            "reason": decision["reason"],
            "atr_pct": latest["atr_pct"],
            "rsi": latest["rsi_14"],
            "grid_spacing_pct": grid_levels["grid_spacing_pct"],
            "est_profit": grid_levels["est_profit_per_cycle"] if dec == "GRID" else 0.0,
            "grid_count": 1 if dec == "GRID" else 0,
            "scalp_count": 1 if dec == "SCALP" else 0,
            "wait_count": 1 if dec == "WAIT" else 0,
        }

        return {"summary": summary, "trades": trades}

    # ==================================================================
    #  PRIVATE — Sharpe estimate from recent price history
    # ==================================================================

    def _estimate_sharpe(self, symbol: str) -> float:
        """
        Fetch 300 candles of the primary pair and compute an annualized
        Sharpe ratio from hourly returns as a rough performance proxy.
        """
        try:
            df_raw = self.fetcher.get_recent_candles(symbol, granularity="FIVE_MINUTE", limit=300)
            prices = df_raw.set_index("timestamp")["close"]
            hourly = prices.resample("1h").last().dropna()
            if len(hourly) < 2:
                return 0.0
            returns = hourly.pct_change().dropna()
            if returns.std() == 0:
                return 0.0
            return round(float((returns.mean() / returns.std()) * np.sqrt(8760)), 4)
        except Exception:
            return 0.0

    # ==================================================================
    #  PRIVATE — write performance_summary.txt
    # ==================================================================

    def _write_summary_txt(self, m: dict) -> str:
        """Write the human-readable performance summary."""
        path = os.path.join(self.export_dir, "performance_summary.txt")
        lines = []
        w = lines.append  # shorthand

        w("=" * 64)
        w("  HYBRID GRID + MOMENTUM SWITCH BOT")
        w("  PERFORMANCE SUMMARY")
        w("=" * 64)
        w("")
        w(f"  Generated     : {m['timestamp']}")
        w(f"  Mode          : {m['mode']}")
        w(f"  Trading pairs : {', '.join(m['trading_pairs'])}")

        w("")
        w("-" * 64)
        w("  ACCOUNT OVERVIEW")
        w("-" * 64)
        w(f"  Cash (USD)      : ${m['cash_usd']:,.4f}")
        w(f"  Coin holdings   : ${m['coin_value_usd']:,.6f}")
        w(f"  Total equity    : ${m['total_equity']:,.4f}")
        w(f"  Peak equity     : ${m['peak_equity']:,.4f}")
        w(f"  Exposure        : ${m['exposure_usd']:,.4f} ({m['exposure_pct']:.1f}%)")

        w("")
        w("-" * 64)
        w("  PERFORMANCE METRICS")
        w("-" * 64)
        pnl_sign = "+" if m["daily_pnl_usd"] >= 0 else ""
        w(f"  Daily P&L       : {pnl_sign}${m['daily_pnl_usd']:,.4f} "
          f"({pnl_sign}{m['daily_pnl_pct']:.2f}%)")
        w(f"  Drawdown        : ${m['drawdown_usd']:,.4f} ({m['drawdown_pct']:.2f}%)")
        w(f"  Sharpe estimate : {m['sharpe_estimate']:.4f}")
        w(f"  Trading allowed : {'YES' if m['trading_allowed'] else 'NO — RISK LIMIT BREACHED'}")

        w("")
        w("-" * 64)
        w("  STRATEGY BREAKDOWN")
        w("-" * 64)
        w(f"  Grid cycles     : {m['total_grid_cycles']}")
        w(f"  Scalp trades    : {m['total_scalp_trades']}")
        w(f"  Wait cycles     : {m['total_wait_cycles']}")
        w(f"  Est. grid profit: ${m['total_est_profit']:,.4f}")

        if m["total_scalp_trades"] > 0:
            w(f"  Scalp wins      : {m['scalp_wins']}")
            w(f"  Scalp losses    : {m['scalp_losses']}")
            w(f"  Scalp win rate  : {m['scalp_win_rate']:.1f}%")

        w("")
        w("-" * 64)
        w("  PER-COIN DETAIL")
        w("-" * 64)

        for cs in m["coin_summaries"]:
            sym = cs["symbol"]
            if "error" in cs:
                w(f"\n  {sym}: ERROR — {cs['error']}")
                continue

            w(f"\n  {sym}")
            w(f"    Price         : ${cs['price']:.10f}")
            w(f"    Regime        : {cs['regime']} ({cs['regime_confidence']:.0%})")
            w(f"    Momentum      : {cs['momentum_score']:.2f} ({cs['momentum_direction']})")
            w(f"    Decision      : {cs['decision']}")
            w(f"    RSI           : {cs['rsi']:.1f}")
            w(f"    ATR%          : {cs['atr_pct']:.3f}%")
            w(f"    Grid spacing  : {cs['grid_spacing_pct']:.2f}%")
            if cs["decision"] == "GRID":
                w(f"    Est. profit   : ${cs['est_profit']:,.4f}")
            w(f"    Reason        : {cs['reason'][:100]}")

        w("")
        w("-" * 64)
        w("  CURRENT POSITIONS")
        w("-" * 64)

        if m["positions"]:
            for sym, pos in m["positions"].items():
                w(f"  {sym:<14} {pos['size_coins']:<20.10f} coins  "
                  f"${pos['value_usd']:,.6f}")
        else:
            w("  (no open positions)")

        w("")
        w("-" * 64)
        w("  EQUITY CURVE SNAPSHOT")
        w("-" * 64)
        w(f"  Current equity  : ${m['total_equity']:,.4f}")
        w(f"  Peak equity     : ${m['peak_equity']:,.4f}")
        dd = m["peak_equity"] - m["total_equity"]
        w(f"  Distance to peak: ${dd:,.4f}")

        w("")
        w("=" * 64)
        w("  END OF REPORT")
        w("=" * 64)
        w("")

        with open(path, "w") as f:
            f.write("\n".join(lines))

        return path

    # ==================================================================
    #  PRIVATE — write trades.csv
    # ==================================================================

    def _write_trades_csv(self, trades: list) -> str:
        """Write every simulated order to a CSV file."""
        path = os.path.join(self.export_dir, "trades.csv")

        fieldnames = [
            "timestamp", "symbol", "strategy", "side", "price",
            "size_usd", "size_coins", "est_profit", "status",
        ]

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in trades:
                writer.writerow({
                    "timestamp": t["timestamp"],
                    "symbol": t["symbol"],
                    "strategy": t["strategy"],
                    "side": t["side"],
                    "price": f"{t['price']:.10f}",
                    "size_usd": f"{t['size_usd']:.4f}",
                    "size_coins": f"{t['size_coins']:.6f}",
                    "est_profit": f"{t['est_profit']:.6f}",
                    "status": t["status"],
                })

        return path
