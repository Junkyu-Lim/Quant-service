"""
Main pipeline: orchestrates scraping, analysis, and database persistence.
"""

import logging
import time
from datetime import date, datetime

import config
from models import (
    Session,
    Stock,
    DailyPrice,
    FinancialMetric,
    BatchLog,
    init_db,
)
from scraper.krx import fetch_all_listings, fetch_daily_prices, fetch_fundamental
from analysis.analyzer import analyze_stock

logger = logging.getLogger(__name__)


def sync_stock_listings(session) -> list[Stock]:
    """Fetch latest listings and upsert into the stocks table."""
    df = fetch_all_listings()
    stocks = []
    for _, row in df.iterrows():
        stock = session.get(Stock, row["code"])
        if stock is None:
            stock = Stock(
                code=row["code"],
                name=row["name"],
                market=row["market"],
                sector=row["sector"],
            )
            session.add(stock)
        else:
            stock.name = row["name"]
            stock.market = row["market"]
            stock.sector = row["sector"]
            stock.updated_at = datetime.utcnow()
        stocks.append(stock)
    session.commit()
    logger.info("Synced %d stock listings", len(stocks))
    return stocks


def process_stock(session, stock: Stock, today: date) -> bool:
    """Scrape and analyse a single stock; persist results. Returns True on success."""
    try:
        # 1. Daily prices
        prices_df = fetch_daily_prices(stock.code, pages=3)
        for _, row in prices_df.iterrows():
            exists = (
                session.query(DailyPrice)
                .filter_by(code=stock.code, trade_date=row["trade_date"])
                .first()
            )
            if exists is None:
                session.add(
                    DailyPrice(
                        code=stock.code,
                        trade_date=row["trade_date"],
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                    )
                )

        # 2. Fundamentals
        fundamentals = fetch_fundamental(stock.code)

        # Update market_cap on latest price row if available
        if fundamentals.get("market_cap") and not prices_df.empty:
            latest_date = prices_df["trade_date"].max()
            dp = (
                session.query(DailyPrice)
                .filter_by(code=stock.code, trade_date=latest_date)
                .first()
            )
            if dp:
                dp.market_cap = fundamentals["market_cap"]

        # 3. Analysis
        metrics = analyze_stock(prices_df, fundamentals)

        # Upsert financial metric for today
        fm = (
            session.query(FinancialMetric)
            .filter_by(code=stock.code, snapshot_date=today)
            .first()
        )
        if fm is None:
            fm = FinancialMetric(code=stock.code, snapshot_date=today)
            session.add(fm)
        for k, v in metrics.items():
            setattr(fm, k, v)

        session.commit()
        return True

    except Exception:
        session.rollback()
        logger.exception("Failed processing %s (%s)", stock.code, stock.name)
        return False


def run_pipeline(limit: int | None = None):
    """Run the full pipeline end-to-end.

    Args:
        limit: If set, only process this many stocks (useful for testing).
    """
    init_db()
    session = Session()
    today = date.today()

    # Log start
    batch_log = BatchLog(job_name="daily_pipeline", started_at=datetime.utcnow())
    session.add(batch_log)
    session.commit()

    try:
        # Step 1 - sync listings
        stocks = sync_stock_listings(session)
        if limit:
            stocks = stocks[:limit]

        # Step 2 - process each stock
        success_count = 0
        for i, stock in enumerate(stocks, 1):
            logger.info("[%d/%d] Processing %s %s", i, len(stocks), stock.code, stock.name)
            if process_stock(session, stock, today):
                success_count += 1
            time.sleep(config.REQUEST_DELAY)

        batch_log.status = "success"
        batch_log.stocks_processed = success_count
        batch_log.message = f"Processed {success_count}/{len(stocks)} stocks"

    except Exception as exc:
        batch_log.status = "failed"
        batch_log.message = str(exc)[:500]
        logger.exception("Pipeline failed")

    finally:
        batch_log.finished_at = datetime.utcnow()
        session.commit()
        session.close()

    logger.info("Pipeline finished: %s", batch_log.message)
