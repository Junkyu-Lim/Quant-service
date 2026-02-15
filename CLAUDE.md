# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Korean stock market (KOSPI/KOSDAQ) quantitative analysis platform. Collects financial data from KRX and FnGuide, applies multi-strategy screening, and serves results via a Flask web dashboard.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run web server + daily scheduler (18:00 KST)
python run.py server

# Run full pipeline (collect all stocks + screen)
python run.py pipeline

# Test pipeline (3 stocks: Samsung, Kakao, SK Hynix)
python run.py pipeline --test

# Screen only (skip collection, use existing DB data)
python run.py pipeline --skip-collect

# Collect data only
python run.py collect [--test]

# Screen only (no collection)
python run.py screen

# Production deployment
gunicorn -w 4 -b 0.0.0.0:5000 webapp.app:app
```

## Architecture

**Data flow:** KRX/FnGuide sources → `quant_collector_enhanced.py` → SQLite DB (`data/quant.db`) → `quant_screener.py` → Excel + `dashboard_result` table → Flask API → Browser dashboard

**Pipeline orchestration:** `pipeline.py` coordinates collection then screening. `run.py` is the CLI entry point. `batch/scheduler.py` runs daily via APScheduler.

### Core Modules

- **`db.py`** — SQLite database helper. Manages `data/quant.db` with tables: `master`, `daily`, `financial_statements`, `indicators`, `shares`, `dashboard_result`. Uses `collected_date` column for date-based versioning (replaces dated CSV filenames). Key functions: `init_db()`, `save_df()`, `load_latest()`, `save_dashboard()`, `load_dashboard()`.

- **`quant_collector_enhanced.py`** — Parallel data collection (ThreadPoolExecutor, MAX_WORKERS=15). Scrapes FnGuide for financial statements, indicators, share counts. Saves to SQLite via `db.save_df()`.

- **`quant_screener.py`** — Screening engine v6. Computes TTM financials, CAGR growth, S-RIM valuation, percentile scoring. Implements 5 strategies: Quality (우량주), Momentum (고성장), GARP (Peter Lynch PEG), Cashcow (Buffett-style FCF), Turnaround (실적반등). Reads from DB via `db.load_latest()`. Produces 6 Excel files.

- **`webapp/app.py`** — Flask REST API with in-memory DB caching (auto-reload on DB file change). Endpoints: `/api/stocks` (paginated, filtered, sorted), `/api/stocks/<code>`, `/api/markets/summary`, `/api/data/status`, `/api/batch/trigger`. Replicates screening filters in `_apply_screen_filter()` to match Excel outputs.

- **`config.py`** — Central config. `DATA_DIR` points to `data/`, `DB_PATH` points to `data/quant.db`. Env vars: `BATCH_HOUR`, `BATCH_MINUTE`, `HOST`, `PORT`, `DEBUG`.

### Frontend

`webapp/templates/dashboard.html` + `webapp/static/js/dashboard.js` — Bootstrap 5.3 single-page app with 6 tabs (one per strategy), market summary cards, sortable table, detail modal, and manual pipeline trigger.

## Key Patterns

- **SQLite storage** — All data stored in `data/quant.db`. `db.load_latest(table)` returns data for the most recent `collected_date`. `db.save_dashboard()` replaces the dashboard_result table each pipeline run.
- **Unit multiplier detection** — Inferred from Samsung (005930) revenue to scale all financial metrics correctly. Critical for accurate PER/PBR/PEG.
- **Stock codes** — Always 6-digit zero-padded strings (`zfill(6)`).
- **Encoding** — Auto-detects cp949/euc-kr/utf-8 for Korean financial data from FnGuide HTML.
- **Screening consistency** — Filter logic exists in both `quant_screener.py` and `webapp/app.py`'s `_apply_screen_filter()`. Changes to screening criteria must be updated in both places.
- **Scoring weights** — Defined in `quant_screener.py`. Each strategy has custom weight vectors for percentile-based composite scoring.
