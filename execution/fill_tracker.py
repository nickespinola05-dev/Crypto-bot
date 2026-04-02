"""
execution/fill_tracker.py — Tracks order fills on Coinbase and manages grid pairs.

The CRITICAL missing piece: when a grid BUY fills, we place a SELL at the target
price (buy_price + spread). When a SELL fills, we record the realized profit.

This turns the grid from "place and pray" into an actual money-making machine.

Usage:
    from execution.fill_tracker import FillTracker
    tracker = FillTracker(client)
    results = tracker.check_and_manage_fills()
"""

import json
import os
import uuid
from datetime import datetime, timezone

from config import settings
from utils.logger import logger


STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "grid_fills.json")


class FillTracker:
    """
    Tracks grid order fills and places matching counter-orders.

    Flow:
        1. Bot places grid BUY orders → we store them as "pending_buys"
        2. Each cycle, check_and_manage_fills() queries Coinbase for status
        3. When a BUY fills → place a SELL at (buy_price + 2*spacing)
        4. When that SELL fills → record realized profit
        5. Rinse and repeat
    """

    def __init__(self, client):
        self.client = client
        self.state = self._load_state()

    # ------------------------------------------------------------------
    #  STATE PERSISTENCE
    # ------------------------------------------------------------------

    def _load_state(self) -> dict:
        """Load fill tracking state from disk."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "pending_buys": {},     # coinbase_order_id -> order info
            "pending_sells": {},    # coinbase_order_id -> order info (with buy reference)
            "realized_profits": [], # list of completed round-trips
            "total_realized_pnl": 0.0,
            "total_fees_paid": 0.0,
            "total_round_trips": 0,
        }

    def _save_state(self):
        """Persist state to disk."""
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2, default=str)

    # ------------------------------------------------------------------
    #  REGISTER NEW ORDERS (called by order_executor after placing)
    # ------------------------------------------------------------------

    def register_buy(self, coinbase_order_id: str, symbol: str, price: float,
                     size_coins: float, size_usd: float, grid_level: int,
                     grid_spacing_pct: float):
        """Register a newly placed grid BUY order for tracking."""
        if not coinbase_order_id or coinbase_order_id == "None":
            return

        self.state["pending_buys"][coinbase_order_id] = {
            "symbol": symbol,
            "side": "BUY",
            "price": price,
            "size_coins": size_coins,
            "size_usd": size_usd,
            "grid_level": grid_level,
            "grid_spacing_pct": grid_spacing_pct,
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_state()
        logger.info(f"[FILL_TRACKER] Registered BUY {coinbase_order_id[:8]} "
                     f"{symbol} {size_coins:.2f} coins @ ${price:.8f}")

    def register_sell(self, coinbase_order_id: str, symbol: str, price: float,
                      size_coins: float, size_usd: float, buy_order_id: str = None,
                      buy_price: float = 0.0):
        """Register a newly placed grid SELL order for tracking."""
        if not coinbase_order_id or coinbase_order_id == "None":
            return

        self.state["pending_sells"][coinbase_order_id] = {
            "symbol": symbol,
            "side": "SELL",
            "price": price,
            "size_coins": size_coins,
            "size_usd": size_usd,
            "buy_order_id": buy_order_id,
            "buy_price": buy_price,
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_state()
        logger.info(f"[FILL_TRACKER] Registered SELL {coinbase_order_id[:8]} "
                     f"{symbol} {size_coins:.2f} coins @ ${price:.8f}")

    # ------------------------------------------------------------------
    #  CHECK FILLS AND MANAGE COUNTER-ORDERS
    # ------------------------------------------------------------------

    def check_and_manage_fills(self) -> dict:
        """
        Main method — call once per cycle.

        1. Check all pending buys: if filled, place a sell at target price
        2. Check all pending sells: if filled, record realized profit
        3. Clean up cancelled/expired orders

        Returns:
            dict with: buys_filled, sells_filled, profit_this_cycle,
                       new_sells_placed, orders_cleaned
        """
        results = {
            "buys_filled": 0,
            "sells_filled": 0,
            "profit_this_cycle": 0.0,
            "fees_this_cycle": 0.0,
            "new_sells_placed": 0,
            "orders_cleaned": 0,
        }

        # --- Check pending BUYS ---
        buy_ids_to_remove = []
        for order_id, info in list(self.state["pending_buys"].items()):
            status = self._get_order_status(order_id)

            if status == "FILLED":
                logger.info(f"[FILL_TRACKER] BUY FILLED: {order_id[:8]} "
                             f"{info['symbol']} @ ${info['price']:.8f}")
                results["buys_filled"] += 1

                # Calculate sell target (AGGRESSIVE MODE):
                # Need to cover: 0.40% maker fee on buy + 0.40% maker fee on sell = 0.80%
                # Aggressive minimum: 1.20% spread → 0.40% net profit (thin but fast fills)
                # Formula: counter-sell = max(spacing × 3, 1.20%) above buy price
                spacing = info.get("grid_spacing_pct", 0.40)
                min_spread_pct = 1.2  # 0.40% net after 0.80% fees — aggressive
                sell_spread = max(spacing * 3, min_spread_pct)
                sell_price = info["price"] * (1 + sell_spread / 100)

                # Place the matching sell order
                sell_order_id = self._place_counter_sell(
                    symbol=info["symbol"],
                    price=sell_price,
                    size_coins=info["size_coins"],
                    buy_order_id=order_id,
                    buy_price=info["price"],
                )
                if sell_order_id:
                    results["new_sells_placed"] += 1

                buy_ids_to_remove.append(order_id)

            elif status in ("CANCELLED", "EXPIRED", "FAILED"):
                buy_ids_to_remove.append(order_id)
                results["orders_cleaned"] += 1

        for oid in buy_ids_to_remove:
            self.state["pending_buys"].pop(oid, None)

        # --- Check pending SELLS ---
        sell_ids_to_remove = []
        for order_id, info in list(self.state["pending_sells"].items()):
            status = self._get_order_status(order_id)

            if status == "FILLED":
                logger.info(f"[FILL_TRACKER] SELL FILLED: {order_id[:8]} "
                             f"{info['symbol']} @ ${info['price']:.8f}")
                results["sells_filled"] += 1

                # Calculate realized profit
                buy_cost = info["buy_price"] * info["size_coins"]
                sell_revenue = info["price"] * info["size_coins"]
                est_fees = (buy_cost + sell_revenue) * 0.004  # ~0.40% maker fee per side
                profit = sell_revenue - buy_cost - est_fees

                results["profit_this_cycle"] += profit
                results["fees_this_cycle"] += est_fees

                self.state["total_realized_pnl"] += profit
                self.state["total_fees_paid"] += est_fees
                self.state["total_round_trips"] += 1

                self.state["realized_profits"].append({
                    "symbol": info["symbol"],
                    "buy_price": info["buy_price"],
                    "sell_price": info["price"],
                    "size_coins": info["size_coins"],
                    "gross_profit": round(sell_revenue - buy_cost, 6),
                    "fees": round(est_fees, 6),
                    "net_profit": round(profit, 6),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })

                # Keep only last 100 round-trips
                if len(self.state["realized_profits"]) > 100:
                    self.state["realized_profits"] = self.state["realized_profits"][-100:]

                logger.info(
                    f"[FILL_TRACKER] ROUND-TRIP COMPLETE: {info['symbol']} "
                    f"buy@${info['buy_price']:.8f} sell@${info['price']:.8f} "
                    f"profit=${profit:+.6f} (fees=${est_fees:.6f})"
                )

                sell_ids_to_remove.append(order_id)

            elif status in ("CANCELLED", "EXPIRED", "FAILED"):
                sell_ids_to_remove.append(order_id)
                results["orders_cleaned"] += 1

        for oid in sell_ids_to_remove:
            self.state["pending_sells"].pop(oid, None)

        self._save_state()

        # Log summary
        if results["buys_filled"] or results["sells_filled"]:
            logger.info(
                f"[FILL_TRACKER] Cycle summary: "
                f"{results['buys_filled']} buys filled, "
                f"{results['sells_filled']} sells filled, "
                f"profit=${results['profit_this_cycle']:+.6f}, "
                f"{results['new_sells_placed']} new sells placed"
            )
            print(f"\n  [FILLS] {results['buys_filled']} buys filled → "
                  f"{results['new_sells_placed']} counter-sells placed | "
                  f"{results['sells_filled']} sells filled → "
                  f"${results['profit_this_cycle']:+.4f} profit")

        return results

    # ------------------------------------------------------------------
    #  HELPERS
    # ------------------------------------------------------------------

    def _get_order_status(self, order_id: str) -> str:
        """Query Coinbase for the current status of an order."""
        try:
            response = self.client.client.get_order(order_id=order_id)
            order = response if not hasattr(response, 'order') else response.order
            status = getattr(order, 'status', None)
            if status:
                return str(status).upper()
            # Try dict access
            if isinstance(order, dict):
                return order.get("status", "UNKNOWN").upper()
            return "UNKNOWN"
        except Exception as e:
            logger.warning(f"[FILL_TRACKER] Could not check order {order_id[:8]}: {e}")
            return "UNKNOWN"

    def _place_counter_sell(self, symbol: str, price: float, size_coins: float,
                            buy_order_id: str, buy_price: float) -> str | None:
        """Place a limit sell order as the counter to a filled buy."""
        order_id = str(uuid.uuid4())[:8]

        # Get precision
        precision = self.client.get_product_precision(symbol)
        price_dec = precision["price_decimals"]
        size_dec = precision["size_decimals"]

        price = round(price, price_dec)
        size_coins = round(size_coins, size_dec)
        price_str = f"{price:.{price_dec}f}"
        size_str = f"{size_coins:.{size_dec}f}"

        try:
            response = self.client.client.limit_order_gtc_sell(
                client_order_id=order_id,
                product_id=symbol,
                base_size=size_str,
                limit_price=price_str,
            )

            success = getattr(response, 'success', None)
            success_resp = getattr(response, 'success_response', None)

            if success and success_resp:
                sr = success_resp if isinstance(success_resp, dict) else (
                    success_resp.__dict__ if hasattr(success_resp, '__dict__') else {})
                cb_order_id = sr.get("order_id", getattr(success_resp, 'order_id', 'unknown'))

                # Register for tracking
                self.register_sell(
                    coinbase_order_id=cb_order_id,
                    symbol=symbol,
                    price=price,
                    size_coins=size_coins,
                    size_usd=price * size_coins,
                    buy_order_id=buy_order_id,
                    buy_price=buy_price,
                )

                logger.info(
                    f"[FILL_TRACKER] Counter-SELL placed: {cb_order_id[:8]} "
                    f"{symbol} {size_str} @ ${price_str}"
                )
                return cb_order_id
            else:
                error_resp = getattr(response, 'error_response', None)
                logger.error(f"[FILL_TRACKER] Counter-SELL FAILED: {error_resp}")
                return None

        except Exception as e:
            logger.error(f"[FILL_TRACKER] Counter-SELL EXCEPTION: {e}")
            return None

    # ------------------------------------------------------------------
    #  SUMMARY
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        """Get fill tracker summary for dashboard."""
        return {
            "pending_buys": len(self.state["pending_buys"]),
            "pending_sells": len(self.state["pending_sells"]),
            "total_realized_pnl": round(self.state["total_realized_pnl"], 6),
            "total_fees_paid": round(self.state["total_fees_paid"], 6),
            "total_round_trips": self.state["total_round_trips"],
            "recent_profits": self.state["realized_profits"][-10:],
        }
