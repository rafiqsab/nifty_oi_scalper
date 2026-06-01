"""
Streamlit UI for the NIFTY OI Scalper.

Run the UI, then enter today's Kite token and click Connect:

    streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st
from kiteconnect import KiteConnect

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

from config.runtime import DEFAULT_INDEX_NAME, INDEX_OPTIONS
from config.settings import settings


DB_PATH = ROOT_DIR / settings.DB_PATH
LOG_DIR = ROOT_DIR / settings.LOG_DIR
SYSTEM_LOG_PATH = LOG_DIR / "system.log"
OPTION_CHAIN_CURRENT_SETTING = getattr(
    settings,
    "OPTION_CHAIN_CURRENT",
    "data/option_chain_current.csv",
)
OPTION_CHAIN_HISTORY_SETTING = getattr(
    settings,
    "OPTION_CHAIN_HISTORY",
    "data/option_chain_history.csv",
)
OPTION_CHAIN_LOG_INTERVAL = getattr(settings, "OPTION_CHAIN_LOG_INTERVAL", 30.0)
RUNTIME_SETTINGS_SETTING = getattr(settings, "RUNTIME_SETTINGS_PATH", "data/runtime_settings.json")
RUNTIME_SETTINGS_PATH = ROOT_DIR / RUNTIME_SETTINGS_SETTING

FEED_PID_PATH = Path(settings.DATA_DIR) / "feed_runner.pid"


def dated_csv_path(path_setting: str, index_name: str) -> Path:
    base_path = ROOT_DIR / path_setting
    date_suffix = datetime.now().strftime("%Y%m%d")
    index_suffix = index_name.upper().replace(" ", "")
    return base_path.with_name(f"{base_path.stem}_{date_suffix}_{index_suffix}{base_path.suffix}")

FREQUENCY_OPTIONS = {
    "1 sec": 1,
    "10 sec": 10,
    "15 sec": 15,
    "30 sec": 30,
    "1 min": 60,
    "2 min": 120,
    "5 min": 300,
}


st.set_page_config(
    page_title="NIFTY OI Scalper",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=1)
def load_option_chain(path: str) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()

    chain = pd.read_csv(csv_path)
    numeric_columns = [
        "underlying_price",
        "atm_strike",
        "strike",
        "ltp",
        "oi",
        "oi_change",
        "volume",
        "volume_change",
        "call_ltp",
        "call_oi",
        "call_volume",
        "put_ltp",
        "put_oi",
        "put_volume",
        "volume_diff",
        "change_call_oi",
        "change_put_oi",
    ]
    for column in numeric_columns:
        if column in chain:
            chain[column] = pd.to_numeric(chain[column], errors="coerce")
    return chain


@st.cache_data(ttl=2)
def load_trades(db_path: str) -> pd.DataFrame:
    path = Path(db_path)
    if not path.exists():
        return pd.DataFrame()

    with sqlite3.connect(path) as conn:
        try:
            trades = pd.read_sql_query(
                """
                SELECT
                    id,
                    trade_date,
                    scenario,
                    instrument,
                    tradingsymbol,
                    direction,
                    oi_change,
                    confidence,
                    entry_price,
                    stop_loss,
                    target,
                    exit_price,
                    exit_time,
                    status,
                    pnl,
                    order_id
                FROM trades
                ORDER BY trade_date DESC, id DESC
                """,
                conn,
            )
        except Exception:
            return pd.DataFrame()

    for column in ("trade_date", "exit_time"):
        if column in trades:
            trades[column] = pd.to_datetime(trades[column], errors="coerce")
    return trades


@st.cache_data(ttl=2)
def load_log_tail(path: str, max_lines: int = 250) -> str:
    log_path = Path(path)
    if not log_path.exists():
        return "No system log found yet."

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:]) if lines else "System log is empty."


def build_tick_display(chain: pd.DataFrame) -> pd.DataFrame:
    if chain.empty:
        return chain

    display_columns = [
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
    if set(display_columns).issubset(chain.columns):
        return chain[display_columns]

    calls = chain[chain["side"] == "CE"].set_index("strike")
    puts = chain[chain["side"] == "PE"].set_index("strike")
    strikes = sorted(set(calls.index).union(set(puts.index)))

    rows = []
    for strike in strikes:
        call = calls.loc[strike] if strike in calls.index else {}
        put = puts.loc[strike] if strike in puts.index else {}
        call_volume = int(call.get("volume", 0) or 0)
        put_volume = int(put.get("volume", 0) or 0)
        call_volume_change = int(call.get("volume_change", 0) or 0)
        put_volume_change = int(put.get("volume_change", 0) or 0)
        change_call_oi = int(call.get("oi_change", 0) or 0)
        change_put_oi = int(put.get("oi_change", 0) or 0)
        volume_diff = call_volume_change + put_volume_change

        if change_call_oi > change_put_oi and volume_diff > 0:
            action = "CALL ACTIVE"
        elif change_put_oi > change_call_oi and volume_diff < 0:
            action = "PUT ACTIVE"
        elif change_call_oi > 0 and change_put_oi > 0:
            action = "BOTH BUILD"
        elif change_call_oi < 0 and change_put_oi < 0:
            action = "OI UNWIND"
        else:
            action = "WATCH"

        rows.append(
            {
                "strike": strike,
                "call_ltp": call.get("ltp", 0.0),
                "call_oi": call.get("oi", 0),
                "call_volume": call_volume,
                "put_ltp": put.get("ltp", 0.0),
                "put_oi": put.get("oi", 0),
                "put_volume": put_volume,
                "volume_diff": volume_diff,
                "change_call_oi": change_call_oi,
                "change_put_oi": change_put_oi,
                "action": action,
            }
        )

    return pd.DataFrame(rows)


def style_tick_display(table: pd.DataFrame, underlying: float, atm: float):
    call_columns = ["call_ltp", "call_oi", "call_volume", "change_call_oi"]
    put_columns = ["put_ltp", "put_oi", "put_volume", "change_put_oi"]

    def row_styles(row: pd.Series) -> list[str]:
        strike = float(row["strike"])
        if strike == atm:
            row_color = "background-color: #fef3c7; color: #713f12"
            return [row_color for _ in row.index]

        styles = []
        for column in row.index:
            if column in call_columns:
                is_itm = strike < underlying
                styles.append(
                    "background-color: #dcfce7; color: #14532d"
                    if is_itm
                    else "background-color: #ffedd5; color: #9a3412"
                )
            elif column in put_columns:
                is_itm = strike > underlying
                styles.append(
                    "background-color: #dcfce7; color: #14532d"
                    if is_itm
                    else "background-color: #ffedd5; color: #9a3412"
                )
            else:
                styles.append("")
        return styles

    return table.style.apply(row_styles, axis=1).format(
        {
            "strike": "{:,.0f}",
            "call_ltp": "{:,.2f}",
            "call_oi": "{:,.0f}",
            "call_volume": "{:,.0f}",
            "put_ltp": "{:,.2f}",
            "put_oi": "{:,.0f}",
            "put_volume": "{:,.0f}",
            "volume_diff": "{:+,.0f}",
            "change_call_oi": "{:+,.0f}",
            "change_put_oi": "{:+,.0f}",
        },
        na_rep="-",
    )


def render_sidebar() -> str:
    st.sidebar.title("Controls")
    auto_refresh = st.sidebar.toggle("Auto refresh", value=True)
    selected_index_name = read_index_name()
    index_options = list(INDEX_OPTIONS.keys())
    index_name = st.sidebar.selectbox(
        "Index name",
        index_options,
        index=index_options.index(selected_index_name),
    )
    selected_frequency = read_tick_frequency()
    frequency_label = st.sidebar.selectbox(
        "Tick frequency",
        list(FREQUENCY_OPTIONS.keys()),
        index=list(FREQUENCY_OPTIONS.values()).index(selected_frequency),
    )
    refresh_seconds = FREQUENCY_OPTIONS[frequency_label]
    write_runtime_settings(
        tick_frequency_seconds=refresh_seconds,
        index_name=index_name,
    )

    if auto_refresh and st_autorefresh:
        st_autorefresh(interval=refresh_seconds * 1000, key="dashboard_refresh")
    elif auto_refresh:
        st.sidebar.warning("Install streamlit-autorefresh for timed refreshes.")

    if st.sidebar.button("Refresh now", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.caption("Runtime")
    current_path = dated_csv_path(OPTION_CHAIN_CURRENT_SETTING, index_name)
    history_path = dated_csv_path(OPTION_CHAIN_HISTORY_SETTING, index_name)
    st.sidebar.write(f"Mode: **{settings.TRADE_MODE}**")
    st.sidebar.write(f"Index: **{index_name}**")
    st.sidebar.write(f"Current CSV: `{current_path.relative_to(ROOT_DIR)}`")
    st.sidebar.write(f"History CSV: `{history_path.relative_to(ROOT_DIR)}`")
    st.sidebar.write(f"Runtime settings: `{RUNTIME_SETTINGS_SETTING}`")

    render_kite_connection_controls()
    return index_name


def read_tick_frequency() -> int:
    default_frequency = 30
    try:
        value = int(read_runtime_settings().get("tick_frequency_seconds", default_frequency))
    except (ValueError, TypeError):
        value = default_frequency

    return value if value in FREQUENCY_OPTIONS.values() else default_frequency


def read_index_name() -> str:
    index_name = str(read_runtime_settings().get("index_name") or DEFAULT_INDEX_NAME)
    return index_name if index_name in INDEX_OPTIONS else DEFAULT_INDEX_NAME


def read_runtime_settings() -> dict:
    if not RUNTIME_SETTINGS_PATH.exists():
        return {}

    try:
        return json.loads(RUNTIME_SETTINGS_PATH.read_text())
    except (OSError, TypeError, json.JSONDecodeError):
        return {}


def write_runtime_settings(**updates) -> None:
    RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = read_runtime_settings()
    payload.update(updates)
    try:
        RUNTIME_SETTINGS_PATH.write_text(json.dumps(payload, indent=2))
    except OSError as exc:
        st.sidebar.error(f"Could not save runtime settings: {exc}")


def render_kite_connection_controls() -> None:
    st.sidebar.divider()
    st.sidebar.caption("Kite Connection")

    if settings.API_KEY:
        login_url = KiteConnect(api_key=settings.API_KEY).login_url()
        st.sidebar.link_button("Open Kite login", login_url, width="stretch")
    else:
        st.sidebar.warning("Set KITE_API_KEY in .env to generate the login link.")

    kite_token = st.sidebar.text_input(
        "Kite token",
        type="password",
        placeholder="Paste request_token or access_token",
    )
    st.sidebar.caption("After Kite login, paste the request_token from the redirect URL.")

    col1, col2 = st.sidebar.columns(2)
    col1.caption("Token is used only for this connection.")
    if col2.button("Connect", width="stretch"):
        start_tick_receiver(kite_token)


def start_tick_receiver(kite_token: str) -> None:
    token = kite_token.strip()
    if not token:
        st.sidebar.error("Enter the Kite request token or access token first.")
        return

    if is_feed_runner_active():
        st.sidebar.info("Tick receiver is already running.")
        return

    access_token = resolve_access_token(token)
    if not access_token:
        return

    FEED_PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    child_env["SCALPER_UI_CONNECT"] = "1"
    child_env["SCALPER_UI_ACCESS_TOKEN"] = access_token
    with (LOG_DIR / "feed_runner.out.log").open("a") as stdout:
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=str(ROOT_DIR),
            env=child_env,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    FEED_PID_PATH.write_text(str(process.pid))
    st.sidebar.success(f"Tick receiver started. PID {process.pid}.")


def resolve_access_token(token: str) -> str:
    kite = KiteConnect(api_key=settings.API_KEY)
    kite.set_access_token(token)
    try:
        kite.profile()
        return token
    except Exception:
        pass

    if not settings.API_SECRET:
        st.sidebar.error("Set KITE_API_SECRET before using a request token.")
        return ""

    try:
        session = kite.generate_session(token, api_secret=settings.API_SECRET)
        access_token = str(session["access_token"])
        kite.set_access_token(access_token)
        kite.profile()
        return access_token
    except Exception as exc:
        st.sidebar.error(f"Kite token validation failed: {exc}")
        return ""


def is_feed_runner_active() -> bool:
    if not FEED_PID_PATH.exists():
        return False

    try:
        pid = int(FEED_PID_PATH.read_text().strip())
    except (OSError, ValueError):
        FEED_PID_PATH.unlink(missing_ok=True)
        return False

    try:
        os.kill(pid, 0)
    except OSError:
        FEED_PID_PATH.unlink(missing_ok=True)
        return False

    return True


def render_chain(chain: pd.DataFrame, current_path: Path, history_path: Path) -> None:
    st.title("NIFTY OI Scalper")
    st.caption("5 ITM strikes, ATM, and 5 OTM strikes from the live Kite feed.")

    if chain.empty:
        st.info(
            "No option-chain snapshot found yet. Enter today's Kite access "
            "token in the sidebar and click Connect; "
            f"it will write `{current_path.relative_to(ROOT_DIR)}`."
        )
        return

    latest_time = chain["timestamp"].iloc[0]
    underlying = float(chain["underlying_price"].iloc[0])
    atm = float(chain["atm_strike"].iloc[0])
    if {"call_oi", "put_oi"}.issubset(chain.columns):
        total_oi = int(chain["call_oi"].fillna(0).sum() + chain["put_oi"].fillna(0).sum())
    else:
        total_oi = int(chain["oi"].fillna(0).sum())

    if "volume_diff" in chain.columns:
        total_volume_change = int(chain["volume_diff"].fillna(0).sum())
    else:
        total_volume_change = int(chain["volume_change"].fillna(0).sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Underlying", f"{underlying:,.2f}")
    col2.metric("ATM Strike", f"{atm:,.0f}")
    col3.metric("Selected OI", f"{total_oi:,}")
    col4.metric("Volume Diff", f"{total_volume_change:+,}")
    st.caption(f"Last snapshot: {latest_time}")

    table = build_tick_display(chain)
    styled = style_tick_display(table, underlying=underlying, atm=atm)
    st.dataframe(styled, width="stretch", hide_index=True)

    with st.expander("CSV files"):
        st.write(f"Latest snapshot: `{current_path}`")
        st.write(f"History for analysis: `{history_path}`")
        if history_path.exists():
            st.download_button(
                "Download history CSV",
                data=history_path.read_bytes(),
                file_name=history_path.name,
                mime="text/csv",
            )


def render_trades(trades: pd.DataFrame) -> None:
    st.subheader("Trades")
    if trades.empty:
        st.dataframe(pd.DataFrame(), width="stretch")
        return

    daily_pnl = float(pd.to_numeric(trades["pnl"], errors="coerce").fillna(0).sum())
    open_count = int((trades["status"] == "OPEN").sum())
    col1, col2, col3 = st.columns(3)
    col1.metric("Daily PnL", f"Rs {daily_pnl:,.0f}")
    col2.metric("Open Trades", open_count)
    col3.metric("Signals Logged", len(trades))
    st.dataframe(trades, width="stretch", hide_index=True)


def render_logs() -> None:
    st.subheader("System Log")
    st.code(load_log_tail(str(SYSTEM_LOG_PATH)), language="text")


def render_config() -> None:
    st.subheader("Settings")
    config = pd.DataFrame(
        [
            ("Trade mode", settings.TRADE_MODE),
            ("OI threshold", f"{settings.OI_THRESHOLD:,}"),
            ("Tick window", str(settings.TICK_WINDOW)),
            ("Max concurrent scalps", str(settings.MAX_CONCURRENT_SCALPS)),
            ("Daily loss limit", f"Rs {settings.DAILY_LOSS_LIMIT:,.0f}"),
            ("Minimum confidence", f"{settings.MIN_CONFIDENCE:.0%}"),
            ("Option-chain log interval", f"{OPTION_CHAIN_LOG_INTERVAL:.1f}s"),
        ],
        columns=["Setting", "Value"],
    )
    st.dataframe(config, width="stretch", hide_index=True)


def main() -> None:
    index_name = render_sidebar()

    current_path = dated_csv_path(OPTION_CHAIN_CURRENT_SETTING, index_name)
    history_path = dated_csv_path(OPTION_CHAIN_HISTORY_SETTING, index_name)
    chain = load_option_chain(str(current_path))
    trades = load_trades(str(DB_PATH))

    chain_tab, trades_tab, logs_tab, config_tab = st.tabs(
        ["Option Chain", "Trades", "Logs", "Config"]
    )

    with chain_tab:
        render_chain(chain, current_path, history_path)
    with trades_tab:
        render_trades(trades)
    with logs_tab:
        render_logs()
    with config_tab:
        render_config()


if __name__ == "__main__":
    main()
