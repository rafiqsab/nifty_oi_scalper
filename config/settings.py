"""
config/settings.py
Central configuration — all values come from .env (never hardcode secrets).
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Kite credentials ---
    API_KEY: str        = os.getenv("KITE_API_KEY", "")
    API_SECRET: str     = os.getenv("KITE_API_SECRET", "")
    ACCESS_TOKEN: str   = os.getenv("KITE_ACCESS_TOKEN", "")

    # --- Mode ---
    TRADE_MODE: str     = os.getenv("TRADE_MODE", "PAPER")   # PAPER | LIVE

    # --- Instrument ---
    UNDERLYING: str     = os.getenv("UNDERLYING", "NIFTY")
    EXCHANGE: str       = os.getenv("EXCHANGE", "NFO")
    LOT_SIZE: int       = int(os.getenv("LOT_SIZE", 25))

    # --- OI detection ---
    OI_THRESHOLD: int   = int(os.getenv("OI_THRESHOLD", 500_000))   # 5 lakh
    TICK_WINDOW: int    = 5      # number of ticks to measure OI change over

    # --- Scalp SL / Target (points on premium or futures price) ---
    SCALP_PARAMS: dict  = {
        "LONG_BUILDUP":  {"sl_pts": 15, "tgt_pts": 25},
        "SHORT_BUILDUP": {"sl_pts": 15, "tgt_pts": 25},
        "SHORT_COVER":   {"sl_pts": 10, "tgt_pts": 20},
        "LONG_UNWIND":   {"sl_pts": 10, "tgt_pts": 20},
    }

    # --- Risk ---
    MAX_CONCURRENT_SCALPS: int = int(os.getenv("MAX_CONCURRENT_SCALPS", 2))
    DAILY_LOSS_LIMIT: float    = float(os.getenv("DAILY_LOSS_LIMIT", 3000))
    MIN_CONFIDENCE: float      = 0.4

    # --- Market hours (IST) ---
    MARKET_OPEN:        str    = "09:30"
    MARKET_CLOSE:       str    = "15:00"

    # --- Paths ---
    DATA_DIR:           str    = os.getenv("DATA_DIR", "data")
    LOG_DIR:            str    = os.getenv("LOG_DIR", "logs")
    DB_PATH:            str    = os.getenv("DB_PATH", f"{DATA_DIR}/trades.db")
    INSTRUMENTS_CACHE:  str    = os.getenv(
        "INSTRUMENTS_CACHE",
        f"{DATA_DIR}/instruments/nfo_instruments.csv",
    )
    OPTION_CHAIN_CURRENT: str  = os.getenv(
        "OPTION_CHAIN_CURRENT",
        f"{DATA_DIR}/option_chain_current.csv",
    )
    OPTION_CHAIN_HISTORY: str  = os.getenv(
        "OPTION_CHAIN_HISTORY",
        f"{DATA_DIR}/option_chain_history.csv",
    )
    OPTION_CHAIN_LOG_INTERVAL: float = float(os.getenv("OPTION_CHAIN_LOG_INTERVAL", 30))
    RUNTIME_SETTINGS_PATH: str = os.getenv(
        "RUNTIME_SETTINGS_PATH",
        f"{DATA_DIR}/runtime_settings.json",
    )


settings = Settings()
