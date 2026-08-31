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