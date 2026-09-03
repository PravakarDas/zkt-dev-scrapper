import os
from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from .env")


# ============================================================
# ZKTECO DEVICES
# ============================================================

DEVICES = [
    {
        "ip": "119.10.168.198",
        "port": 1111,
        "branch": "CTG Office",
    },

    # Add more devices here later.
    #
    # {
    #     "ip": "PUBLIC_IP",
    #     "port": 1111,
    #     "branch": "Dhaka Office",
    # },
]


# ============================================================
# SETTINGS
# ============================================================

# When device is offline, retry after this many seconds.
DEVICE_RETRY_SECONDS = 5

# Full synchronization safety interval.
FULL_SYNC_AFTER_MINUTES = 20

# ZKTeco connection timeout.
DEVICE_TIMEOUT = 10

# Number of records sent to PostgreSQL in one batch.
DB_BATCH_SIZE = 2000


# ============================================================
# WEB / API SETTINGS
#
# Used only by app.py / api.py / web_database.py (the read
# side). Not read by collector.py or database.py.
# ============================================================

# API key required on every /api/v1/* request (header: X-API-Key).
API_KEY = os.getenv("API_KEY")

# Connection pool size for the read-side (web_database.py).
# Kept small: Neon's pooler endpoint has a limited number of
# concurrent connections and this is a low-traffic internal tool.
WEB_POOL_MIN_SIZE = int(os.getenv("WEB_POOL_MIN_SIZE", "1"))
WEB_POOL_MAX_SIZE = int(os.getenv("WEB_POOL_MAX_SIZE", "5"))

# How long cached lookups (filter dropdown values, summary stats)
# are considered fresh before being re-queried, in seconds.
FILTER_CACHE_SECONDS = int(os.getenv("FILTER_CACHE_SECONDS", "120"))
STATS_CACHE_SECONDS = int(os.getenv("STATS_CACHE_SECONDS", "20"))