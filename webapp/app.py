"""
Flask web application – API routes and dashboard serving.
"""

import logging
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from sqlalchemy import func, desc

from models import Session, Stock, DailyPrice, FinancialMetric, BatchLog, init_db

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
CORS(app)


# ---------------------------------------------------------------------------
# Dashboard page
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

@app.route("/api/stocks")
def api_stocks():
    """Return stock list with latest metrics, supporting filtering and sorting.

    Query params:
        market  – filter by market (KOSPI / KOSDAQ)
        sector  – substring filter on sector
        q       – substring search on name or code
        sort    – column to sort by (default: code)
        order   – asc / desc (default: asc)
        page    – page number (default: 1)
        size    – page size (default: 50)
    """
    session = Session()
    try:
        market = request.args.get("market")
        sector = request.args.get("sector")
        q = request.args.get("q")
        sort_col = request.args.get("sort", "code")
        order = request.args.get("order", "asc")
        page = max(int(request.args.get("page", 1)), 1)
        size = min(int(request.args.get("size", 50)), 200)

        # Latest snapshot date
        latest_date = session.query(func.max(FinancialMetric.snapshot_date)).scalar()
        if latest_date is None:
            latest_date = date.today()

        # Base query: join Stock with latest FinancialMetric
        query = (
            session.query(Stock, FinancialMetric)
            .outerjoin(
                FinancialMetric,
                (Stock.code == FinancialMetric.code)
                & (FinancialMetric.snapshot_date == latest_date),
            )
        )

        # Filters
        if market:
            query = query.filter(Stock.market == market.upper())
        if sector:
            query = query.filter(Stock.sector.ilike(f"%{sector}%"))
        if q:
            query = query.filter(
                (Stock.name.ilike(f"%{q}%")) | (Stock.code.ilike(f"%{q}%"))
            )

        # Total count before pagination
        total = query.count()

        # Sorting
        sortable = {
            "code": Stock.code,
            "name": Stock.name,
            "market": Stock.market,
            "sector": Stock.sector,
            "per": FinancialMetric.per,
            "pbr": FinancialMetric.pbr,
            "roe": FinancialMetric.roe,
            "eps": FinancialMetric.eps,
            "bps": FinancialMetric.bps,
            "dividend_yield": FinancialMetric.dividend_yield,
            "rsi14": FinancialMetric.rsi14,
            "change_pct": FinancialMetric.change_pct,
            "ma5": FinancialMetric.ma5,
            "ma20": FinancialMetric.ma20,
            "ma60": FinancialMetric.ma60,
        }
        col = sortable.get(sort_col, Stock.code)
        query = query.order_by(desc(col) if order == "desc" else col)

        # Pagination
        rows = query.offset((page - 1) * size).limit(size).all()

        items = []
        for stock, metric in rows:
            item = stock.to_dict()
            if metric:
                item.update(metric.to_dict())
            items.append(item)

        return jsonify(
            {
                "total": total,
                "page": page,
                "size": size,
                "snapshot_date": latest_date.isoformat() if latest_date else None,
                "items": items,
            }
        )
    finally:
        session.close()


@app.route("/api/stocks/<code>")
def api_stock_detail(code: str):
    """Return detail for a single stock including recent price history."""
    session = Session()
    try:
        stock = session.get(Stock, code)
        if stock is None:
            return jsonify({"error": "Stock not found"}), 404

        data = stock.to_dict()

        # Latest metric
        metric = (
            session.query(FinancialMetric)
            .filter_by(code=code)
            .order_by(desc(FinancialMetric.snapshot_date))
            .first()
        )
        if metric:
            data["metrics"] = metric.to_dict()

        # Recent prices (last 60 days)
        prices = (
            session.query(DailyPrice)
            .filter_by(code=code)
            .order_by(desc(DailyPrice.trade_date))
            .limit(60)
            .all()
        )
        data["prices"] = [p.to_dict() for p in reversed(prices)]

        return jsonify(data)
    finally:
        session.close()


@app.route("/api/batch/status")
def api_batch_status():
    """Return recent batch job logs."""
    session = Session()
    try:
        logs = (
            session.query(BatchLog)
            .order_by(desc(BatchLog.started_at))
            .limit(10)
            .all()
        )
        return jsonify([log.to_dict() for log in logs])
    finally:
        session.close()


@app.route("/api/batch/trigger", methods=["POST"])
def api_batch_trigger():
    """Manually trigger the pipeline (async via scheduler or thread)."""
    import threading
    from pipeline import run_pipeline

    limit = request.json.get("limit") if request.is_json else None
    thread = threading.Thread(target=run_pipeline, kwargs={"limit": limit}, daemon=True)
    thread.start()
    return jsonify({"status": "triggered", "message": "Pipeline started in background"})


@app.route("/api/markets/summary")
def api_market_summary():
    """Return aggregate summary per market."""
    session = Session()
    try:
        latest_date = session.query(func.max(FinancialMetric.snapshot_date)).scalar()
        if latest_date is None:
            return jsonify([])

        results = []
        for market in ("KOSPI", "KOSDAQ"):
            count = session.query(Stock).filter_by(market=market).count()
            avg_per = (
                session.query(func.avg(FinancialMetric.per))
                .join(Stock, Stock.code == FinancialMetric.code)
                .filter(
                    Stock.market == market,
                    FinancialMetric.snapshot_date == latest_date,
                    FinancialMetric.per.isnot(None),
                )
                .scalar()
            )
            avg_pbr = (
                session.query(func.avg(FinancialMetric.pbr))
                .join(Stock, Stock.code == FinancialMetric.code)
                .filter(
                    Stock.market == market,
                    FinancialMetric.snapshot_date == latest_date,
                    FinancialMetric.pbr.isnot(None),
                )
                .scalar()
            )
            results.append(
                {
                    "market": market,
                    "stock_count": count,
                    "avg_per": round(avg_per, 2) if avg_per else None,
                    "avg_pbr": round(avg_pbr, 2) if avg_pbr else None,
                }
            )
        return jsonify(results)
    finally:
        session.close()
