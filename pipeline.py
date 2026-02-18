"""
Pipeline orchestrator: runs quant_collector_enhanced → quant_screener
and saves dashboard results to DuckDB alongside the Excel outputs.
"""

import logging
from datetime import datetime

import db as _db
from quant_collector_enhanced import run_full as collector_run, test_crawling
from quant_screener import (
    load_table,
    preprocess_indicators,
    detect_unit_multiplier,
    analyze_all,
    calc_valuation,
    calc_technical_indicators,
    apply_screen,
    apply_momentum_screen,
    apply_garp_screen,
    apply_cashcow_screen,
    apply_turnaround_screen,
    apply_dividend_growth_screen,
    save_to_excel,
    DATA_DIR,
)

log = logging.getLogger("PIPELINE")


def run_pipeline(skip_collect: bool = False, test_mode: bool = False):
    """Run full pipeline: collect data then screen.

    Args:
        skip_collect: If True, skip collection and only run screener
            (useful when data already exists in DB).
        test_mode: If True, only collect 3 sample stocks.
    """
    start = datetime.now()
    log.info("Pipeline started at %s", start.strftime("%Y-%m-%d %H:%M:%S"))

    _db.init_db()

    # ── Step 1: Collect ──
    if not skip_collect:
        if test_mode:
            log.info("Running collector in TEST mode (3 stocks)...")
            collector_run(test_mode=True)
        else:
            log.info("Running full collector...")
            collector_run()
    else:
        log.info("Skipping collection (--skip-collect)")

    # ── Step 2: Screen & Analyse ──
    log.info("Running screener...")
    master = load_table("master")
    daily = load_table("daily")
    fs = load_table("financial_statements")
    ind = load_table("indicators")
    shares = load_table("shares")
    price_hist = load_table("price_history")

    if daily.empty:
        log.error("daily data not found in DB – cannot run screener")
        return

    ind = preprocess_indicators(ind)
    multiplier = detect_unit_multiplier(ind)
    anal_df = analyze_all(fs, ind)
    full_df = calc_valuation(daily, anal_df, multiplier, shares)

    # 기술적 지표 (주가 히스토리 기반)
    full_df = calc_technical_indicators(full_df, price_hist)

    # Merge market/sector info from master
    if not master.empty and "시장구분" in master.columns:
        master_info = master[["종목코드", "시장구분", "종목구분"]].drop_duplicates("종목코드")
        full_df = full_df.merge(master_info, on="종목코드", how="left")

    # ── Save dashboard to DB ──
    _db.save_dashboard(full_df)
    log.info("Dashboard saved to DB (%d rows)", len(full_df))

    # ── Save Excel outputs (same as original screener) ──
    save_to_excel(
        full_df.sort_values("종합점수", ascending=False),
        DATA_DIR / "quant_all_stocks.xlsx", "전체종목",
    )

    screened = apply_screen(full_df)
    save_to_excel(screened, DATA_DIR / "quant_screened.xlsx", "우량주")

    momentum_df = apply_momentum_screen(full_df)
    save_to_excel(momentum_df, DATA_DIR / "quant_momentum.xlsx", "모멘텀")

    garp_df = apply_garp_screen(full_df)
    save_to_excel(garp_df, DATA_DIR / "quant_GARP.xlsx", "GARP")

    cashcow_df = apply_cashcow_screen(full_df)
    save_to_excel(cashcow_df, DATA_DIR / "quant_cashcow.xlsx", "캐시카우")

    turnaround_df = apply_turnaround_screen(full_df)
    save_to_excel(turnaround_df, DATA_DIR / "quant_turnaround.xlsx", "턴어라운드")

    dividend_growth_df = apply_dividend_growth_screen(full_df)
    save_to_excel(dividend_growth_df, DATA_DIR / "quant_dividend_growth.xlsx", "배당성장")

    elapsed = datetime.now() - start
    log.info(
        "Pipeline finished in %s — %d total, %d screened, %d momentum, "
        "%d GARP, %d cashcow, %d turnaround, %d dividend_growth",
        elapsed, len(full_df), len(screened), len(momentum_df),
        len(garp_df), len(cashcow_df), len(turnaround_df),
        len(dividend_growth_df),
    )
