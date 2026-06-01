"""
strategies/scalp_strategy.py
Receives OIEvents from the tracker, applies filters (confidence,
time-of-day, daily loss limit, max concurrent trades), and creates
ScalpTrade objects that are passed to the executor.
"""
import logging
from datetime import datetime
from typing import Callable

from config.settings import settings
from core.models import OIEvent, ScalpTrade

logger = logging.getLogger(__name__)


class ScalpStrategy:
    def __init__(self, on_trade: Callable[[ScalpTrade], None]):
        """
        on_trade: callback invoked with a new ScalpTrade ready for execution.
        """
        self.on_trade     = on_trade
        self.active_trades: list[ScalpTrade] = []
        self.daily_pnl    = 0.0

    # ------------------------------------------------------------------
    # Called by FeedHandler when an OIEvent fires
    # ------------------------------------------------------------------
    def handle_event(self, event: OIEvent):
        if not self._passes_filters(event):
            return

        params  = settings.SCALP_PARAMS.get(event.scenario, {"sl_pts": 12, "tgt_pts": 20})
        entry   = event.suggested_entry
        sl      = entry - params["sl_pts"]  if event.trade_direction == "BUY" else entry + params["sl_pts"]
        target  = entry + params["tgt_pts"] if event.trade_direction == "BUY" else entry - params["tgt_pts"]

        trade = ScalpTrade(
            event       = event,
            entry_price = entry,
            sl          = sl,
            target      = target,
            quantity    = settings.LOT_SIZE,
        )
        self.active_trades.append(trade)

        logger.info(
            f"\n{'═'*55}"
            f"\n  {event.scenario:<20}  confidence={event.confidence:.0%}"
            f"\n  Instrument : {event.instrument}"
            f"\n  Direction  : {event.trade_direction}"
            f"\n  OI Change  : {event.oi_change:+,} contracts"
            f"\n  Entry      : {entry:.2f}  SL={sl:.2f}  TGT={target:.2f}"
            f"\n{'═'*55}"
        )
        self.on_trade(trade)

    # ------------------------------------------------------------------
    # Trade lifecycle updates (called by executor / monitor)
    # ------------------------------------------------------------------
    def close_trade(self, trade: ScalpTrade, exit_price: float, reason: str):
        trade.exit_price = exit_price
        trade.exit_time  = datetime.now()
        trade.status     = reason   # HIT_TARGET | HIT_SL | MANUAL_EXIT

        multiplier   = 1 if trade.event.trade_direction == "BUY" else -1
        trade.pnl    = multiplier * (exit_price - trade.entry_price) * trade.quantity
        self.daily_pnl += trade.pnl

        if trade in self.active_trades:
            self.active_trades.remove(trade)

        emoji = "✅" if trade.pnl > 0 else "❌"
        logger.info(
            f"{emoji} {reason:<15} {trade.event.instrument:<25} "
            f"PnL=₹{trade.pnl:+.0f}  DailyPnL=₹{self.daily_pnl:+.0f}"
        )

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------
    def _passes_filters(self, event: OIEvent) -> bool:
        # 1. Daily loss limit
        if self.daily_pnl <= -settings.DAILY_LOSS_LIMIT:
            logger.warning("Daily loss limit hit — skipping signal")
            return False

        # 2. Max concurrent positions
        open_count = sum(1 for t in self.active_trades if t.status == "OPEN")
        if open_count >= settings.MAX_CONCURRENT_SCALPS:
            logger.debug("Max concurrent scalps reached — skipping")
            return False

        # 3. Minimum confidence
        if event.confidence < settings.MIN_CONFIDENCE:
            logger.debug(f"Low confidence {event.confidence:.2f} — skipping")
            return False

        # 4. Market hours
        now = datetime.now().time()
        open_t  = datetime.strptime(settings.MARKET_OPEN,  "%H:%M").time()
        close_t = datetime.strptime(settings.MARKET_CLOSE, "%H:%M").time()
        if not (open_t <= now <= close_t):
            logger.debug("Outside market hours — skipping")
            return False

        return True
