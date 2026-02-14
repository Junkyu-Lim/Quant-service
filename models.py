from datetime import datetime, date

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Date,
    DateTime,
    BigInteger,
    Index,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

import config

Base = declarative_base()


class Stock(Base):
    """Master table for listed stocks."""

    __tablename__ = "stocks"

    code = Column(String(20), primary_key=True)        # ticker code e.g. "005930"
    name = Column(String(100), nullable=False)
    market = Column(String(10), nullable=False)         # KOSPI or KOSDAQ
    sector = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "market": self.market,
            "sector": self.sector,
        }


class DailyPrice(Base):
    """Daily OHLCV price data."""

    __tablename__ = "daily_prices"
    __table_args__ = (
        Index("ix_daily_code_date", "code", "trade_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False)
    trade_date = Column(Date, nullable=False)
    open = Column(Integer)
    high = Column(Integer)
    low = Column(Integer)
    close = Column(Integer)
    volume = Column(BigInteger)
    market_cap = Column(BigInteger)

    def to_dict(self):
        return {
            "code": self.code,
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "market_cap": self.market_cap,
        }


class FinancialMetric(Base):
    """Computed financial metrics per stock snapshot."""

    __tablename__ = "financial_metrics"
    __table_args__ = (
        Index("ix_metric_code_date", "code", "snapshot_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False)
    snapshot_date = Column(Date, nullable=False, default=date.today)

    per = Column(Float)           # Price-to-Earnings Ratio
    pbr = Column(Float)           # Price-to-Book Ratio
    eps = Column(Float)           # Earnings Per Share
    bps = Column(Float)           # Book Value Per Share
    dividend_yield = Column(Float)
    roe = Column(Float)           # Return on Equity (%)
    roa = Column(Float)           # Return on Assets (%)
    debt_ratio = Column(Float)    # Debt Ratio (%)

    # Technical indicators
    ma5 = Column(Float)           # 5-day moving average
    ma20 = Column(Float)          # 20-day moving average
    ma60 = Column(Float)          # 60-day moving average
    rsi14 = Column(Float)         # 14-day RSI
    change_pct = Column(Float)    # Daily change %

    def to_dict(self):
        return {
            "code": self.code,
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
            "per": self.per,
            "pbr": self.pbr,
            "eps": self.eps,
            "bps": self.bps,
            "dividend_yield": self.dividend_yield,
            "roe": self.roe,
            "roa": self.roa,
            "debt_ratio": self.debt_ratio,
            "ma5": self.ma5,
            "ma20": self.ma20,
            "ma60": self.ma60,
            "rsi14": self.rsi14,
            "change_pct": self.change_pct,
        }


class BatchLog(Base):
    """Tracks batch job execution history."""

    __tablename__ = "batch_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(100), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String(20), default="running")   # running / success / failed
    message = Column(String(500))
    stocks_processed = Column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "job_name": self.job_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "message": self.message,
            "stocks_processed": self.stocks_processed,
        }


# ---------------------------------------------------------------------------
# Engine / Session helpers
# ---------------------------------------------------------------------------

engine = create_engine(config.DATABASE_URL, echo=False)


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(engine)


Session = sessionmaker(bind=engine)
