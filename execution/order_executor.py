"""
execution/order_executor.py — Places real or simulated orders on Coinbase.

This is where decisions become actions. The OrderExecutor takes the hybrid
decision and translates it into actual limit/market orders on Coinbase.

Safety features:
    1. PAPER_TRADING mode — logs what it WOULD do, places no real orders
    2. Risk checks BEFORE every order — blocked if limits exceeded
    3. Unique client_order_id per order — prevents accidental duplicates
    4. Full logging of every order attempt, success, and failure

Usage:
    from execution.order_executor import OrderExecutor
    executor = OrderExecutor(client, risk_mgr)
    result = executor.execute_plan(decision, grid_levels=levels)
"""

import uuid
from datetime import datetime, timezone

from config import settings
from utils.logger import logger


class OrderExecutor:
    """
    Translates hybrid strategy decisions into Coinbase orders.

    Supports two modes:
        PAPER (default) — simulates orders, logs everything, no real money
        LIVE            — places real orders on Coinbase Advanced Trade
    """

    def __init__(self, client, risk_manager):
        """
        Args:
            client:       An initialized CoinbaseClient.
            risk_manager: An initialized RiskManager.
        """
        self.client = client
        self.risk_mgr = risk_manager
        self.paper_mode = settings.PAPER_TRADING

        mode_str = "PAPER (simulated)" if self.paper_mode else "LIVE (real money!)"
        logger.info(f"OrderExecutor initialized — mode: {mode_str}")

    # ------------------------------------------------------------------
    #  MAIN ENTRY POINT
    # ------------------------------------------------------------------

    def execute_plan(
        self,
        hybrid_decision: dict,
        symbol: str = "PEPE-USD",
        grid_levels: dict | None = None,
        current_equity: float = 0.0,
        current_exposure: float = 0.0,
    ) -> dict:
        """
        Execute the hybrid strategy decision.

        Args:
            hybrid_decision:  Output from HybridStrategy.decide_and_execute_plan().
            symbol:           Trading pair (e.g. "PEPE-USD").
            grid_levels:      Output from GridStrategy.calculate_grid_levels().
            current_equity:   Total account equity for risk checks.
            current_exposure: Current USD exposure in this coin.

        Returns:
            dict with:
                action:       "GRID" / "SCALP" / "WAIT" / "BLOCKED"
                paper_mode:   bool
                orders:       list of order dicts (placed or simulated)
                summary:      human-readable summary
        """
        decision = hybrid_decision["decision"]
        details = hybrid_decision["details"]

        # ----- WAIT = do nothing -----
        if decision == "WAIT":
            logger.info("Decision is WAIT — no orders to place")
            return {
                "action": "WAIT",
                "paper_mode": self.paper_mode,
                "orders": [],
                "summary": "No action — waiting for stronger signal.",
            }

        # ----- GRID mode -----
        if decision == "GRID" and grid_levels:
            return self._execute_grid(
                symbol, grid_levels, current_equity, current_exposure
            )

        # ----- SCALP mode -----
        if decision == "SCALP":
            return self._execute_scalp(
                symbol, details, current_equity, current_exposure
            )

        # Fallback
        logger.warning(f"Unexpected decision: {decision}")
        return {
            "action": "BLOCKED",
            "paper_mode": self.paper_mode,
            "orders": [],
            "summary": f"Unexpected decision type: {decision}",
        }

    # ------------------------------------------------------------------
    #  GRID EXECUTION
    # ------------------------------------------------------------------

    def _execute_grid(
        self,
        symbol: str,
        grid_levels: dict,
        current_equity: float,
        current_exposure: float,
    ) -> dict:
        """Place 5 buy + 5 sell limit orders for the grid strategy."""
        orders = []
        total_cost = grid_levels["total_capital_deployed"]

        # Risk check: is the total grid cost within position limits?
        if current_equity > 0:
            size_ok = self.risk_mgr.check_position_size(
                proposed_usd=total_cost,
                current_exposure_usd=current_exposure,
                total_capital=current_equity,
            )
            if not size_ok:
                logger.warning("Grid BLOCKED by risk manager — position too large")
                return {
                    "action": "BLOCKED",
                    "paper_mode": self.paper_mode,
                    "orders": [],
                    "summary": (
                        f"Grid blocked — deploying ${total_cost:.2f} would exceed "
                        f"{self.risk_mgr.max_position_pct}% position limit."
                    ),
                }

        # ----- Place BUY limit orders -----
        for level in grid_levels["buy_levels"]:
            order = self._place_limit_order(
                symbol=symbol,
                side="BUY",
                price=level["price"],
                size_coins=level["size_coins"],
                tag=f"GRID-B{level['level']}",
            )
            orders.append(order)

        # ----- Place SELL limit orders -----
        for level in grid_levels["sell_levels"]:
            order = self._place_limit_order(
                symbol=symbol,
                side="SELL",
                price=level["price"],
                size_coins=level["size_coins"],
                tag=f"GRID-S{level['level']}",
            )
            orders.append(order)

        placed = sum(1 for o in orders if o["status"] == "placed")
        simulated = sum(1 for o in orders if o["status"] == "simulated")

        summary = (
            f"Grid: {placed} placed, {simulated} simulated — "
            f"{len(grid_levels['buy_levels'])} buys + "
            f"{len(grid_levels['sell_levels'])} sells"
        )
        logger.info(summary)

        return {
            "action": "GRID",
            "paper_mode": self.paper_mode,
            "orders": orders,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    #  SCALP EXECUTION
    # ------------------------------------------------------------------

    def _execute_scalp(
        self,
        symbol: str,
        scalp_plan: dict,
        current_equity: float,
        current_exposure: float,
    ) -> dict:
        """Place a market order for the scalp entry."""
        orders = []

        side = scalp_plan.get("side", "BUY")
        entry_price = scalp_plan["entry_price"]

        # For scalp, use a fraction of the grid capital
        # (25% of max position = same as one grid level set)
        scalp_usd = settings.MAX_POSITION_SIZE_USD * 0.25
        scalp_coins = scalp_usd / entry_price

        # Risk check
        if current_equity > 0:
            size_ok = self.risk_mgr.check_position_size(
                proposed_usd=scalp_usd,
                current_exposure_usd=current_exposure,
                total_capital=current_equity,
            )
            if not size_ok:
                logger.warning("Scalp BLOCKED by risk manager — position too large")
                return {
                    "action": "BLOCKED",
                    "paper_mode": self.paper_mode,
                    "orders": [],
                    "summary": (
                        f"Scalp blocked — ${scalp_usd:.2f} would exceed "
                        f"{self.risk_mgr.max_position_pct}% position limit."
                    ),
                }

        # Place market order for entry
        order = self._place_market_order(
            symbol=symbol,
            side=side,
            size_usd=scalp_usd if side == "BUY" else None,
            size_coins=scalp_coins if side == "SELL" else None,
            tag=f"SCALP-{side}",
        )
        orders.append(order)

        # Log target and stop for reference (actual stop/target orders
        # will be managed by the live loop in Step 8)
        logger.info(
            f"Scalp target: ${scalp_plan['target_price']:.10f} | "
            f"Stop: ${scalp_plan['stop_price']:.10f}"
        )

        placed = sum(1 for o in orders if o["status"] == "placed")
        simulated = sum(1 for o in orders if o["status"] == "simulated")

        summary = (
            f"Scalp: {placed} placed, {simulated} simulated — "
            f"{side} ${scalp_usd:.2f} of {symbol}"
        )
        logger.info(summary)

        return {
            "action": "SCALP",
            "paper_mode": self.paper_mode,
            "orders": orders,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    #  LOW-LEVEL ORDER METHODS
    # ------------------------------------------------------------------

    def _place_limit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        size_coins: float,
        tag: str = "",
    ) -> dict:
        """
        Place a single limit order (GTC = Good Till Cancelled).

        In paper mode: logs and returns a simulated order.
        In live mode:  calls the Coinbase SDK.
        """
        order_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()

        # Format for Coinbase: price and size as strings
        price_str = f"{price:.10f}"
        size_str = f"{size_coins:.10f}"

        order_record = {
            "order_id": order_id,
            "tag": tag,
            "type": "limit_gtc",
            "side": side,
            "symbol": symbol,
            "price": price,
            "size_coins": size_coins,
            "size_usd": price * size_coins,
            "timestamp": timestamp,
            "status": "simulated",
            "coinbase_order_id": None,
        }

        if self.paper_mode:
            order_record["status"] = "simulated"
            logger.info(
                f"[PAPER] {tag} {side} {size_str} {symbol} "
                f"@ ${price_str} (${price * size_coins:.4f})"
            )
        else:
            try:
                if side == "BUY":
                    response = self.client.client.limit_order_gtc_buy(
                        client_order_id=order_id,
                        product_id=symbol,
                        base_size=size_str,
                        limit_price=price_str,
                    )
                else:
                    response = self.client.client.limit_order_gtc_sell(
                        client_order_id=order_id,
                        product_id=symbol,
                        base_size=size_str,
                        limit_price=price_str,
                    )

                if response.get("success"):
                    cb_order_id = response["success_response"]["order_id"]
                    order_record["status"] = "placed"
                    order_record["coinbase_order_id"] = cb_order_id
                    logger.info(
                        f"[LIVE] {tag} {side} {size_str} {symbol} "
                        f"@ ${price_str} — order_id: {cb_order_id}"
                    )
                else:
                    error = response.get("error_response", {})
                    order_record["status"] = "failed"
                    order_record["error"] = str(error)
                    logger.error(
                        f"[LIVE] {tag} FAILED: {error}"
                    )
            except Exception as e:
                order_record["status"] = "failed"
                order_record["error"] = str(e)
                logger.error(f"[LIVE] {tag} EXCEPTION: {e}")

        return order_record

    def _place_market_order(
        self,
        symbol: str,
        side: str,
        size_usd: float | None = None,
        size_coins: float | None = None,
        tag: str = "",
    ) -> dict:
        """
        Place a single market order (executes immediately at best price).

        For BUY:  specify size_usd (quote_size — how much USD to spend)
        For SELL: specify size_coins (base_size — how many coins to sell)
        """
        order_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()

        order_record = {
            "order_id": order_id,
            "tag": tag,
            "type": "market",
            "side": side,
            "symbol": symbol,
            "size_usd": size_usd,
            "size_coins": size_coins,
            "timestamp": timestamp,
            "status": "simulated",
            "coinbase_order_id": None,
        }

        if self.paper_mode:
            order_record["status"] = "simulated"
            if side == "BUY":
                logger.info(
                    f"[PAPER] {tag} MARKET BUY ${size_usd:.4f} of {symbol}"
                )
            else:
                logger.info(
                    f"[PAPER] {tag} MARKET SELL {size_coins:.10f} {symbol}"
                )
        else:
            try:
                if side == "BUY":
                    response = self.client.client.market_order_buy(
                        client_order_id=order_id,
                        product_id=symbol,
                        quote_size=f"{size_usd:.2f}",
                    )
                else:
                    response = self.client.client.market_order_sell(
                        client_order_id=order_id,
                        product_id=symbol,
                        base_size=f"{size_coins:.10f}",
                    )

                if response.get("success"):
                    cb_order_id = response["success_response"]["order_id"]
                    order_record["status"] = "placed"
                    order_record["coinbase_order_id"] = cb_order_id
                    logger.info(
                        f"[LIVE] {tag} MARKET {side} — order_id: {cb_order_id}"
                    )
                else:
                    error = response.get("error_response", {})
                    order_record["status"] = "failed"
                    order_record["error"] = str(error)
                    logger.error(f"[LIVE] {tag} MARKET FAILED: {error}")

            except Exception as e:
                order_record["status"] = "failed"
                order_record["error"] = str(e)
                logger.error(f"[LIVE] {tag} MARKET EXCEPTION: {e}")

        return order_record
