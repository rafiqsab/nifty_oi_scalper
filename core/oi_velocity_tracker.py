"""
core/oi_velocity_tracker.py
Detects LONG_BUILDUP / SHORT_BUILDUP / LONG_UNWIND / SHORT_COVER
by watching OI change over a rolling tick window.
"""
import threading
from collections import deque
from datetime import datetime

from config.settings import settings
from core.models import OIEvent, OISnapshot


class OIVelocityTracker:
    """
    For each (strike, opt_type) and for futures, keeps a rolling deque
    of OISnapshot objects.  When cumulative OI change >= oi_threshold,
    an OIEvent is emitted with the classified scenario.
    """

    def __init__(
        self,
        oi_threshold: int  = None,
        tick_window:  int  = None,
        token_map:    dict = None,   # {token: {strike, type, tradingsymbol}}
    ):
        self.oi_threshold = oi_threshold or settings.OI_THRESHOLD
        self.tick_window  = tick_window  or settings.TICK_WINDOW
        self.token_map    = token_map or {}
        self.scalp_params = settings.SCALP_PARAMS

        # per-(strike, opt_type) rolling history
        self._history: dict[tuple, deque] = {}
        self._fut_history: deque          = deque(maxlen=self.tick_window)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public update methods (called from WebSocket on_ticks)
    # ------------------------------------------------------------------
    def update_option(self, snap: OISnapshot) -> OIEvent | None:
        key = (snap.strike, snap.opt_type)
        with self._lock:
            if key not in self._history:
                self._history[key] = deque(maxlen=self.tick_window)
            self._history[key].append(snap)
            if len(self._history[key]) < 2:
                return None
            return self._evaluate_option(key)

    def update_futures(self, snap: OISnapshot) -> OIEvent | None:
        with self._lock:
            self._fut_history.append(snap)
            if len(self._fut_history) < 2:
                return None
            return self._evaluate_futures()

    # ------------------------------------------------------------------
    # Evaluation helpers
    # ------------------------------------------------------------------
    def _evaluate_option(self, key: tuple) -> OIEvent | None:
        hist  = self._history[key]
        old   = hist[0]
        new   = hist[-1]
        strike, opt_type = key

        oi_change    = new.oi  - old.oi
        price_change = new.ltp - old.ltp

        if abs(oi_change) < self.oi_threshold:
            return None

        scenario, direction = self._classify(oi_change, price_change)
        if scenario is None:
            return None

        confidence = self._confidence(oi_change, price_change)
        params     = self.scalp_params.get(scenario, {"sl_pts": 12, "tgt_pts": 20})
        entry      = new.ltp
        sl         = entry - params["sl_pts"]  if direction == "BUY" else entry + params["sl_pts"]
        target     = entry + params["tgt_pts"] if direction == "BUY" else entry - params["tgt_pts"]

        # build proper tradingsymbol from token_map (already resolved by loader)
        ts = self.token_map.get((strike, opt_type), {}).get("tradingsymbol",
             f"NIFTY{int(strike)}{opt_type}")

        return OIEvent(
            timestamp       = new.timestamp,
            scenario        = scenario,
            instrument      = f"NIFTY {opt_type} {int(strike)}",
            tradingsymbol   = ts,
            oi_change       = oi_change,
            price_change    = price_change,
            confidence      = confidence,
            trade_direction = direction,
            suggested_entry = entry,
            stop_loss       = sl,
            target          = target,
        )

    def _evaluate_futures(self) -> OIEvent | None:
        old = self._fut_history[0]
        new = self._fut_history[-1]

        oi_change    = new.futures_oi    - old.futures_oi
        price_change = new.futures_price - old.futures_price

        if abs(oi_change) < self.oi_threshold:
            return None

        scenario, direction = self._classify(oi_change, price_change)
        if scenario is None:
            return None

        confidence = self._confidence(oi_change, price_change)
        params     = self.scalp_params.get(scenario, {"sl_pts": 15, "tgt_pts": 25})
        entry      = new.futures_price
        sl         = entry - params["sl_pts"]  if direction == "BUY" else entry + params["sl_pts"]
        target     = entry + params["tgt_pts"] if direction == "BUY" else entry - params["tgt_pts"]

        return OIEvent(
            timestamp       = new.timestamp,
            scenario        = scenario,
            instrument      = "NIFTY FUT",
            tradingsymbol   = "NIFTYFUT",      # resolved properly in loader
            oi_change       = oi_change,
            price_change    = price_change,
            confidence      = confidence,
            trade_direction = direction,
            suggested_entry = entry,
            stop_loss       = sl,
            target          = target,
        )

    # ------------------------------------------------------------------
    # Classification + confidence
    # ------------------------------------------------------------------
    @staticmethod
    def _classify(oi_change: int, price_change: float) -> tuple[str | None, str | None]:
        oi_up    = oi_change    > 0
        price_up = price_change > 0

        if   oi_up and     price_up:   return "LONG_BUILDUP",  "BUY"
        elif oi_up and not price_up:   return "SHORT_BUILDUP", "SELL"
        elif not oi_up and not price_up: return "LONG_UNWIND", "SELL"
        elif not oi_up and price_up:   return "SHORT_COVER",   "BUY"
        return None, None

    @staticmethod
    def _confidence(oi_change: int, price_change: float) -> float:
        oi_score    = min(abs(oi_change) / 2_000_000, 1.0)          # saturates at 20L
        price_score = min(abs(price_change) / 50.0,   1.0)          # saturates at 50 pts
        return round(oi_score * 0.6 + price_score * 0.4, 3)
