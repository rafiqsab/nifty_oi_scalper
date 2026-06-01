"""
core/models.py
Shared dataclasses — OI snapshots, events, trades.
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OISnapshot:
    timestamp:      datetime
    strike:         float
    opt_type:       str          # CE | PE | FUT
    oi:             int
    ltp:            float
    futures_oi:     int   = 0
    futures_price:  float = 0.0
    volume:         int   = 0


@dataclass
class OIEvent:
    """Emitted by OIVelocityTracker when a threshold is breached."""
    timestamp:        datetime
    scenario:         str        # LONG_BUILDUP | SHORT_BUILDUP | LONG_UNWIND | SHORT_COVER
    instrument:       str        # human-readable e.g. "NIFTY CE 24500"
    tradingsymbol:    str        # exact Kite tradingsymbol for order placement
    oi_change:        int
    price_change:     float
    confidence:       float      # 0.0 – 1.0
    trade_direction:  str        # BUY | SELL
    suggested_entry:  float
    stop_loss:        float
    target:           float


@dataclass
class ScalpTrade:
    event:        OIEvent
    entry_price:  float
    sl:           float
    target:       float
    quantity:     int
    entry_time:   datetime        = field(default_factory=datetime.now)
    exit_price:   float           = 0.0
    exit_time:    datetime | None = None
    status:       str             = "OPEN"   # OPEN | HIT_TARGET | HIT_SL | MANUAL_EXIT
    pnl:          float           = 0.0
    order_id:     str             = ""
