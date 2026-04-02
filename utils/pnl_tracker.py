"""
utils/pnl_tracker.py — Persistent P/L tracking for paper AND live trading.

In PAPER mode: tracks simulated equity by accumulating estimated profits
from each cycle's grid orders (since real Coinbase balance doesn't change).

In LIVE mode: tracks real Coinbase equity.

Stores data in state/pnl_history.json.

Usage:
    from utils.pnl_tracker import record_equity, record_paper_profit, get_summary
    record_equity(979.36)              # call each cycle (real balance)
    record_paper_profit(0.0512)        # call each cycle in paper mode (est. grid profit)
    summary = get_summary()            # read from dashboard
"""

import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")
PNL_FILE = os.path.join(STATE_DIR, "pnl_history.json")
LOCAL_TZ = ZoneInfo("America/New_York")


def _load() -> dict:
    """Load persisted P/L data from disk."""
    try:
        with open(PNL_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save(data: dict):
    """Save P/L data to disk."""
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        with open(PNL_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def record_equity(current_equity: float):
    """
    Record the current equity snapshot. Call this every bot cycle.
    Tracks starting equity, daily snapshots, and all-time P/L.
    """
    data = _load()
    now = datetime.now(LOCAL_TZ)
    today_str = now.strftime("%Y-%m-%d")

    # First ever run — set the starting equity
    if "starting_equity" not in data:
        data["starting_equity"] = current_equity
        data["start_date"] = today_str

    # Daily tracking
    if "days" not in data:
        data["days"] = {}

    if today_str not in data["days"]:
        # New day — record opening equity
        data["days"][today_str] = {
            "open_equity": current_equity,
            "high_equity": current_equity,
            "low_equity": current_equity,
            "close_equity": current_equity,
            "first_update": now.isoformat(),
            "last_update": now.isoformat(),
        }
    else:
        day = data["days"][today_str]
        day["close_equity"] = current_equity
        day["high_equity"] = max(day.get("high_equity", current_equity), current_equity)
        day["low_equity"] = min(day.get("low_equity", current_equity), current_equity)
        day["last_update"] = now.isoformat()

    # Current snapshot
    data["last_equity"] = current_equity
    data["last_update"] = now.isoformat()

    _save(data)


def record_paper_profit(cycle_profit: float):
    """
    Record simulated profit from a paper trading cycle.
    Accumulates into paper_profit_total and paper_profit_today.
    This is the estimated grid profit per cycle (from est_profit_per_cycle).
    """
    data = _load()
    now = datetime.now(LOCAL_TZ)
    today_str = now.strftime("%Y-%m-%d")

    # Accumulate all-time paper profit
    data["paper_profit_total"] = data.get("paper_profit_total", 0.0) + cycle_profit

    # Accumulate daily paper profit
    if "paper_daily" not in data:
        data["paper_daily"] = {}

    if today_str not in data["paper_daily"]:
        data["paper_daily"][today_str] = {
            "profit": cycle_profit,
            "cycles": 1,
        }
    else:
        data["paper_daily"][today_str]["profit"] += cycle_profit
        data["paper_daily"][today_str]["cycles"] += 1

    data["paper_last_update"] = now.isoformat()
    print(f"[DEBUG] Paper profit this cycle: ${cycle_profit:.4f} | "
          f"Today total: ${data['paper_daily'][today_str]['profit']:.4f} | "
          f"All-time: ${data['paper_profit_total']:.4f}")

    _save(data)


def get_summary() -> dict:
    """
    Get P/L summary for dashboard display.

    In paper mode, uses accumulated paper_profit values.
    Falls back to real equity deltas for live mode.

    Returns:
        dict with:
            starting_equity: float
            current_equity: float
            daily_pnl: float          (today's P/L in USD)
            daily_pnl_pct: float      (today's P/L as %)
            alltime_pnl: float        (all-time P/L in USD)
            alltime_pnl_pct: float    (all-time P/L as %)
            today_open: float
            days_trading: int
    """
    data = _load()

    if not data:
        return {
            "starting_equity": 0,
            "current_equity": 0,
            "daily_pnl": 0,
            "daily_pnl_pct": 0,
            "alltime_pnl": 0,
            "alltime_pnl_pct": 0,
            "today_open": 0,
            "days_trading": 0,
        }

    starting = data.get("starting_equity", 0)
    current = data.get("last_equity", starting)

    now = datetime.now(LOCAL_TZ)
    today_str = now.strftime("%Y-%m-%d")

    # Check actual setting to determine paper vs live mode
    from config import settings
    is_paper = settings.PAPER_TRADING

    if is_paper and "paper_profit_total" in data:
        # Paper mode: use accumulated simulated profits
        alltime_pnl = data.get("paper_profit_total", 0)
        daily_data = data.get("paper_daily", {}).get(today_str, {})
        daily_pnl = daily_data.get("profit", 0)
        # Paper equity = starting + all accumulated paper profit
        paper_equity = starting + alltime_pnl
        current = paper_equity
    else:
        # Live mode: use actual equity changes from Coinbase
        today_data = data.get("days", {}).get(today_str, {})
        today_open = today_data.get("open_equity", current)
        daily_pnl = current - today_open
        alltime_pnl = current - starting

    daily_pnl_pct = (daily_pnl / starting * 100) if starting > 0 else 0
    alltime_pnl_pct = (alltime_pnl / starting * 100) if starting > 0 else 0

    days_trading = len(data.get("days", {}))

    return {
        "starting_equity": round(starting, 4),
        "current_equity": round(current, 4),
        "daily_pnl": round(daily_pnl, 4),
        "daily_pnl_pct": round(daily_pnl_pct, 4),
        "alltime_pnl": round(alltime_pnl, 4),
        "alltime_pnl_pct": round(alltime_pnl_pct, 4),
        "today_open": round(starting, 4),
        "days_trading": days_trading,
    }
