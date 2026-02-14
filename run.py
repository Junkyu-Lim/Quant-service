#!/usr/bin/env python3
"""
Entry point for the Quant service.

Usage:
    python run.py server          – Start web server with batch scheduler
    python run.py pipeline        – Run the data pipeline once (foreground)
    python run.py pipeline --limit 10  – Process only 10 stocks (for testing)
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_server(args):
    from models import init_db
    from batch.scheduler import start_scheduler
    from webapp.app import app
    import config

    init_db()
    logger.info("Database initialised")

    scheduler = start_scheduler()
    logger.info("Batch scheduler active")

    try:
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
    finally:
        scheduler.shutdown(wait=False)


def cmd_pipeline(args):
    from models import init_db
    from pipeline import run_pipeline

    init_db()
    run_pipeline(limit=args.limit)


def main():
    parser = argparse.ArgumentParser(description="Quant Service – KOSPI/KOSDAQ analysis")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("server", help="Start web server with scheduler")

    p_pipe = sub.add_parser("pipeline", help="Run data pipeline once")
    p_pipe.add_argument("--limit", type=int, default=None, help="Max stocks to process")

    args = parser.parse_args()

    if args.command == "server":
        cmd_server(args)
    elif args.command == "pipeline":
        cmd_pipeline(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
