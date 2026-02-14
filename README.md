# Quant-service

Automated financial data pipeline and dashboard for KOSPI/KOSDAQ stocks.

## Features

- **Data scraping** – Fetches stock listings, daily OHLCV prices, and fundamental data (PER, PBR, EPS, BPS, dividend yield) from KRX and Naver Finance
- **Technical analysis** – Computes moving averages (MA5/20/60), RSI(14), daily change %, and derived metrics (ROE)
- **Batch automation** – APScheduler runs the pipeline daily after market close (configurable via `BATCH_HOUR` / `BATCH_MINUTE`)
- **Web dashboard** – Flask-based UI with server-side pagination, column sorting, market/sector/text filtering, and Chart.js price charts
- **REST API** – JSON endpoints for stocks, detail views, market summaries, batch status, and manual pipeline triggers

## Project Structure

```
├── config.py               # Environment-based configuration
├── models.py               # SQLAlchemy models (Stock, DailyPrice, FinancialMetric, BatchLog)
├── pipeline.py             # End-to-end pipeline orchestrator
├── run.py                  # CLI entry point (server / pipeline)
├── requirements.txt
├── scraper/
│   └── krx.py              # KRX listing + Naver Finance scrapers
├── analysis/
│   └── analyzer.py         # Technical & fundamental analysis
├── batch/
│   └── scheduler.py        # APScheduler background scheduler
└── webapp/
    ├── app.py              # Flask app with API routes
    ├── templates/
    │   └── dashboard.html  # Dashboard UI
    └── static/
        ├── css/style.css
        └── js/dashboard.js
```

## Quick Start

```bash
pip install -r requirements.txt

# Run the pipeline once (test with 10 stocks)
python run.py pipeline --limit 10

# Start web server + batch scheduler
python run.py server
```

The dashboard is available at `http://localhost:5000`.

## Configuration

All settings can be overridden via environment variables:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///quant.db` | SQLAlchemy database URI |
| `BATCH_HOUR` | `18` | Scheduled pipeline hour (KST) |
| `BATCH_MINUTE` | `0` | Scheduled pipeline minute |
| `HOST` | `0.0.0.0` | Web server bind address |
| `PORT` | `5000` | Web server port |
| `DEBUG` | `false` | Flask debug mode |
| `REQUEST_TIMEOUT` | `30` | HTTP request timeout (seconds) |
| `REQUEST_DELAY` | `0.2` | Delay between scraper requests (seconds) |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/stocks` | Paginated stock list with metrics (supports `market`, `sector`, `q`, `sort`, `order`, `page`, `size`) |
| GET | `/api/stocks/<code>` | Stock detail with price history |
| GET | `/api/markets/summary` | Aggregate stats per market |
| GET | `/api/batch/status` | Recent batch job logs |
| POST | `/api/batch/trigger` | Manually trigger pipeline |
