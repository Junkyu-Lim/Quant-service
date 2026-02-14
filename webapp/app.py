"""
Flask web application – CSV-based API for the Quant dashboard.
Reads dashboard_result.csv produced by the pipeline and serves it
with server-side filtering, sorting, and pagination.
"""

import logging
import os
import threading
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

import config

log = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
CORS(app)

# ── In-memory data cache ──
_cache: dict = {"df": pd.DataFrame(), "mtime": 0}

RESULT_CSV = config.DATA_DIR / "dashboard_result.csv"

# Columns exposed to the frontend
DISPLAY_COLS = [
    "종목코드", "종목명", "시장구분", "종가", "시가총액",
    "PER", "PBR", "PSR", "PEG", "ROE(%)", "EPS", "BPS",
    "부채비율(%)", "영업이익률(%)", "이익수익률(%)", "FCF수익률(%)",
    "배당수익률(%)", "이익품질_양호",
    "매출_CAGR", "영업이익_CAGR", "순이익_CAGR",
    "매출_연속성장", "영업이익_연속성장", "순이익_연속성장",
    "이익률_개선", "이익률_급개선", "이익률_변동폭",
    "흑자전환", "영업이익률_최근", "영업이익률_전년",
    "적정주가_SRIM", "괴리율(%)",
    "종합점수",
    "TTM_매출", "TTM_영업이익", "TTM_순이익", "TTM_영업CF",
    "자본", "부채",
]


def _load_data() -> pd.DataFrame:
    """Load (or reload) dashboard CSV into cache."""
    if not RESULT_CSV.exists():
        _cache["df"] = pd.DataFrame()
        _cache["mtime"] = 0
        return _cache["df"]

    mtime = os.path.getmtime(RESULT_CSV)
    if mtime != _cache["mtime"]:
        df = pd.read_csv(RESULT_CSV, encoding="utf-8-sig", dtype={"종목코드": str})
        df["종목코드"] = df["종목코드"].str.zfill(6)
        df = df.replace({np.nan: None})
        _cache["df"] = df
        _cache["mtime"] = mtime
        log.info("Loaded %d rows from %s", len(df), RESULT_CSV.name)

    return _cache["df"]


def _safe_val(v):
    """Convert numpy types to JSON-safe Python types."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4) if not np.isnan(v) else None
    return v


def _row_to_dict(row, cols):
    return {c: _safe_val(row.get(c)) for c in cols if c in row.index}


# ─────────────────────────────────────────
# Pages
# ─────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ─────────────────────────────────────────
# REST API
# ─────────────────────────────────────────

@app.route("/api/stocks")
def api_stocks():
    """Paginated stock list with filtering, sorting, and screening tab support.

    Query params:
        screen  – screening filter: all / screened / momentum / garp / cashcow / turnaround
        market  – KOSPI / KOSDAQ
        q       – substring search (name or code)
        sort    – column name to sort by
        order   – asc / desc
        page    – page number (1-based)
        size    – page size (max 200)
    """
    df = _load_data()
    if df.empty:
        return jsonify({"total": 0, "page": 1, "size": 50, "items": []})

    screen = request.args.get("screen", "all")
    market = request.args.get("market", "")
    q = request.args.get("q", "").strip()
    sort_col = request.args.get("sort", "종합점수")
    order = request.args.get("order", "desc")
    page = max(int(request.args.get("page", 1)), 1)
    size = min(int(request.args.get("size", 50)), 200)

    filtered = df.copy()

    # ── Screening filter ──
    if screen == "screened":
        filtered = _apply_screen_filter(filtered, "screened")
    elif screen == "momentum":
        filtered = _apply_screen_filter(filtered, "momentum")
    elif screen == "garp":
        filtered = _apply_screen_filter(filtered, "garp")
    elif screen == "cashcow":
        filtered = _apply_screen_filter(filtered, "cashcow")
    elif screen == "turnaround":
        filtered = _apply_screen_filter(filtered, "turnaround")

    # ── Market filter ──
    if market and "시장구분" in filtered.columns:
        filtered = filtered[filtered["시장구분"] == market.upper()]

    # ── Text search ──
    if q:
        mask = (
            filtered["종목명"].str.contains(q, case=False, na=False)
            | filtered["종목코드"].str.contains(q, case=False, na=False)
        )
        filtered = filtered[mask]

    total = len(filtered)

    # ── Sort ──
    if sort_col in filtered.columns:
        asc = order != "desc"
        filtered = filtered.sort_values(sort_col, ascending=asc, na_position="last")

    # ── Paginate ──
    start = (page - 1) * size
    page_df = filtered.iloc[start : start + size]

    available = [c for c in DISPLAY_COLS if c in page_df.columns]
    items = [_row_to_dict(row, available) for _, row in page_df.iterrows()]

    return jsonify({"total": total, "page": page, "size": size, "items": items})


@app.route("/api/stocks/<code>")
def api_stock_detail(code: str):
    """Detail view for a single stock."""
    df = _load_data()
    if df.empty:
        return jsonify({"error": "No data"}), 404

    row = df[df["종목코드"] == code.zfill(6)]
    if row.empty:
        return jsonify({"error": "Stock not found"}), 404

    data = {c: _safe_val(row.iloc[0].get(c)) for c in df.columns}
    return jsonify(data)


@app.route("/api/markets/summary")
def api_market_summary():
    """Aggregate stats per market."""
    df = _load_data()
    if df.empty or "시장구분" not in df.columns:
        return jsonify([])

    results = []
    for mkt in ("KOSPI", "KOSDAQ"):
        sub = df[df["시장구분"] == mkt]
        results.append({
            "market": mkt,
            "stock_count": len(sub),
            "avg_per": _safe_val(sub["PER"].median()) if "PER" in sub.columns else None,
            "avg_pbr": _safe_val(sub["PBR"].median()) if "PBR" in sub.columns else None,
            "avg_roe": _safe_val(sub["ROE(%)"].median()) if "ROE(%)" in sub.columns else None,
        })
    return jsonify(results)


@app.route("/api/batch/trigger", methods=["POST"])
def api_batch_trigger():
    """Manually trigger the pipeline in background."""
    from pipeline import run_pipeline

    opts = {}
    if request.is_json:
        opts["skip_collect"] = request.json.get("skip_collect", False)
        opts["test_mode"] = request.json.get("test_mode", False)

    thread = threading.Thread(target=run_pipeline, kwargs=opts, daemon=True)
    thread.start()
    return jsonify({"status": "triggered", "message": "파이프라인이 백그라운드에서 시작되었습니다"})


@app.route("/api/data/status")
def api_data_status():
    """Check what data files exist."""
    files = {}
    for name in ["master", "daily", "financial_statements", "indicators", "shares", "dashboard_result"]:
        candidates = list(config.DATA_DIR.glob(f"{name}*.csv"))
        if candidates:
            latest = sorted(candidates)[-1]
            files[name] = {
                "file": latest.name,
                "size_mb": round(latest.stat().st_size / 1_048_576, 2),
                "modified": pd.Timestamp(latest.stat().st_mtime, unit="s").isoformat(),
            }
    return jsonify(files)


# ─────────────────────────────────────────
# Screening helpers (mirror quant_screener logic)
# ─────────────────────────────────────────

def _apply_screen_filter(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Apply screening filters matching quant_screener.py logic."""
    if name == "screened":
        mask = (
            df["TTM_순이익"].notna() & (df["TTM_순이익"] > 0)
            & (df["ROE(%)"] >= 5)
            & df["PER"].between(1, 50)
            & df["PBR"].between(0.1, 10)
            & (df["매출_연속성장"] >= 2)
            & (df["순이익_연속성장"] >= 1)
            & (df["시가총액"] >= 50_000_000_000)
        )
        if "PER_이상" in df.columns:
            mask = mask & (df["PER_이상"] == "")
        return df[mask]

    elif name == "momentum":
        mask = (
            df["매출_CAGR"].notna() & df["영업이익_CAGR"].notna()
            & ((df["매출_CAGR"] >= 15) | (df["영업이익_CAGR"] >= 15))
            & (df["이익률_개선"] == 1)
            & (df["ROE(%)"] >= 5)
            & (df["TTM_순이익"] > 0)
            & (df["시가총액"] >= 50_000_000_000)
        )
        return df[mask]

    elif name == "garp":
        mask = (
            df["PEG"].notna() & (df["PEG"] > 0) & (df["PEG"] < 1.5)
            & df["매출_CAGR"].notna() & (df["매출_CAGR"] >= 10)
            & df["ROE(%)"].notna() & (df["ROE(%)"] >= 12)
            & df["PER"].notna() & df["PER"].between(5, 30)
            & (df["시가총액"] >= 50_000_000_000)
            & (df["TTM_순이익"] > 0)
        )
        if "PER_이상" in df.columns:
            mask = mask & (df["PER_이상"] == "")
        return df[mask]

    elif name == "cashcow":
        mask = (
            df["FCF수익률(%)"].notna() & (df["FCF수익률(%)"] >= 5)
            & (df["이익품질_양호"] == 1)
            & df["영업이익률(%)"].notna() & (df["영업이익률(%)"] >= 8)
            & (
                (df["부채비율(%)"].notna() & (df["부채비율(%)"] < 100))
                | df["부채비율(%)"].isna()
            )
            & (df["시가총액"] >= 50_000_000_000)
            & (df["TTM_순이익"] > 0)
        )
        return df[mask]

    elif name == "turnaround":
        mask = (
            ((df["흑자전환"] == 1) | (df["이익률_급개선"] == 1))
            & (df["TTM_순이익"] > 0)
            & (df["시가총액"] >= 30_000_000_000)
        )
        return df[mask]

    return df
