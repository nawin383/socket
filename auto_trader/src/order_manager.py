"""
Order placement: a marketable-limit order first (to bound slippage on
option strikes that can be thin), falling back to a market order if it
doesn't fill in time. In "paper" mode nothing is sent to the broker —
fills are simulated at the current LTP so the whole strategy can be
dry-run tested first.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class OrderError(Exception):
    pass


class OrderManager:
    def __init__(self, kite, config: dict, mode: str = "paper"):
        self.kite = kite
        self.config = config
        self.mode = mode  # "paper" or "live"

    @staticmethod
    def _round_tick(price: float, tick_size: float = 0.05) -> float:
        return round(price / tick_size) * tick_size

    def sell_to_open(self, tradingsymbol: str, exchange: str, quantity: int,
                      ltp: float, product: str) -> float:
        return self._execute("SELL", tradingsymbol, exchange, quantity, ltp, product)

    def buy_to_close(self, tradingsymbol: str, exchange: str, quantity: int,
                      ltp: float, product: str) -> float:
        return self._execute("BUY", tradingsymbol, exchange, quantity, ltp, product)

    def _execute(self, transaction_type: str, tradingsymbol: str, exchange: str,
                 quantity: int, ltp: float, product: str) -> float:
        if self.mode == "paper":
            logger.info("[PAPER] %s %s x%s @ ~%.2f", transaction_type, tradingsymbol, quantity, ltp)
            return ltp

        buffer_pct = self.config.get("slippage_buffer_pct", 1.0) / 100.0
        limit_price = self._round_tick(
            ltp * (1 - buffer_pct) if transaction_type == "SELL" else ltp * (1 + buffer_pct)
        )

        order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=transaction_type,
            quantity=quantity,
            product=product,
            order_type=self.kite.ORDER_TYPE_LIMIT,
            price=limit_price,
        )

        fill_price = self._await_fill(order_id)
        if fill_price is None and self.config.get("fallback_to_market", True):
            logger.warning("Order %s not filled in time, cancelling and sending MARKET", order_id)
            try:
                self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
            except Exception as e:
                logger.warning("Cancel failed (order may have already filled): %s", e)

            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=transaction_type,
                quantity=quantity,
                product=product,
                order_type=self.kite.ORDER_TYPE_MARKET,
            )
            fill_price = self._await_fill(order_id, timeout=30)

        if fill_price is None:
            raise OrderError(f"Order {order_id} for {tradingsymbol} did not fill")
        return fill_price

    def _await_fill(self, order_id: str, timeout: int = None) -> float:
        timeout = timeout or self.config.get("order_fill_timeout_sec", 20)
        deadline = time.time() + timeout
        while time.time() < deadline:
            history = self.kite.order_history(order_id)
            last = history[-1]
            status = last["status"]
            if status == "COMPLETE":
                return float(last["average_price"])
            if status in ("REJECTED", "CANCELLED"):
                logger.error("Order %s ended as %s: %s", order_id, status, last.get("status_message"))
                return None
            time.sleep(1)
        return None

    def place_resting_limit_sell(self, tradingsymbol: str, exchange: str, quantity: int,
                                  limit_price: float, product: str) -> str:
        """
        Place a SELL LIMIT order and return immediately with its order_id —
        does NOT wait for a fill like sell_to_open() does. Meant for an order
        that should rest on the exchange across multiple poll cycles (a
        passive re-entry attempt that should only fill if price actually
        comes back to it, never chased with a market fallback).

        Paper mode returns a synthetic id; check_order_filled() always
        reports "still pending" for it — the caller decides a simulated
        fill by comparing a later LTP against limit_price itself.
        """
        limit_price = self._round_tick(limit_price)
        if self.mode == "paper":
            order_id = f"paper-{tradingsymbol}-{int(time.time())}"
            logger.info("[PAPER] resting SELL LIMIT %s x%s @ %.2f (id=%s)",
                        tradingsymbol, quantity, limit_price, order_id)
            return order_id

        return self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type="SELL",
            quantity=quantity,
            product=product,
            order_type=self.kite.ORDER_TYPE_LIMIT,
            price=limit_price,
        )

    def check_order_filled(self, order_id: str) -> Optional[float]:
        """Non-blocking: returns the fill price if COMPLETE, None if still
        pending or (in paper mode, always) not applicable — see
        place_resting_limit_sell()'s docstring for the paper-mode case."""
        if self.mode == "paper":
            return None
        history = self.kite.order_history(order_id)
        last = history[-1]
        if last["status"] == "COMPLETE":
            return float(last["average_price"])
        return None

    def cancel_order(self, order_id: str):
        if self.mode == "paper":
            return
        try:
            self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
        except Exception as e:
            logger.warning("Cancel failed (order may have already filled): %s", e)
