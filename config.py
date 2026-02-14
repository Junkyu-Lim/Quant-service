import os
from pathlib import Path

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Batch schedule (cron-style)
BATCH_HOUR = int(os.environ.get("BATCH_HOUR", "18"))   # 18시 KST (장 마감 후)
BATCH_MINUTE = int(os.environ.get("BATCH_MINUTE", "0"))

# Web server
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
