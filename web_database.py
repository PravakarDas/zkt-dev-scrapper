"""
Read-side data access for the Flask app (app.py) and the REST
API (api.py).

This module owns every query that serves the dashboard / API.
It does NOT touch the device-sync write path — that lives in
database.py and is used unchanged by collector.py.

Performance notes (see CLAUDE.md for the full writeup):
- All queries go through the shared pool in db_pool.py instead of
  opening a new connection each time.
- Record listing does exactly one round trip for the page of rows
  and one for the total count (both share a single pool checkout).
- Filter dropdown values and summary stats are cached in-process
  with a short TTL (config.FILTER_CACHE_SECONDS / STATS_CACHE_SECONDS)
  since they change rarely relative to how often the page is loaded.
"""

import csv
import io
import threading
import time

from db_pool import pool
from config import FILTER_CACHE_SECONDS, STATS_CACHE_SECONDS


ATTENDANCE_TABLE = "zkt_attendance"
DEVICE_TABLE = "zkt_devices"

RECORD_COLUMNS = """
    id,
    device_id,
    branch_name,
    device_ip,
    device_port,
    device_name,
    serial_number,
    firmware,
    platform,
    user_id,
    user_name,
    attendance_time,
    status,
    punch,
    punch_type,
    record_hash,
    created_at
"""

SORT_COLUMNS = {
    "attendance_time": "attendance_time",
    "id": "id",
    "user_id": "user_id",
    "branch_name": "branch_name",
}


# ============================================================
# SMALL TTL CACHE
#
# A single-writer, read-mostly cache. Not distributed / not
# shared across worker processes - fine for this app's traffic.
# ============================================================

class _TTLCache:

    def __init__(self):
        self._lock = threading.Lock()
        self._value = None
        self._expires_at = 0.0

    def get_or_set(self, ttl_seconds, loader):

        now = time.time()

        if self._value is not None and now < self._expires_at:
            return self._value

        with self._lock:

            now = time.time()

            if self._value is not None and now < self._expires_at:
                return self._value

            value = loader()

            self._value = value
            self._expires_at = now + ttl_seconds

            return value


_filter_cache = _TTLCache()
_stats_cache = _TTLCache()


# ============================================================
# FILTER BUILDING
# ============================================================

def build_filters(args):

    conditions = []
    params = []

    record_id = (args.get("record_id") or "").strip()

    if record_id:

        try:
            conditions.append("id = %s")
            params.append(int(record_id))
        except ValueError:
            conditions.append("1 = 0")

    # since_id: "give me everything new since the last record I saw".
    # id is an auto-incrementing primary key assigned at insert time, so
    # this is a safe polling cursor - unlike a timestamp filter it can't
    # miss or double-count rows around clock boundaries.
    since_id = (args.get("since_id") or "").strip()

    if since_id:

        try:
            conditions.append("id > %s")
            params.append(int(since_id))
        except ValueError:
            conditions.append("1 = 0")

    employee_id = (args.get("employee_id") or "").strip()

    if employee_id:
        conditions.append("user_id = %s")
        params.append(employee_id)

    branch = (args.get("branch") or "").strip()

    if branch:
        conditions.append("branch_name = %s")
        params.append(branch)

    device_ip = (args.get("device_ip") or "").strip()

    if device_ip:
        conditions.append("device_ip = %s")
        params.append(device_ip)

    device_serial = (args.get("device_serial") or "").strip()

    if device_serial:
        conditions.append("serial_number = %s")
        params.append(device_serial)

    punch_type = (args.get("punch_type") or "").strip()

    if punch_type:
        conditions.append("punch_type = %s")
        params.append(punch_type)

    status = (args.get("status") or "").strip()

    if status:

        try:
            conditions.append("status = %s")
            params.append(int(status))
        except ValueError:
            conditions.append("1 = 0")

    search = (args.get("search") or "").strip()

    if search:
        conditions.append(
            "(user_name ILIKE %s OR user_id ILIKE %s)"
        )
        like = f"%{search}%"
        params.append(like)
        params.append(like)

    from_date = (args.get("from_date") or "").strip()

    if from_date:
        conditions.append("attendance_time >= %s::date")
        params.append(from_date)

    to_date = (args.get("to_date") or "").strip()

    if to_date:
        conditions.append(
            "attendance_time < (%s::date + INTERVAL '1 day')"
        )
        params.append(to_date)

    where_sql = (
        "WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )

    return where_sql, params


def _resolve_sort(args):

    sort_by = (args.get("sort_by") or "attendance_time").strip()
    sort_dir = (args.get("sort_dir") or "desc").strip().lower()

    column = SORT_COLUMNS.get(sort_by, "attendance_time")
    direction = "ASC" if sort_dir == "asc" else "DESC"

    return f"{column} {direction}, id {direction}"


# ============================================================
# ATTENDANCE: LIST + COUNT (one pool checkout, two queries)
# ============================================================

def get_attendance_page(args, page=1, per_page=50):

    where_sql, params = build_filters(args)
    order_sql = _resolve_sort(args)

    page = max(page, 1)
    per_page = max(1, min(per_page, 500))
    offset = (page - 1) * per_page

    records_query = f"""
        SELECT {RECORD_COLUMNS}
        FROM {ATTENDANCE_TABLE}
        {where_sql}
        ORDER BY {order_sql}
        LIMIT %s
        OFFSET %s
    """

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM {ATTENDANCE_TABLE}
        {where_sql}
    """

    with pool.connection() as conn:

        with conn.cursor() as cur:

            cur.execute(records_query, params + [per_page, offset])
            records = cur.fetchall()

            cur.execute(count_query, params)
            total = cur.fetchone()["total"]

    return records, total


def get_record(record_id):

    query = f"""
        SELECT {RECORD_COLUMNS}
        FROM {ATTENDANCE_TABLE}
        WHERE id = %s
        LIMIT 1
    """

    with pool.connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query, (record_id,))
            return cur.fetchone()


# ============================================================
# FILTER OPTIONS (cached, single round trip on cache miss)
# ============================================================

def _load_filter_options():

    query = f"""
        SELECT 'branch' AS field, branch_name AS value
        FROM {ATTENDANCE_TABLE}
        WHERE branch_name IS NOT NULL
        GROUP BY branch_name

        UNION ALL

        SELECT 'device_ip', device_ip
        FROM {ATTENDANCE_TABLE}
        WHERE device_ip IS NOT NULL
        GROUP BY device_ip

        UNION ALL

        SELECT 'device_serial', serial_number
        FROM {ATTENDANCE_TABLE}
        WHERE serial_number IS NOT NULL
        GROUP BY serial_number

        UNION ALL

        SELECT 'punch_type', punch_type
        FROM {ATTENDANCE_TABLE}
        WHERE punch_type IS NOT NULL
        GROUP BY punch_type

        UNION ALL

        SELECT 'status', status::text
        FROM {ATTENDANCE_TABLE}
        WHERE status IS NOT NULL
        GROUP BY status
    """

    result = {
        "branches": [],
        "device_ips": [],
        "device_serials": [],
        "punch_types": [],
        "statuses": [],
    }

    field_to_key = {
        "branch": "branches",
        "device_ip": "device_ips",
        "device_serial": "device_serials",
        "punch_type": "punch_types",
        "status": "statuses",
    }

    with pool.connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query)

            for row in cur.fetchall():

                key = field_to_key[row["field"]]
                result[key].append(row["value"])

    for key in result:
        result[key].sort()

    # Back-compat alias used by older templates/JS.
    result["devices"] = result["device_ips"]

    return result


def get_filter_options():

    return _filter_cache.get_or_set(
        FILTER_CACHE_SECONDS,
        _load_filter_options,
    )


# ============================================================
# SUMMARY STATS (cached)
# ============================================================

def _load_stats():

    query = f"""
        SELECT
            COUNT(*) AS total_records,
            COALESCE(MAX(id), 0) AS latest_id,
            COUNT(*) FILTER (
                WHERE attendance_time >= CURRENT_DATE
            ) AS records_today,
            COUNT(DISTINCT user_id) AS unique_employees,
            COUNT(DISTINCT branch_name) AS branch_count,
            MAX(attendance_time) AS latest_record_time
        FROM {ATTENDANCE_TABLE}
    """

    device_query = f"""
        SELECT
            COUNT(*) AS total_devices,
            COUNT(*) FILTER (WHERE status = 'active') AS active_devices
        FROM {DEVICE_TABLE}
    """

    with pool.connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query)
            stats = dict(cur.fetchone())

            cur.execute(device_query)
            stats.update(cur.fetchone())

    return stats


def get_stats():

    return _stats_cache.get_or_set(
        STATS_CACHE_SECONDS,
        _load_stats,
    )


# ============================================================
# DEVICES (read-only, pooled)
#
# Device WRITES (add/activate/deactivate) still go through
# database.py unchanged - those are rare admin actions and
# already touch the same table the collector polls, so they
# are intentionally left as-is rather than duplicated here.
# ============================================================

def list_devices():

    query = """
        SELECT
            id,
            device_id,
            branch_name,
            ip_address,
            port,
            device_name,
            serial_number,
            firmware,
            platform,
            status,
            first_seen,
            last_seen,
            created_at,
            updated_at
        FROM zkt_devices
        ORDER BY id ASC
    """

    with pool.connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query)
            return cur.fetchall()


# ============================================================
# JSON SERIALIZATION HELPER
# ============================================================

def serialize_record(record):

    result = {}

    for key, value in record.items():

        if value is None:
            result[key] = None
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat(
                sep=" ",
                timespec="seconds",
            )
        else:
            result[key] = value

    return result


# ============================================================
# API PAGE PAYLOAD
# ============================================================

def get_attendance_api_data(args, page=1, per_page=50):

    records, total_records = get_attendance_page(
        args,
        page=page,
        per_page=per_page,
    )

    total_pages = (
        (total_records + per_page - 1) // per_page
        if total_records
        else 0
    )

    return {
        "count": total_records,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "next": page + 1 if page < total_pages else None,
        "previous": page - 1 if page > 1 else None,
        "data": [serialize_record(r) for r in records],
    }


# ============================================================
# EXPORT CSV
# ============================================================

CSV_HEADERS = [
    "ID", "Device ID", "Branch Name", "Device IP", "Device Port",
    "Device Name", "Serial Number", "Firmware", "Platform",
    "Employee ID", "Employee Name", "Attendance Time", "Status",
    "Punch", "Punch Type", "Record Hash", "Created At",
]

CSV_FIELDS = [
    "id", "device_id", "branch_name", "device_ip", "device_port",
    "device_name", "serial_number", "firmware", "platform",
    "user_id", "user_name", "attendance_time", "status",
    "punch", "punch_type", "record_hash", "created_at",
]


def export_csv(args):

    where_sql, params = build_filters(args)
    order_sql = _resolve_sort(args)

    query = f"""
        SELECT {RECORD_COLUMNS}
        FROM {ATTENDANCE_TABLE}
        {where_sql}
        ORDER BY {order_sql}
    """

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADERS)

    with pool.connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query, params)

            for row in cur:
                writer.writerow([row[field] for field in CSV_FIELDS])

    return output.getvalue()
