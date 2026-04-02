"""
utils/shared_state.py — Lightweight IPC between main.py and dashboard.py.

main.py writes bot state to state/bot_state.json after every cycle.
dashboard.py reads it every 5 seconds to display live info.

The file is small (<50KB) and atomic writes prevent corruption.
"""

import os
import json
import tempfile
from datetime import datetime, timezone

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")
STATE_FILE = os.path.join(STATE_DIR, "bot_state.json")
MAX_ORDERS = 20   # keep last 20 orders (a few cycles of history)
MAX_ALERTS = 30   # keep last 30 alerts


def write_state(
    cycle_count: int = 0,
    daily_cycle_count: int = 0,
    last_decision: dict | None = None,
    last_orders: list | None = None,
    alerts: list | None = None,
    risk_summary: dict | None = None,
    equity_snapshot: dict | None = None,
    bot_running: bool = True,
    extra: dict | None = None,
):
    """
    Atomically write the bot's current state to disk.
    Called by main.py at the end of each trading cycle.
    """
    os.makedirs(STATE_DIR, exist_ok=True)

    # Read existing to preserve order/alert history
    existing = read_state()
    old_orders = existing.get("orders_history", [])
    old_alerts = existing.get("alerts_history", [])

    # Merge new orders
    new_orders = last_orders or []
    all_orders = new_orders + old_orders
    all_orders = all_orders[:MAX_ORDERS]

    # Merge new alerts
    new_alerts = alerts or []
    all_alerts = new_alerts + old_alerts
    all_alerts = all_alerts[:MAX_ALERTS]

    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bot_running": bot_running,
        "cycle_count": cycle_count,
        "daily_cycle_count": daily_cycle_count,
        "last_decision": last_decision,
        "orders_history": all_orders,
        "alerts_history": all_alerts,
        "risk_summary": risk_summary,
        "equity_snapshot": equity_snapshot,
    }
    if extra:
        state.update(extra)

    # Atomic write: write to temp file then rename
    try:
        fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, default=str)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        # If atomic write fails, try direct write
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, default=str)
        except Exception:
            pass


def read_state() -> dict:
    """
    Read the bot's current state from disk.
    Called by dashboard.py every 5 seconds.
    Returns empty dict if file doesn't exist or is corrupted.
    """
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def write_shutdown():
    """Mark the bot as stopped."""
    existing = read_state()
    existing["bot_running"] = False
    existing["shutdown_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(existing, f, default=str)
    except Exception:
        pass
