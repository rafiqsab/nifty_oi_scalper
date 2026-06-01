"""
core/feed_handler.py
Manages the KiteTicker WebSocket connection.
Feeds ticks into OIStore and OIVelocityTracker.
Calls a user-supplied callback when an OIEvent fires.
"""
import logging
import time
from datetime import datetime
from typing import Callable

from kiteconnect import KiteTicker

from config.runtime import runtime_underlying
from core.feed_status import write_feed_status
from core.models import OIEvent, OISnapshot
from core.oi_store import OIStore
from core.oi_velocity_tracker import OIVelocityTracker

logger = logging.getLogger(__name__)


class FeedHandler:
    def __init__(
        self,
        api_key:      str,
        access_token: str,
        token_map:    dict,          # from instrument_loader
        key_map:      dict,
        fut_token:    int | None,
        oi_store:     OIStore,
        tracker:      OIVelocityTracker,
        on_event:     Callable[[OIEvent], None],   # your signal handler
        option_chain_logger = None,
    ):
        self.token_map    = token_map
        self.key_map      = key_map
        self.fut_token    = fut_token
        self.oi_store     = oi_store
        self.tracker      = tracker
        self.on_event     = on_event
        self.option_chain_logger = option_chain_logger
        self.underlying = runtime_underlying()
        self.tick_batches = 0
        self._last_status_write = 0.0

        # shared ltp dict for position monitor
        self.ltp_cache: dict[str, float] = {}
        self.underlying_price = 0.0

        self.kws = KiteTicker(api_key, access_token)
        self.kws.on_connect = self._on_connect
        self.kws.on_ticks   = self._on_ticks
        self.kws.on_close   = self._on_close
        self.kws.on_error   = self._on_error

    # ------------------------------------------------------------------
    # KiteTicker callbacks
    # ------------------------------------------------------------------
    def _on_connect(self, ws, response):
        all_tokens = list(self.token_map.keys())
        if self.fut_token:
            all_tokens.append(self.fut_token)

        logger.info(f"WebSocket connected. Subscribing {len(all_tokens)} tokens…")
        ws.subscribe(all_tokens)
        ws.set_mode(ws.MODE_FULL, all_tokens)   # FULL mode gives OI
        write_feed_status("connected", subscribed_tokens=len(all_tokens))

    def _on_ticks(self, ws, ticks: list):
        self.tick_batches += 1
        now = time.monotonic()
        if now - self._last_status_write >= 1:
            write_feed_status(
                "receiving_ticks",
                tick_batches=self.tick_batches,
                latest_batch_size=len(ticks),
            )
            self._last_status_write = now
        for tick in ticks:
            token = tick.get("instrument_token")
            ltp   = tick.get("last_price", 0.0)
            oi    = tick.get("oi", 0)
            volume = tick.get("volume_traded") or tick.get("volume") or 0
            ts    = datetime.now()

            # --- futures tick ---
            if token == self.fut_token:
                self.ltp_cache[f"{self.underlying} FUT"] = ltp
                self.underlying_price = ltp
                snap = OISnapshot(
                    timestamp     = ts,
                    strike        = 0,
                    opt_type      = "FUT",
                    oi            = 0,
                    ltp           = 0.0,
                    futures_oi    = oi,
                    futures_price = ltp,
                )
                event = self.tracker.update_futures(snap)
                if event:
                    self.on_event(event)
                continue

            # --- options tick ---
            if token not in self.token_map:
                continue

            info   = self.token_map[token]
            strike = info["strike"]
            otype  = info["type"]

            self.oi_store.update(strike, otype, oi, ltp, volume)
            self.ltp_cache[info["tradingsymbol"]] = ltp

            snap = OISnapshot(
                timestamp = ts,
                strike    = strike,
                opt_type  = otype,
                oi        = oi,
                ltp       = ltp,
            )
            event = self.tracker.update_option(snap)
            if event:
                self.on_event(event)

        if self.option_chain_logger:
            self.option_chain_logger.maybe_log(self.underlying_price)

    def _on_close(self, ws, code, reason):
        logger.warning(f"WebSocket closed [{code}]: {reason}")
        write_feed_status("closed", code=code, reason=str(reason))

    def _on_error(self, ws, code, reason):
        logger.error(f"WebSocket error [{code}]: {reason}")
        write_feed_status("error", code=code, reason=str(reason))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self, threaded: bool = True):
        """Start the WebSocket (non-blocking when threaded=True)."""
        self.kws.connect(threaded=threaded)

    def close(self):
        self.kws.stop()
