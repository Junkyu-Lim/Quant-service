import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'quant.db')}"
)

# Batch schedule (cron-style)
BATCH_HOUR = int(os.environ.get("BATCH_HOUR", "18"))  # 6 PM KST after market close
BATCH_MINUTE = int(os.environ.get("BATCH_MINUTE", "0"))

# Web server
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Scraper
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "0.2"))  # seconds between requests
