"""
Shared, warm PostgreSQL connection pool for the read side
(web_database.py / api.py / app.py) ONLY.

collector.py and database.py do not import this module and are
completely unaffected by it — the write/collection path keeps
opening its own plain psycopg connections exactly as before.

Why this exists
----------------
Opening a brand new connection to the Neon endpoint costs roughly
1.5-2 seconds (TLS handshake + auth) from a typical client. The
previous web_database.py opened a fresh connection for *every*
query, so a single page load (records + count + 5 filter-option
queries) could open 5+ connections back to back and take 8-10+
seconds. Keeping a small pool of already-authenticated connections
open removes that per-query connection cost.
"""

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from config import (
    DATABASE_URL,
    WEB_POOL_MIN_SIZE,
    WEB_POOL_MAX_SIZE,
)


pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=WEB_POOL_MIN_SIZE,
    max_size=WEB_POOL_MAX_SIZE,
    kwargs={"row_factory": dict_row},
    open=True,
)
