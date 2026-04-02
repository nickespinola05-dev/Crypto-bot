"""
main.py — Step 10: PRODUCTION-READY bot with Telegram alerts + safeguards.

Coinbase -> candles -> indicators -> regime -> grid -> momentum -> hybrid
-> EXTREME VOLATILITY CHECK -> risk check -> ORDER EXECUTION -> Telegram alert
-> wait 5 min -> repeat.   Daily summary at midnight UTC.

Usage:
    python main.py              # starts the live bot (runs every 5 minutes)
    python main.py --backtest   # runs the backtester instead
    Ctrl+C                      # graceful shutdown
"""

import sys
import schedule
import time
from datetime import datetime, timezone

from config import settings
from execution.coinbase_client import CoinbaseClient
from execution.order_executor import OrderExecutor
from data.fetcher import DataFetcher
from data.indicators import add_indicators
from ml.regime_classifier import RegimeClassifier
from ml.momentum_predictor import MomentumPredictor
from strategies.grid_strategy import GridStrategy
from strategies.hybrid_strategy import HybridStrategy
from strategies.position_manager import PositionManager
from utils.risk_manager import RiskManager
from utils.telegram_alerts import TelegramAlerts
from utils.shared_state import write_state, write_shutdown
from utils.pnl_tracker import record_equity, record_paper_profit
from utils.logger import logger


# =====================================================================
#  SHARED OBJECTS (created once, reused every cycle)
# =====================================================================

client = None
fetcher = None
classifier = None
risk_mgr = None
pos_mgr = None
executor = None
alerts = None

cycle_count = 0
daily_cycle_count = 0
start_of_day_equity_global = None
last_summary_date = None

# Extreme volatility threshold — if ATR% > 8%, force WAIT
EXTREME_VOLATILITY_THRESHOLD = 8.0


def initialize():
    """Create all shared objects once at startup."""
    global client, fetcher, classifier, risk_mgr, pos_mgr, executor, alerts

    logger.info("Initializing shared objects...")

    client = CoinbaseClient()
    client.test_connection()

    fetcher = DataFetcher(client)
    classifier = RegimeClassifier()
    risk_mgr = RiskManager()
    pos_mgr = PositionManager(client)
    executor = OrderExecutor(client, risk_mgr)
    alerts = TelegramAlerts()

    logger.info("All shared objects initialized successfully.")


# =====================================================================
#  DAILY SUMMARY (runs once at midnight UTC)
# =====================================================================

def send_daily_summary_if_needed():
    """
    Check if it's a new UTC day. If so, send a daily summary via Telegram
    and reset the daily counters.
    """
    global last_summary_date, daily_cycle_count, start_of_day_equity_global

    today = datetime.now(timezone.utc).date()

    if last_summary_date is None:
        # First run — just set the date, don't send summary yet
        last_summary_date = today
        return

    if today != last_summary_date:
        # It's a new day! Send yesterday's summary.
        logger.info("New UTC day detected — sending daily summary...")

        try:
            positions = pos_mgr.get_current_positions()
            equity_info = pos_mgr.get_account_equity(positions)
            current_equity = equity_info["total_equity"]
            peak_equity = pos_mgr.update_peak_equity(current_equity)

            daily_pnl = 0.0
            if start_of_day_equity_global and start_of_day_equity_global > 0:
                daily_pnl = current_equity - start_of_day_equity_global

            # Send Telegram summary
            alerts.send_daily_summary(
                daily_pnl=daily_pnl,
                current_equity=current_equity,
                peak_equity=peak_equity,
                total_cycles=daily_cycle_count,
            )

            # Print to console too
            print("\n" + "=" * 60)
            print("  DAILY SUMMARY (end of UTC day)")
            print("=" * 60)
            pnl_sign = "+" if daily_pnl >= 0 else ""
            print(f"    P&L today     : {pnl_sign}${daily_pnl:,.4f}")
            print(f"    Equity        : ${current_equity:,.4f}")
            print(f"    Peak          : ${peak_equity:,.4f}")
            print(f"    Cycles today  : {daily_cycle_count}")
            print("=" * 60 + "\n")

        except Exception as e:
            logger.error(f"Daily summary failed: {e}")

        # Reset daily counters
        last_summary_date = today
        daily_cycle_count = 0
        start_of_day_equity_global = None  # Will be set next cycle


# =====================================================================
#  FULL TRADING CYCLE (runs every 5 minutes)
# =====================================================================

def run_full_trading_cycle():
    """
    One complete pass of the trading pipeline — loops through ALL configured pairs:
        For each pair:
            fetch -> indicators -> regime -> grid -> momentum -> hybrid
            -> extreme volatility check -> risk check -> execute orders
            -> Telegram alerts -> print reports.
    """
    global cycle_count, daily_cycle_count, start_of_day_equity_global
    cycle_count += 1
    daily_cycle_count += 1

    cycle_start = datetime.now(timezone.utc)
    logger.info(f"===== CYCLE {cycle_count} START — {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} UTC =====")

    # Check if we need to send a daily summary (midnight UTC rollover)
    send_daily_summary_if_needed()

    try:
        # ----- LIVE BALANCE REFRESH (once per cycle — shared across all pairs) -----
        live_equity_info = pos_mgr.get_account_equity()   # force fresh API call
        live_equity = live_equity_info["total_equity"]
        print(f"[DEBUG] Balance refresh complete - using ${live_equity:.2f} equity")
        logger.info(f"Live equity at cycle start: ${live_equity:.4f}")
        print(f"\n  Live equity: ${live_equity:,.4f} "
              f"(cash: ${live_equity_info['cash_usd']:,.4f} + "
              f"coins: ${live_equity_info['coin_value_usd']:,.4f})")

        # ----- Loop through ALL trading pairs -----
        all_pairs = settings.TRADING_PAIRS
        all_state_orders = []
        all_state_alerts = []
        last_dec = None
        last_reason = ""
        last_risk = None
        last_symbol = all_pairs[0] if all_pairs else "DOGE-USDC"

        for pair_idx, symbol in enumerate(all_pairs):
            print(f"\n{'#' * 60}")
            print(f"  PAIR {pair_idx + 1}/{len(all_pairs)}: {symbol}")
            print(f"{'#' * 60}")

            pair_result = _run_pair_cycle(
                symbol=symbol,
                cycle_start=cycle_start,
                live_equity=live_equity,
                live_equity_info=live_equity_info,
            )

            # Collect results from this pair
            all_state_orders.extend(pair_result["state_orders"])
            all_state_alerts.extend(pair_result["state_alerts"])
            last_dec = pair_result["decision"]
            last_reason = pair_result["reason"]
            last_risk = pair_result["risk"]
            last_symbol = symbol

        # =================================================================
        #  WRITE SHARED STATE (combined across all pairs)
        # =================================================================
        current_equity = live_equity
        positions = pos_mgr.get_current_positions()
        equity_info = pos_mgr.get_account_equity(positions)
        current_equity = equity_info["total_equity"]
        total_exposure = pos_mgr.calculate_total_exposure(positions)

        # Set start-of-day equity on first cycle of the day
        if start_of_day_equity_global is None:
            start_of_day_equity_global = current_equity

        peak_equity = pos_mgr.update_peak_equity(current_equity)

        risk = risk_mgr.get_risk_summary(
            current_equity=current_equity,
            start_of_day_equity=start_of_day_equity_global,
            peak_equity=peak_equity,
            current_exposure_usd=total_exposure,
        )

        write_state(
            cycle_count=cycle_count,
            daily_cycle_count=daily_cycle_count,
            last_decision={"symbol": last_symbol, "decision": last_dec, "reason": last_reason[:120]},
            last_orders=all_state_orders,
            alerts=all_state_alerts,
            risk_summary={
                "daily_pnl_pct": risk["daily_pnl_pct"],
                "drawdown_pct": risk["drawdown_pct"],
                "exposure_pct": risk["exposure_pct"],
                "trading_allowed": risk["trading_allowed"],
            },
            equity_snapshot={
                "total_equity": current_equity,
                "peak_equity": peak_equity,
                "cash_usd": equity_info["cash_usd"],
            },
            bot_running=True,
        )

        # Record equity for persistent P/L tracking
        record_equity(current_equity)

        # =================================================================
        #  CYCLE COMPLETE
        # =================================================================
        cycle_end = datetime.now(timezone.utc)
        elapsed = (cycle_end - cycle_start).total_seconds()

        print(f"\n  Time: {cycle_end.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  Cycle {cycle_count} completed in {elapsed:.1f}s — traded {len(all_pairs)} pairs")
        print(f"  Next cycle in 5 minutes...")
        print("=" * 60 + "\n")

        logger.info(
            f"Cycle {cycle_count} complete — "
            f"{len(all_pairs)} pairs — {elapsed:.1f}s elapsed"
        )

    except Exception as e:
        logger.error(f"Cycle {cycle_count} FAILED: {e}")
        print(f"\n  [ERROR] Cycle {cycle_count} failed: {e}")
        print(f"  Will retry next cycle in 5 minutes...\n")
        # Alert on errors too
        try:
            alerts.send_risk_alert(f"Cycle {cycle_count} FAILED: {e}")
        except Exception:
            pass  # Don't crash if Telegram also fails


# Track last grid prices per symbol for smart cancel logic
_last_grid_prices = {}


def _run_pair_cycle(symbol: str, cycle_start, live_equity: float, live_equity_info: dict) -> dict:
    """
    Run one full analysis + execution cycle for a single trading pair.

    Returns:
        dict with: state_orders, state_alerts, decision, reason, risk
    """
    global start_of_day_equity_global

    try:
        # ----- Fetch candles -----
        # Candle data: use -USD version (Coinbase has more liquidity/data on USD pairs)
        # Orders will go through the actual symbol (e.g. DOGE-USDC) so they match your balance
        candle_symbol = symbol.replace("-USDC", "-USD").replace("-USDT", "-USD")
        df_raw = fetcher.get_recent_candles(candle_symbol, granularity="FIVE_MINUTE", limit=100)

        # ----- Add technical indicators -----
        df = add_indicators(df_raw)

        # ----- Classify regime -----
        regime_result = classifier.classify(df)

        # =================================================================
        #  REGIME REPORT
        # =================================================================
        latest = df.iloc[-1]

        print("\n" + "=" * 60)
        print(f"  CYCLE {cycle_count} — REGIME ANALYSIS — {symbol}")
        print("=" * 60)

        print(f"\n  Price Data:")
        print(f"    Candles used     : {len(df)} (after indicator warmup)")
        print(f"    Latest close     : ${latest['close']:.10f}")
        print(f"    Highest price    : ${df['high'].max():.10f}")
        print(f"    Lowest price     : ${df['low'].min():.10f}")

        print(f"\n  Key Indicators (latest):")
        print(f"    RSI (14)         : {latest['rsi_14']:.1f}")
        print(f"    ADX (14)         : {latest['adx_14']:.1f}")
        print(f"    ATR %            : {latest['atr_pct']:.3f}%")
        print(f"    BB Width         : {latest['bb_width']:.2f}%")
        print(f"    MACD Histogram   : {latest['macd_hist']:.10f}")
        print(f"    Volume Ratio     : {latest['volume_ratio']:.2f}x average")

        regime_emoji = "||" if regime_result["regime"] == "RANGING" else "//"
        print(f"\n  {'=' * 50}")
        print(f"  {regime_emoji}  REGIME: {regime_result['regime']}  "
              f"(confidence: {regime_result['confidence']:.0%})")
        print(f"  {'=' * 50}")

        print(f"\n  Indicator Votes:")
        print(regime_result["details"])

        # =================================================================
        #  EXTREME VOLATILITY SAFEGUARD
        # =================================================================
        atr_pct = latest["atr_pct"]
        extreme_volatility = atr_pct > EXTREME_VOLATILITY_THRESHOLD

        if extreme_volatility:
            logger.warning(
                f"EXTREME VOLATILITY DETECTED! ATR% = {atr_pct:.3f}% "
                f"(threshold: {EXTREME_VOLATILITY_THRESHOLD}%) — "
                f"forcing WAIT mode for safety."
            )
            print(f"\n  {'!' * 50}")
            print(f"  !!!  EXTREME VOLATILITY: ATR% = {atr_pct:.3f}%")
            print(f"  !!!  Threshold: {EXTREME_VOLATILITY_THRESHOLD}%")
            print(f"  !!!  FORCING WAIT MODE — too dangerous to trade")
            print(f"  {'!' * 50}")

            alerts.send_risk_alert(
                f"EXTREME VOLATILITY on {symbol}! "
                f"ATR% = {atr_pct:.3f}% (limit: {EXTREME_VOLATILITY_THRESHOLD}%). "
                f"Bot is pausing all trading until volatility drops."
            )

        # =================================================================
        #  GRID STRATEGY REPORT
        # =================================================================
        grid = GridStrategy(df, regime_result, capital_usd=live_equity)
        grid_levels = grid.calculate_grid_levels()

        print("\n" + "=" * 60)
        print(f"  GRID STRATEGY REPORT — {symbol}")
        print("=" * 60)

        print(f"\n  Configuration:")
        print(f"    Regime           : {grid_levels['regime']}")
        print(f"    Current price    : ${grid_levels['current_price']:.10f}")
        print(f"    Grid spacing     : {grid_levels['grid_spacing_pct']:.2f}%  "
              f"(${grid_levels['grid_spacing_usd']:.10f})")
        print(f"    Capital per level: ${grid_levels['capital_per_level']:.2f}")
        print(f"    Total deployed   : ${grid_levels['total_capital_deployed']:.2f}")

        print(f"\n  BUY LEVELS (below price — we accumulate here):")
        print(f"  {'Level':<7} {'Price':<22} {'USD':<10} {'Coins':<20}")
        print(f"  {'-'*7} {'-'*22} {'-'*10} {'-'*20}")
        for b in grid_levels["buy_levels"]:
            print(
                f"  B{b['level']:<6} ${b['price']:<21.10f} "
                f"${b['size_usd']:<9.2f} {b['size_coins']:<20,.2f}"
            )

        print(f"\n  SELL LEVELS (above price — we take profit here):")
        print(f"  {'Level':<7} {'Price':<22} {'USD':<10} {'Coins':<20}")
        print(f"  {'-'*7} {'-'*22} {'-'*10} {'-'*20}")
        for s in grid_levels["sell_levels"]:
            print(
                f"  S{s['level']:<6} ${s['price']:<21.10f} "
                f"${s['size_usd']:<9.2f} {s['size_coins']:<20,.2f}"
            )

        print(f"\n  PROFIT ESTIMATE (one full grid cycle):")
        print(f"  {'-'*50}")
        print(f"    Total buy cost   : ${grid_levels['total_capital_deployed']:.2f}")
        total_sell = sum(s["size_usd"] for s in grid_levels["sell_levels"])
        print(f"    Total sell rev.  : ${total_sell:.2f}")
        print(f"    Net profit       : ${grid_levels['est_profit_per_cycle']:.4f}")
        print(f"    Return on capital: {grid_levels['est_profit_pct']:.2f}%")

        # =================================================================
        #  MOMENTUM REPORT
        # =================================================================
        predictor = MomentumPredictor(df)
        momentum_result = predictor.get_momentum_score()

        print("\n" + "=" * 60)
        print(f"  MOMENTUM ANALYSIS — {symbol}")
        print("=" * 60)

        score = momentum_result["score"]
        direction = momentum_result["direction"]
        confidence = momentum_result["confidence"]

        bar_filled = int(score * 20)
        bar_empty = 20 - bar_filled
        score_bar = "#" * bar_filled + "." * bar_empty

        print(f"\n  Score     : [{score_bar}] {score:.2f} / 1.00")
        print(f"  Direction : {direction.upper()}")
        print(f"  Confidence: {confidence}")
        print(f"  Bull pts  : {momentum_result['bullish_points']:.2f}  |  "
              f"Bear pts: {momentum_result['bearish_points']:.2f}")

        print(f"\n  Signal Breakdown:")
        for name, sig in momentum_result["signals"].items():
            val = sig.get("value", "?")
            vote = sig.get("vote", "?")
            print(f"    {name:<18}: {str(val):<12} -> {vote}")

        # =================================================================
        #  HYBRID DECISION REPORT
        # =================================================================
        hybrid = HybridStrategy(df, regime_result, grid_levels, momentum_result)
        decision = hybrid.decide_and_execute_plan()

        # --- Override decision if extreme volatility ---
        if extreme_volatility:
            decision = {
                "decision": "WAIT",
                "reason": (
                    f"FORCED WAIT — extreme volatility detected. "
                    f"ATR% = {atr_pct:.3f}% exceeds safety threshold of "
                    f"{EXTREME_VOLATILITY_THRESHOLD}%. "
                    f"Original decision was overridden for capital protection."
                ),
                "details": {
                    "strategy": "none",
                    "waiting_for": (
                        f"ATR% to drop below {EXTREME_VOLATILITY_THRESHOLD}%"
                    ),
                    "current_momentum": momentum_result["score"],
                    "current_direction": momentum_result["direction"],
                },
            }

        print("\n" + "=" * 60)
        print(f"  HYBRID DECISION — {symbol}")
        print("=" * 60)

        dec = decision["decision"]
        if dec == "GRID":
            icon = "|||"
            color_word = "GRID MODE"
        elif dec == "SCALP":
            icon = ">>>"
            color_word = "SCALP MODE"
        else:
            icon = "..."
            color_word = "WAIT MODE"

        print(f"\n  {'*' * 50}")
        print(f"  {icon}  DECISION: {color_word}")
        print(f"  {'*' * 50}")

        print(f"\n  Reason:")
        print(f"    {decision['reason']}")

        details = decision["details"]

        if dec == "GRID":
            print(f"\n  Action Plan:")
            print(f"    Place {details['num_buy_levels']} buy orders + "
                  f"{details['num_sell_levels']} sell orders")
            print(f"    Grid spacing: {details['grid_spacing_pct']:.2f}%")
            print(f"    Capital deployed: ${details['total_capital']:.2f}")
            print(f"    Est. profit/cycle: ${details['est_profit_per_cycle']:.4f}")

        elif dec == "SCALP":
            print(f"\n  Scalp Trade Plan:")
            print(f"    Side        : {details['side']}")
            print(f"    Direction   : {details['direction'].upper()}")
            print(f"    Entry price : ${details['entry_price']:.10f}")
            print(f"    Target      : ${details['target_price']:.10f}  "
                  f"(+{details['potential_profit_pct']:.3f}%)")
            print(f"    Stop loss   : ${details['stop_price']:.10f}  "
                  f"(-{details['potential_loss_pct']:.3f}%)")
            print(f"    Risk/Reward : {details['risk_reward_ratio']}")

        else:  # WAIT
            print(f"\n  Waiting for:")
            print(f"    {details['waiting_for']}")
            print(f"    Current momentum: {details['current_momentum']:.2f} "
                  f"({details['current_direction']})")

        # --- Send Telegram decision alert ---
        alerts.send_decision_alert(dec, symbol, details)

        # =================================================================
        #  RISK CHECK (quick — uses cached equity from parent)
        # =================================================================
        positions = pos_mgr.get_current_positions()
        equity_info = pos_mgr.get_account_equity(positions)
        total_exposure = pos_mgr.calculate_total_exposure(positions)
        current_equity = equity_info["total_equity"]

        if start_of_day_equity_global is None:
            start_of_day_equity_global = current_equity

        peak_equity = pos_mgr.update_peak_equity(current_equity)

        risk = risk_mgr.get_risk_summary(
            current_equity=current_equity,
            start_of_day_equity=start_of_day_equity_global,
            peak_equity=peak_equity,
            current_exposure_usd=total_exposure,
        )

        print(f"\n  Risk: exposure {risk['exposure_pct']:.1f}%, "
              f"daily P&L {risk['daily_pnl_pct']:+.2f}%, "
              f"drawdown {risk['drawdown_pct']:.2f}% — "
              f"{'OK' if risk['trading_allowed'] else 'BLOCKED'}")

        if not risk["trading_allowed"]:
            alerts.send_risk_alert(
                f"Risk limit breached on {symbol}! "
                f"Daily loss: {risk['daily_pnl_pct']:+.2f}%, "
                f"Drawdown: {risk['drawdown_pct']:.2f}%. "
                f"Trading is HALTED until limits recover."
            )

        # =================================================================
        #  ORDER EXECUTION
        # =================================================================
        if risk["trading_allowed"]:
            exec_result = executor.execute_plan(
                hybrid_decision=decision,
                symbol=symbol,
                grid_levels=grid_levels,
                current_equity=current_equity,
                current_exposure=total_exposure,
            )
        else:
            exec_result = {
                "action": "BLOCKED",
                "paper_mode": settings.PAPER_TRADING,
                "orders": [],
                "summary": "Trading halted — risk limit breached.",
            }

        mode_label = "PAPER" if exec_result["paper_mode"] else "LIVE"
        print(f"\n  [{mode_label}] {exec_result['action']}: {exec_result['summary']}")

        orders = exec_result["orders"]
        if orders:
            for o in orders:
                price_str = f"${o['price']:.10f}" if "price" in o and o["price"] else "MARKET"
                usd_str = f"${o.get('size_usd', 0):.4f}" if o.get("size_usd") else "—"
                print(f"    {o['tag']:<12} {o['side']:<6} {price_str:<22} {usd_str:<12} {o['status']}")

        # --- Send Telegram alerts ---
        alerts.send_order_alert(exec_result, symbol)

        # Record paper trading profit (estimated grid profit per cycle)
        if settings.PAPER_TRADING and dec == "GRID":
            est_profit = grid_levels.get("est_profit_per_cycle", 0)
            if est_profit > 0:
                record_paper_profit(est_profit)

        # =================================================================
        #  BUILD RETURN DATA
        # =================================================================
        state_orders = []
        for o in exec_result.get("orders", []):
            state_orders.append({
                "timestamp": o.get("timestamp", cycle_start.isoformat()),
                "symbol": symbol,
                "side": o.get("side", ""),
                "type": o.get("type", ""),
                "price": o.get("price", 0),
                "size_usd": o.get("size_usd", 0),
                "tag": o.get("tag", ""),
                "status": o.get("status", ""),
            })

        state_alerts = [{
            "timestamp": cycle_start.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "type": "decision",
            "message": f"{dec} — {decision['reason'][:100]}",
        }]
        if not risk["trading_allowed"]:
            state_alerts.append({
                "timestamp": cycle_start.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "type": "risk",
                "message": f"Risk limit breached — Daily: {risk['daily_pnl_pct']:+.2f}%, DD: {risk['drawdown_pct']:.2f}%",
            })
        if extreme_volatility:
            state_alerts.append({
                "timestamp": cycle_start.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "type": "risk",
                "message": f"Extreme volatility! ATR% = {atr_pct:.3f}% — forced WAIT",
            })

        return {
            "state_orders": state_orders,
            "state_alerts": state_alerts,
            "decision": dec,
            "reason": decision["reason"][:120],
            "risk": risk,
        }

    except Exception as e:
        logger.error(f"Pair {symbol} FAILED in cycle {cycle_count}: {e}")
        print(f"\n  [ERROR] {symbol} failed: {e}")
        return {
            "state_orders": [],
            "state_alerts": [{
                "timestamp": cycle_start.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "type": "error",
                "message": f"{symbol} cycle error: {str(e)[:80]}",
            }],
            "decision": "ERROR",
            "reason": str(e)[:120],
            "risk": None,
        }


# =====================================================================
#  BACKTEST MODE
# =====================================================================

def run_backtest_mode():
    """Run the backtester and print a beautiful results summary."""
    from utils.backtester import Backtester

    # ----- Backtest banner -----
    print("\n" + "#" * 60)
    print("#" + " " * 58 + "#")
    print("#   BACKTEST MODE                                        #")
    print("#   Hybrid Grid + Momentum Switch Bot                    #")
    print("#" + " " * 58 + "#")
    print("#" * 60)

    symbol = settings.TRADING_PAIRS[0] if settings.TRADING_PAIRS else "PEPE-USD"
    days_back = 7
    initial_capital = 1000.0

    print(f"\n  Symbol           : {symbol}")
    print(f"  Period           : last {days_back} days")
    print(f"  Starting capital : ${initial_capital:.2f}")
    print(f"  Fee assumption   : 0.6% per trade (Coinbase taker)")
    print(f"  Started at       : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()

    # ----- Run the backtest -----
    bt = Backtester()
    summary, equity_curve = bt.run_backtest(
        symbol=symbol,
        days_back=days_back,
        initial_capital=initial_capital,
    )

    if "error" in summary:
        print(f"\n  [ERROR] {summary['error']}")
        return

    # =================================================================
    #  BACKTEST RESULTS SUMMARY
    # =================================================================
    print("\n" + "=" * 60)
    print("  BACKTEST RESULTS SUMMARY")
    print("=" * 60)

    print(f"\n  Period & Data:")
    print(f"  {'-' * 50}")
    print(f"    Symbol           : {summary['symbol']}")
    print(f"    Start date       : {summary['start_date']}")
    print(f"    End date         : {summary['end_date']}")
    print(f"    Candles processed: {summary['candles_processed']:,}")
    print(f"    Total cycles     : {summary['total_cycles']:,}")

    print(f"\n  Performance:")
    print(f"  {'-' * 50}")
    print(f"    Starting capital : ${summary['initial_capital']:,.2f}")
    print(f"    Final equity     : ${summary['final_equity']:,.4f}")

    pnl = summary['total_profit_usd']
    pnl_sign = "+" if pnl >= 0 else ""
    ret = summary['total_return_pct']
    ret_sign = "+" if ret >= 0 else ""

    print(f"    Total P&L        : {pnl_sign}${pnl:,.4f}")
    print(f"    Total return     : {ret_sign}{ret:.4f}%")
    print(f"    Sharpe ratio     : {summary['sharpe_ratio']:.4f}")
    print(f"    Max drawdown     : -{summary['max_drawdown_pct']:.4f}%  "
          f"(${summary['max_drawdown_usd']:,.4f})")

    print(f"\n  Strategy Breakdown:")
    print(f"  {'-' * 50}")
    print(f"    Grid cycles      : {summary['grid_cycles']:,}  "
          f"(profit: ${summary['grid_profit_usd']:+,.4f})")
    print(f"    Scalp trades     : {summary['scalp_trades']:,}  "
          f"(profit: ${summary['scalp_profit_usd']:+,.4f})")
    print(f"    Wait cycles      : {summary['wait_cycles']:,}")
    print(f"    Risk stops       : {summary['risk_stops']:,}")

    if summary['scalp_trades'] > 0:
        print(f"\n  Scalp Detail:")
        print(f"  {'-' * 50}")
        print(f"    Wins             : {summary['scalp_wins']}")
        print(f"    Losses           : {summary['scalp_losses']}")
        print(f"    Win rate         : {summary['scalp_win_rate_pct']:.1f}%")

    print(f"\n  Timing:")
    print(f"  {'-' * 50}")
    print(f"    Backtest runtime : {summary['backtest_time_seconds']:.1f} seconds")

    # ----- Equity curve mini-chart (text-based) -----
    if len(equity_curve) > 10:
        print(f"\n  Equity Curve (text chart):")
        print(f"  {'-' * 50}")
        _print_mini_chart(equity_curve)

    # ----- Final verdict -----
    print(f"\n  {'=' * 50}")
    if pnl > 0:
        print(f"  [OK]  PROFITABLE — the strategy made money over this period")
    elif pnl == 0:
        print(f"  [--]  BREAK EVEN — no profit or loss")
    else:
        print(f"  [!!]  LOSS — the strategy lost money over this period")
    print(f"  {'=' * 50}\n")

    logger.info("Backtest completed")


def run_export_mode():
    """Export current performance data to files."""
    from utils.performance_exporter import PerformanceExporter

    print("\n" + "#" * 60)
    print("#" + " " * 58 + "#")
    print("#   EXPORT MODE                                          #")
    print("#   Hybrid Grid + Momentum Switch Bot                    #")
    print("#" + " " * 58 + "#")
    print("#" * 60)

    mode_str = "PAPER (simulated)" if settings.PAPER_TRADING else "LIVE"
    print(f"\n  Mode           : {mode_str}")
    print(f"  Trading pairs  : {settings.TRADING_PAIRS}")
    print(f"  Started at     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"\n  Connecting to Coinbase and running pipeline...")

    exporter = PerformanceExporter()
    result = exporter.export()

    print(f"\n  Files generated:")
    print(f"    {result['summary_path']}")
    print(f"    {result['csv_path']}")

    master = result["master"]
    print(f"\n  Quick Stats:")
    print(f"    Total equity   : ${master['total_equity']:,.4f}")
    print(f"    Daily P&L      : ${master['daily_pnl_usd']:+,.4f}")
    print(f"    Grid cycles    : {master['total_grid_cycles']}")
    print(f"    Scalp trades   : {master['total_scalp_trades']}")
    print(f"    Sharpe estimate: {master['sharpe_estimate']:.4f}")

    print(f"\n  Export complete -- files saved to exports/ folder")
    print("=" * 60 + "\n")

    logger.info("Export completed successfully.")


def _print_mini_chart(equity_curve: "pd.Series"):
    """Print a simple text-based equity curve chart."""
    # Sample down to ~40 points for display
    if len(equity_curve) > 40:
        step = len(equity_curve) // 40
        sampled = equity_curve.iloc[::step]
    else:
        sampled = equity_curve

    values = sampled.values
    min_val = values.min()
    max_val = values.max()
    val_range = max_val - min_val

    if val_range == 0:
        val_range = 1  # Avoid division by zero

    chart_width = 40
    for val in values:
        position = int(((val - min_val) / val_range) * chart_width)
        bar = " " * position + "*"
        print(f"    ${val:>10,.2f} |{bar}")

    print(f"    {'':>10} +{'-' * (chart_width + 1)}")
    print(f"    {'':>10}  ${min_val:,.2f}{' ' * (chart_width - 16)}${max_val:,.2f}")


# =====================================================================
#  STARTUP + SCHEDULED LOOP
# =====================================================================

if __name__ == "__main__":

    # ----- Check for --backtest flag -----
    if "--backtest" in sys.argv:
        run_backtest_mode()
        sys.exit(0)

    # ----- Check for --export flag -----
    if "--export" in sys.argv:
        run_export_mode()
        sys.exit(0)

    # ----- Normal live mode below -----

    # ----- PRODUCTION-READY STARTUP BANNER -----
    mode_str = "PAPER (simulated)" if settings.PAPER_TRADING else "LIVE (real money!)"
    tg_str = "ON" if settings.ENABLE_TELEGRAM_ALERTS else "OFF"

    print("\n" + "#" * 60)
    print("#" + " " * 58 + "#")
    print("#   HYBRID GRID + MOMENTUM SWITCH BOT                    #")
    print("#   Coinbase Advanced Trade — Spot Only                   #")
    print("#" + " " * 58 + "#")
    print("#   BOT FULLY ARMED — PAPER/LIVE READY                   #")
    print("#" + " " * 58 + "#")
    print("#" * 60)

    print(f"\n  Mode              : {mode_str}")
    print(f"  Telegram alerts   : {tg_str}")
    print(f"  Trading pairs     : {settings.TRADING_PAIRS}")
    print(f"  Max position      : ${settings.MAX_POSITION_SIZE_USD:.2f}")
    print(f"  Risk limits       : {settings.MAX_POSITION_PCT}% pos / "
          f"{settings.DAILY_LOSS_LIMIT_PCT}% daily / "
          f"{settings.MAX_DRAWDOWN_PCT}% drawdown")
    print(f"  Extreme vol guard : ATR% > {EXTREME_VOLATILITY_THRESHOLD}% = force WAIT")
    print(f"  Cycle interval    : every 5 minutes")
    print(f"  Started at        : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"\n  Press Ctrl+C to stop the bot.\n")

    # ----- Initialize shared objects -----
    initialize()

    # ----- Send Telegram startup alert -----
    alerts.send_startup_alert()

    # ----- Schedule the trading cycle every 5 minutes -----
    schedule.every(5).minutes.do(run_full_trading_cycle)

    # ----- Run the first cycle immediately -----
    logger.info("Running first cycle immediately...")
    run_full_trading_cycle()

    # ----- Loop: wait for next scheduled cycle -----
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("  BOT STOPPED — Graceful shutdown")
        print(f"  Total cycles completed: {cycle_count}")
        print(f"  Stopped at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print("=" * 60 + "\n")
        logger.info(f"Bot stopped by user after {cycle_count} cycles.")

        # Send shutdown alert + write state
        try:
            alerts.send_risk_alert(
                f"Bot STOPPED by user. "
                f"Total cycles completed: {cycle_count}."
            )
        except Exception:
            pass
        write_shutdown()
