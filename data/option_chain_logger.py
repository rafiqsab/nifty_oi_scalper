"""
CSV logger for the Streamlit option-chain view.

It writes:
- data/option_chain_current_YYYYMMDD_INDEX.csv: latest combined call/put strike snapshot
- data/option_chain_history_YYYYMMDD_INDEX.csv: append-only history for later analysis
"""
from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

from config.settings import settings
from config.runtime import DEFAULT_INDEX_NAME, runtime_index_name
from core.oi_store import OIStore


class OptionChainLogger:
    HEADERS = [
        "timestamp",
        "underlying_price",
        "atm_strike",
        "strike",
        "call_ltp",
        "call_oi",
        "call_volume",
        "put_ltp",
        "put_oi",
        "put_volume",
        "volume_diff",
        "change_call_oi",
        "change_put_oi",
        "action",
    ]

    def __init__(
        self,
        oi_store: OIStore,
        token_map: dict[int, dict],
        current_path: str = settings.OPTION_CHAIN_CURRENT,
        history_path: str = settings.OPTION_CHAIN_HISTORY,
        interval_seconds: float = settings.OPTION_CHAIN_LOG_INTERVAL,
    ):
        self.oi_store = oi_store
        self.token_map = token_map
        self.current_path_base = Path(current_path)
        self.history_path_base = Path(history_path)
        self.interval_seconds = interval_seconds
        self._last_write = 0.0
        self._last_logged: dict[tuple[float, str], dict[str, int]] = {}
        self._active_date = datetime.now().strftime("%Y%m%d")
        self._active_index_name = self._runtime_index_name()

        self.current_path_base.parent.mkdir(parents=True, exist_ok=True)
        self.history_path_base.parent.mkdir(parents=True, exist_ok=True)
        self._init_history(self._history_path())

    def maybe_log(self, underlying_price: float) -> None:
        if underlying_price <= 0:
            return

        now = time.monotonic()
        interval = self._runtime_interval_seconds()
        if now - self._last_write < interval:
            return

        self._roll_daily_files_if_needed()
        rows = self._build_rows(underlying_price)
        if not rows:
            return

        current_path = self._current_path()
        history_path = self._history_path()
        self._write_current(rows, current_path)
        self._append_history(rows, history_path)
        self._last_write = now

    def _build_rows(self, underlying_price: float) -> list[dict]:
        snapshot = self.oi_store.snapshot()
        strikes = sorted(snapshot.keys())
        if not strikes:
            return []

        atm = min(strikes, key=lambda strike: abs(strike - underlying_price))
        below_atm = [strike for strike in strikes if strike < atm][-5:]
        above_atm = [strike for strike in strikes if strike > atm][:5]
        selected_strikes = below_atm + [atm] + above_atm
        ts = datetime.now().isoformat(timespec="seconds")

        rows: list[dict] = []
        for strike in selected_strikes:
            call = snapshot.get(strike, {}).get("CE", {})
            put = snapshot.get(strike, {}).get("PE", {})

            call_oi, call_volume, call_oi_change, call_volume_change = self._leg_values(
                strike, "CE", call
            )
            put_oi, put_volume, put_oi_change, put_volume_change = self._leg_values(
                strike, "PE", put
            )
            volume_diff = call_volume_change + put_volume_change

            rows.append(
                {
                    "timestamp": ts,
                    "underlying_price": round(underlying_price, 2),
                    "atm_strike": atm,
                    "strike": strike,
                    "call_ltp": call.get("ltp", 0.0),
                    "call_oi": call_oi,
                    "call_volume": call_volume,
                    "put_ltp": put.get("ltp", 0.0),
                    "put_oi": put_oi,
                    "put_volume": put_volume,
                    "volume_diff": volume_diff,
                    "change_call_oi": call_oi_change,
                    "change_put_oi": put_oi_change,
                    "action": self._action(call_oi_change, put_oi_change, volume_diff),
                }
            )
        return rows

    def _leg_values(self, strike: float, side: str, leg: dict) -> tuple[int, int, int, int]:
        key = (strike, side)
        prev = self._last_logged.get(key, {})
        oi = int(leg.get("oi", 0) or 0)
        volume = int(leg.get("volume", 0) or 0)
        oi_change = oi - int(prev.get("oi", oi))
        volume_change = volume - int(prev.get("volume", volume))
        self._last_logged[key] = {"oi": oi, "volume": volume}
        return oi, volume, oi_change, volume_change

    def _runtime_interval_seconds(self) -> float:
        data = self._runtime_settings()
        try:
            return float(data.get("tick_frequency_seconds", self.interval_seconds))
        except (ValueError, TypeError):
            return self.interval_seconds

    def _runtime_index_name(self) -> str:
        return runtime_index_name() or DEFAULT_INDEX_NAME

    def _runtime_settings(self) -> dict:
        runtime_path = Path(settings.RUNTIME_SETTINGS_PATH)
        if not runtime_path.exists():
            return {}

        try:
            return json.loads(runtime_path.read_text())
        except (OSError, TypeError, json.JSONDecodeError):
            return {}

    def _roll_daily_files_if_needed(self) -> None:
        current_date = datetime.now().strftime("%Y%m%d")
        current_index_name = self._runtime_index_name()
        if current_date == self._active_date and current_index_name == self._active_index_name:
            return

        self._active_date = current_date
        self._active_index_name = current_index_name
        self._last_logged.clear()
        self._init_history(self._history_path())

    def _current_path(self) -> Path:
        return self._dated_path(self.current_path_base)

    def _history_path(self) -> Path:
        return self._dated_path(self.history_path_base)

    def _dated_path(self, base_path: Path) -> Path:
        index_name = self._active_index_name.upper().replace(" ", "")
        return base_path.with_name(
            f"{base_path.stem}_{self._active_date}_{index_name}{base_path.suffix}"
        )

    @staticmethod
    def _action(change_call_oi: int, change_put_oi: int, volume_diff: int) -> str:
        if change_call_oi > change_put_oi and volume_diff > 0:
            return "CALL ACTIVE"
        if change_put_oi > change_call_oi and volume_diff < 0:
            return "PUT ACTIVE"
        if change_call_oi > 0 and change_put_oi > 0:
            return "BOTH BUILD"
        if change_call_oi < 0 and change_put_oi < 0:
            return "OI UNWIND"
        return "WATCH"

    def _init_history(self, history_path: Path) -> None:
        if history_path.exists():
            try:
                with history_path.open(newline="") as file:
                    existing_headers = next(csv.reader(file), [])
            except OSError:
                existing_headers = []

            if existing_headers == self.HEADERS:
                return

            backup_path = history_path.with_suffix(
                f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            )
            os.replace(history_path, backup_path)

        if not history_path.exists():
            with history_path.open("w", newline="") as file:
                csv.DictWriter(file, fieldnames=self.HEADERS).writeheader()

    def _write_current(self, rows: list[dict], current_path: Path) -> None:
        temp_path = current_path.with_suffix(".tmp")
        with temp_path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=self.HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, current_path)

    def _append_history(self, rows: list[dict], history_path: Path) -> None:
        with history_path.open("a", newline="") as file:
            csv.DictWriter(file, fieldnames=self.HEADERS).writerows(rows)
