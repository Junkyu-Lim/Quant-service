"""
Flask web application – SQLite-based API for the Quant dashboard.
Reads dashboard_result from SQLite DB produced by the pipeline and serves it
with server-side filtering, sorting, and pagination.
"""

import json
import logging
import os
import threading

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

import config
import db as _db
from analysis.claude_analyzer import generate_report

log = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
CORS(app)

# ── In-memory data cache ──
_cache: dict = {"df": pd.DataFrame(), "mtime": 0}

# Columns exposed to the frontend
DISPLAY_COLS = [
    "종목코드", "종목명", "시장구분", "종가", "시가총액",
    "PER", "PBR", "PSR", "PEG", "ROE(%)", "EPS", "BPS",
    "부채비율(%)", "영업이익률(%)", "이익수익률(%)", "FCF수익률(%)",
    "배당수익률(%)", "이익품질_양호", "현금전환율(%)", "CAPEX비율(%)",
    "부채상환능력", "F스코어",
    "52주_최고대비(%)", "52주_최저대비(%)", "MA20_이격도(%)", "MA60_이격도(%)",
    "RSI_14", "거래대금_20일평균", "거래대금_증감(%)", "변동성_60일(%)",
    "매출_CAGR", "영업이익_CAGR", "순이익_CAGR", "영업CF_CAGR", "FCF_CAGR",
    "DPS_최근", "DPS_CAGR", "배당_연속증가", "배당_수익동반증가",
    "매출_연속성장", "영업이익_연속성장", "순이익_연속성장", "영업CF_연속성장",
    "이익률_개선", "이익률_급개선", "이익률_변동폭",
    "흑자전환", "영업이익률_최근", "영업이익률_전년",
    "적정주가_SRIM", "괴리율(%)",
    "종합점수",
    "TTM_매출", "TTM_영업이익", "TTM_순이익", "TTM_영업CF", "TTM_CAPEX", "TTM_FCF",
    "자본", "부채", "자산총계",
]


def _load_data() -> pd.DataFrame:
    """Load (or reload) dashboard data from DB into cache."""
    db_path = str(config.DB_PATH)
    if not os.path.exists(db_path):
        _cache["df"] = pd.DataFrame()
        _cache["mtime"] = 0
        return _cache["df"]

    mtime = os.path.getmtime(db_path)
    if mtime != _cache["mtime"]:
        df = _db.load_dashboard()
        if not df.empty:
            if "종목코드" in df.columns:
                df["종목코드"] = df["종목코드"].astype(str).str.zfill(6)
            df = df.replace({np.nan: None})
        _cache["df"] = df
        _cache["mtime"] = mtime
        log.info("Loaded %d rows from DB (dashboard_result)", len(df))

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
        screen  – screening filter: all / screened / momentum / garp / cashcow / turnaround / dividend_growth
        market  – KOSPI / KOSDAQ
        q       – substring search (name or code)
        sort    – column name to sort by
        order   – asc / desc
        page    – page number (1-based)
        size    – page size (max 200)
        min_*   – minimum value for column (e.g., min_PER=10)
        max_*   – maximum value for column (e.g., max_PER=20)
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
    elif screen == "dividend_growth":
        filtered = _apply_screen_filter(filtered, "dividend_growth")

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

    # ── Column range filters ──
    for key, val in request.args.items():
        if key.startswith("min_"):
            col = key[4:]  # Remove "min_" prefix
            if col in filtered.columns:
                try:
                    filtered = filtered[filtered[col] >= float(val)]
                except (ValueError, TypeError):
                    pass
        elif key.startswith("max_"):
            col = key[4:]  # Remove "max_" prefix
            if col in filtered.columns:
                try:
                    filtered = filtered[filtered[col] <= float(val)]
                except (ValueError, TypeError):
                    pass

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
    """Check what data exists in the DB."""
    status = _db.get_data_status()

    # DB 파일 크기 정보 추가
    db_path = str(config.DB_PATH)
    if os.path.exists(db_path):
        status["_db"] = {
            "file": config.DB_PATH.name,
            "size_mb": round(os.path.getsize(db_path) / 1_048_576, 2),
            "modified": pd.Timestamp(os.path.getmtime(db_path), unit="s").isoformat(),
        }

    return jsonify(status)


# ─────────────────────────────────────────
# Analysis Report API
# ─────────────────────────────────────────

@app.route("/api/stocks/<code>/report")
def api_get_report(code: str):
    """Get existing analysis report for a stock."""
    report = _db.load_report(code.zfill(6))
    if report is None:
        return jsonify({"exists": False}), 200
    return jsonify({
        "exists": True,
        "report_html": report["report_html"],
        "scores": json.loads(report["scores_json"]) if report["scores_json"] else {},
        "model_used": report["model_used"],
        "generated_date": report["generated_date"],
        "종목명": report["종목명"],
    })


@app.route("/api/stocks/<code>/report", methods=["POST"])
def api_generate_report(code: str):
    """Generate a new analysis report using Claude API."""
    if not config.ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY가 설정되지 않았습니다."}), 500

    df = _load_data()
    if df.empty:
        return jsonify({"error": "데이터 없음"}), 404

    row = df[df["종목코드"] == code.zfill(6)]
    if row.empty:
        return jsonify({"error": "종목을 찾을 수 없습니다."}), 404

    stock_data = {c: _safe_val(row.iloc[0].get(c)) for c in df.columns}

    try:
        result = generate_report(stock_data)

        _db.init_db()
        _db.save_report(
            code=code.zfill(6),
            name=stock_data.get("종목명", ""),
            html=result["report_html"],
            scores_json=json.dumps(result["scores"], ensure_ascii=False),
            model=result["model"],
            date=result["generated_date"],
        )

        return jsonify({
            "exists": True,
            "report_html": result["report_html"],
            "scores": result["scores"],
            "model_used": result["model"],
            "generated_date": result["generated_date"],
            "종목명": stock_data.get("종목명", ""),
        })
    except Exception as e:
        log.exception("Report generation failed for %s", code)
        return jsonify({"error": str(e)}), 500


@app.route("/api/reports")
def api_list_reports():
    """List all generated reports."""
    return jsonify(_db.list_reports())


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
            & (df["F스코어"] >= 5)
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
            df["ROE(%)"].notna() & (df["ROE(%)"] >= 10)
            & df["영업이익률(%)"].notna() & (df["영업이익률(%)"] >= 10)
            & (
                (df["부채비율(%)"].notna() & (df["부채비율(%)"] < 100))
                | df["부채비율(%)"].isna()
            )
            & (df["매출_연속성장"] >= 1)
            & (df["시가총액"] >= 50_000_000_000)
            & (df["TTM_순이익"] > 0)
            & (df["이익품질_양호"] == 1)
            & (df["F스코어"] >= 6)
        )
        return df[mask]

    elif name == "turnaround":
        mask = (
            ((df["흑자전환"] == 1) | (df["이익률_급개선"] == 1))
            & (df["TTM_순이익"] > 0)
            & (df["시가총액"] >= 30_000_000_000)
        )
        return df[mask]

    elif name == "dividend_growth":
        mask = (
            (df["순이익_연속성장"] >= 2)
            & (df["배당_연속증가"] >= 1)
            & df["DPS_CAGR"].notna() & (df["DPS_CAGR"] > 0)
            & df["ROE(%)"].notna() & (df["ROE(%)"] >= 5)
            & (df["배당수익률(%)"] > 0)
            & (df["시가총액"] >= 30_000_000_000)
            & (df["TTM_순이익"] > 0)
            & (df["배당_수익동반증가"] == 1)
        )
        return df[mask]

    return df
