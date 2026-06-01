# NIFTY OI Scalper

OI-velocity scalping system for Indian indices using Zerodha KiteConnect WebSocket.

## Detects
| Scenario | OI | Price | Trade |
|---|---|---|---|
| Long Buildup | ↑ | ↑ | BUY |
| Short Buildup | ↑ | ↓ | SELL |
| Long Unwinding | ↓ | ↓ | SELL |
| Short Covering | ↓ | ↑ | BUY |

Threshold default: **5 lakh OI change** over 5 ticks fires a signal.

---

## Setup

```bash
# 1. clone / download the project
cd nifty_oi_scalper

# 2. create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. install dependencies
pip install -r requirements.txt

# 4. copy and fill in credentials
cp .env.example .env
# edit .env — add KITE_API_KEY and KITE_API_SECRET
```

---

## Every morning before market open

```bash
python auth.py
# Opens Kite login in browser → paste request_token → access token saved to .env
```

---

## Run

```bash
python main.py
```

- Starts in **PAPER** mode by default (set `TRADE_MODE=LIVE` in `.env` when ready)
- Trades logged to `data/trades.db` and `logs/trades_YYYYMMDD.csv`
- Option-chain snapshots are logged to `data/option_chain_current.csv` and
  `data/option_chain_history.csv`

## Streamlit UI

Run the trading engine and the UI in separate terminals:

```bash
python main.py
streamlit run dashboard/streamlit_app.py
```

The Streamlit app reads local CSV, SQLite, and log files, so it can monitor
all CE/PE strikes, OI, volume changes, trades, config, and logs without placing
orders itself.

---

## Tests

```bash
python -m pytest tests/ -v
```

---

## Project structure

```
nifty_oi_scalper/
├── auth.py                     # one-shot morning auth → saves access token
├── main.py                     # entry point
├── requirements.txt
├── .env.example                # copy to .env and fill in
│
├── config/
│   └── settings.py             # all config from .env
│
├── core/
│   ├── models.py               # OISnapshot, OIEvent, ScalpTrade
│   ├── oi_store.py             # per-strike OI state (PCR, max pain, walls)
│   ├── oi_velocity_tracker.py  # detects the 4 OI scenarios
│   └── feed_handler.py         # KiteTicker WebSocket callbacks
│
├── strategies/
│   └── scalp_strategy.py       # filters events, creates trades
│
├── execution/
│   └── order_executor.py       # paper / live orders + position monitor
│
├── data/
│   ├── instrument_loader.py    # fetches & caches NFO option chain
│   ├── trade_logger.py         # SQLite + CSV trade persistence
│   └── instruments/            # cached instrument CSVs
│
├── dashboard/
│   └── streamlit_app.py        # Streamlit monitoring UI
│
├── logs/                       # system.log + daily trade CSVs
└── tests/
    └── test_classifier.py      # unit tests for OI classification
```

---

## Key config knobs (in `.env`)

| Variable | Default | Meaning |
|---|---|---|
| `OI_THRESHOLD` | 500000 | Minimum OI change (5L) to fire a signal |
| `TRADE_MODE` | PAPER | `PAPER` or `LIVE` |
| `MAX_CONCURRENT_SCALPS` | 2 | Max open positions at once |
| `DAILY_LOSS_LIMIT` | 3000 | Stop trading if daily PnL < -₹3000 |
| `LOT_SIZE` | 25 | Nifty lot size (verify current value) |
"# nifty_oi_scalper" 
