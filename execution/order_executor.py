"""
execution/order_executor.py
Handles order placement (paper or live) and position monitoring.
Runs a background monitor thread that watches LTP against SL/Target.
"""
import logging
import time
import threading
from datetime import datetime

from kiteconnect import KiteConnect

from config.settings import settings
from core.models import ScalpTrade
from data.trade_logger import TradeLogger

logger = logging.getLogger(__name__)


class OrderExecutor:
    def __init__(
        self,
        kite:        KiteConnect,
        ltp_cache:   dict,              # shared dict updated by FeedHandler
        strategy,                        # ScalpStrategy — for close_trade()
        trade_logger: "TradeLogger",
    ):
        self.kite         = kite
        self.ltp_cache    = ltp_cache
        self.strategy     = strategy
        self.logger       = trade_logger
        self.mode         = settings.TRADE_MODE   # PAPER | LIVE
        self._monitor_running = False

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------
    def execute(self, trade: ScalpTrade):
        """Place entry order (paper or live)."""
        ev = trade.event

        if self.mode == "PAPER":
            logger.info(
                f"[PAPER] {ev.trade_direction} {ev.tradingsymbol} "
                f"qty={trade.quantity} @ {trade.entry_price:.2f}"
            )
            self.logger.log(trade)
            return

        # --- live order ---
        try:
            txn = (self.kite.TRANSACTION_TYPE_BUY
                   if ev.trade_direction == "BUY"
                   else self.kite.TRANSACTION_TYPE_SELL)

            order_id = self.kite.place_order(
                variety          = self.kite.VARIETY_CO,    # Cover Order has built-in SL
                exchange         = self.kite.EXCHANGE_NFO,
                tradingsymbol    = ev.tradingsymbol,
                transaction_type = txn,
                quantity         = trade.quantity,
                order_type       = self.kite.ORDER_TYPE_MARKET,
                product          = self.kite.PRODUCT_MIS,
                trigger_price    = trade.sl,
            )
            trade.order_id = str(order_id)
            logger.info(f"[LIVE] Order placed: {order_id}")
            self.logger.log(trade)

        except Exception as exc:
            logger.error(f"Order placement failed: {exc}")

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------
    def exit_trade(self, trade: ScalpTrade, reason: str):
        ev = trade.event

        # get actual LTP at exit time
        exit_price = self.ltp_cache.get(ev.tradingsymbol, trade.entry_price)
        self.strategy.close_trade(trade, exit_price, reason)
        self.logger.update(trade)

        if self.mode == "PAPER":
            logger.info(f"[PAPER EXIT] {reason} — {ev.tradingsymbol} @ {exit_price:.2f}")
            return

        try:
            txn = (self.kite.TRANSACTION_TYPE_SELL
                   if ev.trade_direction == "BUY"
                   else self.kite.TRANSACTION_TYPE_BUY)

            self.kite.place_order(
                variety          = self.kite.VARIETY_REGULAR,
                exchange         = self.kite.EXCHANGE_NFO,
                tradingsymbol    = ev.tradingsymbol,
                transaction_type = txn,
                quantity         = trade.quantity,
                order_type       = self.kite.ORDER_TYPE_MARKET,
                product          = self.kite.PRODUCT_MIS,
            )
        except Exception as exc:
            logger.error(f"Exit order failed: {exc}")

    # ------------------------------------------------------------------
    # Position monitor (background thread)
    # ------------------------------------------------------------------
    def start_monitor(self):
        self._monitor_running = True
        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()
        logger.info("Position monitor started.")

    def stop_monitor(self):
        self._monitor_running = False

    def _monitor_loop(self):
        while self._monitor_running:
            for trade in list(self.strategy.active_trades):
                if trade.status != "OPEN":
                    continue
                self._check_exit(trade)
            time.sleep(0.5)   # 500 ms resolution

    def _check_exit(self, trade: ScalpTrade):
        symbol      = trade.event.tradingsymbol
        current_ltp = self.ltp_cache.get(symbol, trade.entry_price)
        direction   = trade.event.trade_direction

        hit_target = (
            (direction == "BUY"  and current_ltp >= trade.target) or
            (direction == "SELL" and current_ltp <= trade.target)
        )
        hit_sl = (
            (direction == "BUY"  and current_ltp <= trade.sl) or
            (direction == "SELL" and current_ltp >= trade.sl)
        )

        if hit_target:
            self.exit_trade(trade, "HIT_TARGET")
        elif hit_sl:
            self.exit_trade(trade, "HIT_SL")
