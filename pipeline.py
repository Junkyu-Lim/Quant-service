"""
Pipeline orchestrator: runs quant_collector_enhanced → quant_screener
and saves a dashboard-ready CSV alongside the Excel outputs.
"""

import logging
from datetime import datetime

from quant_collector_enhanced import run_full as collector_run, test_crawling
from quant_screener import (
    load_csv,
    preprocess_indicators,
    detect_unit_multiplier,
    analyze_all,
    calc_valuation,
    apply_screen,
    apply_momentum_screen,
    apply_garp_screen,
    apply_cashcow_screen,
    apply_turnaround_screen,
    save_to_excel,
    DATA_DIR,
)

log = logging.getLogger("PIPELINE")


def run_pipeline(skip_collect: bool = False, test_mode: bool = False):
    """Run full pipeline: collect data then screen.

    Args:
        skip_collect: If True, skip collection and only run screener
            (useful when CSV data already exists).
        test_mode: If True, only collect 3 sample stocks.
    """
    start = datetime.now()
    log.info("Pipeline started at %s", start.strftime("%Y-%m-%d %H:%M:%S"))

    # ── Step 1: Collect ──
    if not skip_collect:
        if test_mode:
            log.info("Running collector in TEST mode (3 stocks)...")
            test_crawling()
        else:
            log.info("Running full collector...")
            collector_run()
    else:
        log.info("Skipping collection (--skip-collect)")

    # ── Step 2: Screen & Analyse ──
    log.info("Running screener...")
    master = load_csv("master")
    daily = load_csv("daily")
    fs = load_csv("financial_statements")
    ind = load_csv("indicators")
    shares = load_csv("shares")

    if daily.empty:
        log.error("daily CSV not found – cannot run screener")
        return

    ind = preprocess_indicators(ind)
    multiplier = detect_unit_multiplier(ind)
    anal_df = analyze_all(fs, ind)
    full_df = calc_valuation(daily, anal_df, multiplier, shares)

    # Merge market/sector info from master
    if not master.empty and "시장구분" in master.columns:
        master_info = master[["종목코드", "시장구분", "종목구분"]].drop_duplicates("종목코드")
        full_df = full_df.merge(master_info, on="종목코드", how="left")

    # ── Save dashboard CSV (for fast webapp loading) ──
    dashboard_csv = DATA_DIR / "dashboard_result.csv"
    full_df.to_csv(dashboard_csv, index=False, encoding="utf-8-sig")
    log.info("Dashboard CSV saved: %s (%d rows)", dashboard_csv.name, len(full_df))

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

    elapsed = datetime.now() - start
    log.info(
        "Pipeline finished in %s — %d total, %d screened, %d momentum, "
        "%d GARP, %d cashcow, %d turnaround",
        elapsed, len(full_df), len(screened), len(momentum_df),
        len(garp_df), len(cashcow_df), len(turnaround_df),
    )
