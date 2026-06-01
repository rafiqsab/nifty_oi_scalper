"""
core/oi_store.py
In-memory store for per-strike OI.  Updated on every WebSocket tick.
Provides PCR, max pain, and OI-wall helpers used by strategies.
"""
import threading
from collections import defaultdict


class OIStore:
    def __init__(self):
        # strike -> { "CE": {oi, oi_prev, ltp}, "PE": {...} }
        self.data: dict[float, dict] = defaultdict(lambda: {
            "CE": {"oi": 0, "oi_prev": 0, "ltp": 0.0, "volume": 0, "volume_prev": 0},
            "PE": {"oi": 0, "oi_prev": 0, "ltp": 0.0, "volume": 0, "volume_prev": 0},
        })
        self.lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def update(self, strike: float, opt_type: str, oi: int, ltp: float, volume: int = 0):
        with self.lock:
            leg = self.data[strike][opt_type]
            leg["oi_prev"]     = leg["oi"]
            leg["volume_prev"] = leg["volume"]
            leg["oi"]          = oi
            leg["ltp"]         = ltp
            leg["volume"]      = volume

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------
    def pcr(self) -> float:
        """Put-Call Ratio by total OI."""
        with self.lock:
            total_ce = sum(v["CE"]["oi"] for v in self.data.values())
            total_pe = sum(v["PE"]["oi"] for v in self.data.values())
        return round(total_pe / total_ce, 4) if total_ce else 0.0

    def oi_change(self, strike: float, opt_type: str) -> int:
        """Positive = buildup, Negative = unwinding."""
        with self.lock:
            leg = self.data[strike][opt_type]
            return leg["oi"] - leg["oi_prev"]

    def volume_change(self, strike: float, opt_type: str) -> int:
        """Positive = fresh volume since the previous tick."""
        with self.lock:
            leg = self.data[strike][opt_type]
            return leg["volume"] - leg["volume_prev"]

    def max_pain(self) -> float:
        """Strike where aggregate option-writer loss is minimum."""
        with self.lock:
            strikes = sorted(self.data.keys())
            pain: dict[float, float] = {}
            for s in strikes:
                loss = 0.0
                for k, v in self.data.items():
                    loss += max(0.0, s - k) * v["CE"]["oi"]   # CE writers
                    loss += max(0.0, k - s) * v["PE"]["oi"]   # PE writers
                pain[s] = loss
        return min(pain, key=pain.get) if pain else 0.0

    def oi_walls(self, top_n: int = 3) -> dict:
        """Highest-OI strikes act as resistance (CE) and support (PE)."""
        with self.lock:
            items = list(self.data.items())
        ce_wall = sorted(items, key=lambda x: x[1]["CE"]["oi"], reverse=True)[:top_n]
        pe_wall = sorted(items, key=lambda x: x[1]["PE"]["oi"], reverse=True)[:top_n]
        return {
            "resistance": [s for s, _ in ce_wall],
            "support":    [s for s, _ in pe_wall],
        }

    def snapshot(self) -> dict:
        """Thread-safe copy of full data (for dashboard)."""
        with self.lock:
            return {k: {t: dict(v) for t, v in sides.items()}
                    for k, sides in self.data.items()}
