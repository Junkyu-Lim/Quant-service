import os
from pathlib import Path

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# SQLite database
DB_PATH = DATA_DIR / "quant.db"

# Batch schedule (cron-style)
BATCH_HOUR = int(os.environ.get("BATCH_HOUR", "18"))   # 18시 KST (장 마감 후)
BATCH_MINUTE = int(os.environ.get("BATCH_MINUTE", "0"))

# Web server
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Claude API (for qualitative analysis reports)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANALYSIS_MODEL = os.environ.get("ANALYSIS_MODEL", "claude-sonnet-4-5-20250929")
REPORT_DIR = DATA_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)
