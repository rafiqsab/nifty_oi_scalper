"""
main.py
Entry point — wires all components together and starts the system.

Usage:
    python auth.py        # run once every morning
    python main.py        # start the trading system
"""
import logging
import os
import sys
import time

from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()

# ── configure logging ──────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/system.log"),
    ],
)
logger = logging.getLogger(__name__)

# ── local imports ──────────────────────────────────────────────────────
from config.settings import settings
from config.runtime import runtime_exchange, runtime_index_name, runtime_underlying
from core.oi_store import OIStore
from core.oi_velocity_tracker import OIVelocityTracker
from core.feed_handler import FeedHandler
from data.instrument_loader import load_option_chain
from data.option_chain_logger import OptionChainLogger
from data.trade_logger import TradeLogger
from execution.order_executor import OrderExecutor
from strategies.scalp_strategy import ScalpStrategy


def validate_kite_session(kite: KiteConnect) -> None:
    """Fail early when the daily access token is missing or expired."""
    try:
        profile = kite.profile()
    except Exception as exc:
        raise SystemExit(
            "Kite session validation failed. Run `python auth.py` to generate "
            "a fresh KITE_ACCESS_TOKEN, then start `python main.py` again.\n"
            f"Original error: {exc}"
        ) from exc

    logger.info(
        "Kite session validated for %s",
        profile.get("user_id") or profile.get("user_name") or "current user",
    )


def main():
    index_name = runtime_index_name()
    logger.info(
        "Starting %s OI Scalper  [mode=%s, underlying=%s, exchange=%s]",
        index_name,
        settings.TRADE_MODE,
        runtime_underlying(),
        runtime_exchange(),
    )

    # --- Kite session ---
    kite = KiteConnect(api_key=settings.API_KEY)
    kite.set_access_token(settings.ACCESS_TOKEN)
    logger.info("Kite session initialised.")
    validate_kite_session(kite)

    # --- Load instruments ---
    chain = load_option_chain(kite, force_refresh=False)
    token_map  = chain["token_map"]   # {token -> info}
    key_map    = chain["key_map"]     # {(strike, type) -> info}
    fut_token  = chain["fut_token"]

    # --- Core components ---
    oi_store = OIStore()

    tracker = OIVelocityTracker(
        oi_threshold = settings.OI_THRESHOLD,
        tick_window  = settings.TICK_WINDOW,
        token_map    = {(v["strike"], v["type"]): v for v in token_map.values()},
    )

    trade_logger = TradeLogger()
    option_chain_logger = OptionChainLogger(oi_store=oi_store, token_map=token_map)

    # ── wire strategy → executor ───────────────────────────────────────
    executor: OrderExecutor | None = None   # set below after creation

    def on_trade(trade):
        executor.execute(trade)

    strategy = ScalpStrategy(on_trade=on_trade)

    executor = OrderExecutor(
        kite         = kite,
        ltp_cache    = {},            # will be populated by FeedHandler
        strategy     = strategy,
        trade_logger = trade_logger,
    )

    # ── event handler called on every OI signal ───────────────────────
    def on_event(event):
        strategy.handle_event(event)

    # ── feed handler (WebSocket) ──────────────────────────────────────
    feed = FeedHandler(
        api_key      = settings.API_KEY,
        access_token = settings.ACCESS_TOKEN,
        token_map    = token_map,
        key_map      = key_map,
        fut_token    = fut_token,
        oi_store     = oi_store,
        tracker      = tracker,
        on_event     = on_event,
        option_chain_logger = option_chain_logger,
    )
    # share ltp_cache with executor
    executor.ltp_cache = feed.ltp_cache

    # ── start everything ──────────────────────────────────────────────
    feed.connect(threaded=True)
    executor.start_monitor()
    logger.info("System running. Streamlit reads %s", settings.OPTION_CHAIN_CURRENT)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down…")
    finally:
        executor.stop_monitor()
        feed.close()
        logger.info("Bye.")


if __name__ == "__main__":
    main()
