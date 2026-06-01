from __future__ import annotations

import json
from pathlib import Path

from config.settings import settings


INDEX_OPTIONS = {
    "Nifty50": {"underlying": "NIFTY", "exchange": "NFO"},
    "BankNifty": {"underlying": "BANKNIFTY", "exchange": "NFO"},
    "FinNifty": {"underlying": "FINNIFTY", "exchange": "NFO"},
    "MidcpNifty": {"underlying": "MIDCPNIFTY", "exchange": "NFO"},
    "Sensex": {"underlying": "SENSEX", "exchange": "BFO"},
    "Bankex": {"underlying": "BANKEX", "exchange": "BFO"},
}
DEFAULT_INDEX_NAME = "Nifty50"


def read_runtime_settings() -> dict:
    runtime_path = Path(settings.RUNTIME_SETTINGS_PATH)
    if not runtime_path.exists():
        return {}

    try:
        data = json.loads(runtime_path.read_text())
    except (OSError, TypeError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def runtime_index_name() -> str:
    index_name = str(read_runtime_settings().get("index_name") or DEFAULT_INDEX_NAME)
    return index_name if index_name in INDEX_OPTIONS else DEFAULT_INDEX_NAME


def runtime_index_config(index_name: str | None = None) -> dict:
    selected_name = index_name or runtime_index_name()
    return INDEX_OPTIONS.get(selected_name, INDEX_OPTIONS[DEFAULT_INDEX_NAME])


def runtime_underlying() -> str:
    return runtime_index_config()["underlying"]


def runtime_exchange() -> str:
    return runtime_index_config()["exchange"]
