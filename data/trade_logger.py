"""
data/trade_logger.py
Persists every trade to a SQLite database using SQLAlchemy core.
Also writes a CSV log for easy spreadsheet analysis.
"""
import csv
import logging
import os
from datetime import datetime

from sqlalchemy import (Column, DateTime, Float, Integer, String,
                        create_engine, text)
from sqlalchemy.orm import DeclarativeBase, Session

from config.settings import settings
from core.models import ScalpTrade

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class TradeRecord(Base):
    __tablename__ = "trades"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    trade_date    = Column(DateTime, default=datetime.now)
    scenario      = Column(String)
    instrument    = Column(String)
    tradingsymbol = Column(String)
    direction     = Column(String)
    oi_change     = Column(Integer)
    confidence    = Column(Float)
    entry_price   = Column(Float)
    stop_loss     = Column(Float)
    target        = Column(Float)
    exit_price    = Column(Float, nullable=True)
    exit_time     = Column(DateTime, nullable=True)
    status        = Column(String, default="OPEN")
    pnl           = Column(Float, default=0.0)
    order_id      = Column(String, default="")


class TradeLogger:
    def __init__(self):
        os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
        self.engine = create_engine(f"sqlite:///{settings.DB_PATH}")
        Base.metadata.create_all(self.engine)
        logger.info(f"Trade DB ready at {settings.DB_PATH}")

        # CSV path — one file per date
        date_str      = datetime.now().strftime("%Y%m%d")
        os.makedirs(settings.LOG_DIR, exist_ok=True)
        self.csv_path = os.path.join(settings.LOG_DIR, f"trades_{date_str}.csv")
        self._init_csv()

    # ------------------------------------------------------------------
    # Write new trade (entry)
    # ------------------------------------------------------------------
    def log(self, trade: ScalpTrade):
        ev = trade.event
        with Session(self.engine) as session:
            rec = TradeRecord(
                trade_date    = ev.timestamp,
                scenario      = ev.scenario,
                instrument    = ev.instrument,
                tradingsymbol = ev.tradingsymbol,
                direction     = ev.trade_direction,
                oi_change     = ev.oi_change,
                confidence    = ev.confidence,
                entry_price   = trade.entry_price,
                stop_loss     = trade.sl,
                target        = trade.target,
                status        = "OPEN",
                order_id      = trade.order_id,
            )
            session.add(rec)
            session.commit()
            # store DB id on the trade object for future updates
            trade._db_id = rec.id

    # ------------------------------------------------------------------
    # Update existing trade (exit)
    # ------------------------------------------------------------------
    def update(self, trade: ScalpTrade):
        db_id = getattr(trade, "_db_id", None)
        if db_id is None:
            return
        with Session(self.engine) as session:
            session.execute(
                text("""UPDATE trades
                        SET exit_price=:ep, exit_time=:et, status=:st, pnl=:pnl
                        WHERE id=:id"""),
                {"ep": trade.exit_price, "et": trade.exit_time,
                 "st": trade.status, "pnl": trade.pnl, "id": db_id},
            )
            session.commit()
        self._append_csv(trade)

    # ------------------------------------------------------------------
    # CSV helpers
    # ------------------------------------------------------------------
    _CSV_HEADERS = [
        "entry_time", "exit_time", "scenario", "instrument", "direction",
        "oi_change", "confidence", "entry", "sl", "target",
        "exit_price", "status", "pnl",
    ]

    def _init_csv(self):
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="") as f:
                csv.writer(f).writerow(self._CSV_HEADERS)

    def _append_csv(self, trade: ScalpTrade):
        ev = trade.event
        with open(self.csv_path, "a", newline="") as f:
            csv.writer(f).writerow([
                ev.timestamp, trade.exit_time, ev.scenario, ev.instrument,
                ev.trade_direction, ev.oi_change, ev.confidence,
                trade.entry_price, trade.sl, trade.target,
                trade.exit_price, trade.status, trade.pnl,
            ])
