"""
data/instrument_loader.py
Downloads NFO instrument list from Kite, filters to the nearest weekly
Nifty expiry, and caches to CSV so you don't re-download every restart.
"""
import os
import logging
from datetime import date, datetime

import pandas as pd
from kiteconnect import KiteConnect

from config.settings import settings
from config.runtime import runtime_exchange, runtime_underlying

logger = logging.getLogger(__name__)


def exchange_cache_path(base_path: str, exchange: str) -> str:
    path = os.path.normpath(base_path)
    directory, filename = os.path.split(path)
    stem, suffix = os.path.splitext(filename)
    exchange_key = exchange.lower()

    if stem.lower().startswith(f"{exchange_key}_"):
        return path

    for known_exchange in ("nfo", "bfo"):
        prefix = f"{known_exchange}_"
        if stem.lower().startswith(prefix):
            stem = stem[len(prefix):]
            break

    return os.path.join(directory, f"{exchange_key}_{stem}{suffix}")


def get_nearest_expiry(df: pd.DataFrame) -> date:
    """Return the nearest upcoming expiry date."""
    today = date.today()
    expiries = sorted(df["expiry"].dropna().unique())
    future   = [e for e in expiries if e >= today]
    return future[0] if future else expiries[-1]


def load_option_chain(kite: KiteConnect, force_refresh: bool = False) -> dict:
    """
    Returns two dicts:
        token_map : {instrument_token -> {strike, type, tradingsymbol, expiry}}
        key_map   : {(strike, opt_type) -> {tradingsymbol, token}}
    Also returns the futures tradingsymbol string for the nearest expiry.
    """
    underlying = runtime_underlying()
    exchange = runtime_exchange()
    cache_path = exchange_cache_path(settings.INSTRUMENTS_CACHE, exchange)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    # --- load from cache or API ---
    if not force_refresh and os.path.exists(cache_path):
        logger.info(f"Loading instruments from cache: {cache_path}")
        df = pd.read_csv(cache_path, parse_dates=["expiry"])
        df["expiry"] = df["expiry"].dt.date
    else:
        logger.info("Downloading instruments from Kite API…")
        instruments = kite.instruments(exchange)
        df          = pd.DataFrame(instruments)
        df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
        df.to_csv(cache_path, index=False)
        logger.info(f"Cached {len(df)} instruments → {cache_path}")

    # --- filter selected-index options on nearest expiry ---
    nifty_opts = df[
        (df["name"] == underlying) &
        (df["instrument_type"].isin(["CE", "PE"]))
    ].copy()

    nearest = get_nearest_expiry(nifty_opts)
    logger.info(f"Trading expiry: {nearest}")
    nifty_opts = nifty_opts[nifty_opts["expiry"] == nearest]

    # --- filter nearest selected-index future for ATM reference price ---
    nifty_futs = df[
        (df["name"] == underlying) &
        (df["instrument_type"] == "FUT") &
        (df["expiry"] >= date.today())
    ].sort_values("expiry")

    fut_symbol = ""
    fut_token  = None
    if not nifty_futs.empty:
        row        = nifty_futs.iloc[0]
        fut_symbol = row["tradingsymbol"]
        fut_token  = int(row["instrument_token"])
        logger.info(f"Futures: {fut_symbol}  token={fut_token}")

    # --- build lookup dicts ---
    token_map: dict[int, dict] = {}
    key_map:   dict[tuple, dict] = {}

    for _, row in nifty_opts.iterrows():
        token = int(row["instrument_token"])
        info  = {
            "strike":        float(row["strike"]),
            "type":          row["instrument_type"],   # CE | PE
            "tradingsymbol": row["tradingsymbol"],
            "expiry":        row["expiry"],
        }
        token_map[token]                            = info
        key_map[(info["strike"], info["type"])]    = {
            "tradingsymbol": row["tradingsymbol"],
            "token":         token,
        }

    logger.info(f"Loaded {len(token_map)} option tokens for {nearest}")

    return {
        "token_map":  token_map,
        "key_map":    key_map,
        "fut_symbol": fut_symbol,
        "fut_token":  fut_token,
        "expiry":     nearest,
        "all_tokens": list(token_map.keys()) + ([fut_token] if fut_token else []),
    }
