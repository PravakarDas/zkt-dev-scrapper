"""
Hand-written OpenAPI 3.0 spec for the /api/v1 endpoints.

Served as JSON at /api/v1/openapi.json. Import that URL directly
into Postman (File > Import > Link) to get every endpoint, its
parameters, and the API key auth already wired up as a collection.
Also rendered as a browsable page at /api/docs via Swagger UI.
"""


ATTENDANCE_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 4821},
        "device_id": {"type": "string", "example": "CIY0K0500123"},
        "branch_name": {"type": "string", "example": "CTG Office"},
        "device_ip": {"type": "string", "example": "119.10.168.198"},
        "device_port": {"type": "integer", "example": 1111},
        "device_name": {"type": "string", "nullable": True},
        "serial_number": {"type": "string", "nullable": True},
        "firmware": {"type": "string", "nullable": True},
        "platform": {"type": "string", "nullable": True},
        "user_id": {"type": "string", "example": "23"},
        "user_name": {"type": "string", "nullable": True, "example": "John Doe"},
        "attendance_time": {
            "type": "string",
            "example": "2026-09-02 09:14:03",
        },
        "status": {
            "type": "integer",
            "nullable": True,
            "description": (
                "Raw verification-method code reported by the terminal "
                "(e.g. fingerprint vs. password vs. card), NOT the "
                "check-in/out state - use punch_type for that. Observed "
                "values in this dataset are 1, 3 and 4; the exact "
                "code-to-method mapping is device/firmware-specific and "
                "not documented by ZKTeco in a way this project encodes, "
                "so treat it as an opaque device code unless you've "
                "confirmed the mapping yourself."
            ),
        },
        "punch": {
            "type": "integer",
            "example": 0,
            "description": (
                "Raw punch code from the device. 0=Check In, 1=Check Out, "
                "2=Break Out, 3=Break In, 4=Overtime In, 5=Overtime Out. "
                "Any other code (255 shows up in real data) is not in "
                "this mapping and comes back as punch_type='Unknown' - "
                "filter on the raw punch integer if you need those rows."
            ),
        },
        "punch_type": {
            "type": "string",
            "example": "Check In",
            "description": "Human-readable label derived from `punch`. See the `punch` field for the code mapping.",
        },
        "record_hash": {"type": "string"},
        "created_at": {
            "type": "string",
            "description": "When this row was inserted into the database - not the same as attendance_time (the actual punch time). Useful for auditing, but use `since_id` (see /attendance) rather than this for polling.",
        },
    },
}

DEVICE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "device_id": {"type": "string"},
        "branch_name": {"type": "string"},
        "ip_address": {"type": "string"},
        "port": {"type": "integer"},
        "device_name": {"type": "string", "nullable": True},
        "serial_number": {"type": "string", "nullable": True},
        "firmware": {"type": "string", "nullable": True},
        "platform": {"type": "string", "nullable": True},
        "status": {"type": "string", "enum": ["active", "inactive"]},
        "first_seen": {"type": "string", "nullable": True},
        "last_seen": {"type": "string", "nullable": True},
    },
}

FILTER_PARAMS = [
    {
        "name": "since_id",
        "in": "query",
        "schema": {"type": "integer", "example": 46000},
        "description": (
            "**Use this to check for new data.** Returns only records with "
            "`id` greater than the value given - i.e. everything inserted "
            "since you last checked. `id` is an auto-incrementing primary "
            "key assigned at insert time, so this is a safe polling cursor "
            "even if punch times are backdated or a device's clock drifts "
            "(a timestamp filter would not be safe for that). "
            "\n\n**Recommended polling loop:**\n"
            "1. Call `GET /api/v1/stats` once and remember `latest_id`.\n"
            "2. Periodically call `GET /api/v1/attendance?since_id="
            "{last_seen_id}&sort_by=id&sort_dir=asc&per_page=200`.\n"
            "3. Process the rows you get back, then set `last_seen_id` to "
            "the highest `id` in that page (or keep `last_seen_id` "
            "unchanged if `data` was empty - there's nothing new yet).\n"
            "4. Repeat. If `next` is not null, immediately fetch that next "
            "page too before waiting for the next poll interval - a big "
            "backfill can span more than one page."
        ),
    },
    {
        "name": "employee_id",
        "in": "query",
        "schema": {"type": "string", "example": "23"},
        "description": "Exact match on the device's user_id (the raw employee ID assigned on the ZKTeco terminal, not this API's `id`).",
    },
    {
        "name": "branch",
        "in": "query",
        "schema": {"type": "string", "example": "CTG Office"},
        "description": "Exact match on branch_name. See GET /api/v1/attendance/filters for the current list of values.",
    },
    {
        "name": "device_ip",
        "in": "query",
        "schema": {"type": "string", "example": "119.10.168.198"},
        "description": "Exact match on the device's IP address.",
    },
    {
        "name": "device_serial",
        "in": "query",
        "schema": {"type": "string"},
        "description": "Exact match on the device's serial number.",
    },
    {
        "name": "punch_type",
        "in": "query",
        "schema": {
            "type": "string",
            "enum": [
                "Check In", "Check Out", "Break Out",
                "Break In", "Overtime In", "Overtime Out", "Unknown",
            ],
        },
        "description": "Exact match on the human-readable punch label. Pass 'Unknown' to find rows whose raw `punch` code isn't in the known mapping (this does happen in real device data).",
    },
    {
        "name": "status",
        "in": "query",
        "schema": {"type": "integer", "example": 1},
        "description": "Exact match on the raw device verification-method code (see the `status` field description on AttendanceRecord). This is NOT check-in/out state - use punch_type for that.",
    },
    {
        "name": "search",
        "in": "query",
        "schema": {"type": "string", "example": "john"},
        "description": "Case-insensitive partial match against employee name OR employee ID (user_id). Good for a free-text search box.",
    },
    {
        "name": "from_date",
        "in": "query",
        "schema": {"type": "string", "format": "date", "example": "2026-08-01"},
        "description": "Inclusive lower bound on attendance_time (the actual punch time, not when the row was saved). Format: YYYY-MM-DD.",
    },
    {
        "name": "to_date",
        "in": "query",
        "schema": {"type": "string", "format": "date", "example": "2026-08-31"},
        "description": "Inclusive upper bound on attendance_time. Format: YYYY-MM-DD. Combine with from_date for a range, e.g. from_date=2026-08-01&to_date=2026-08-31 for the whole month of August.",
    },
    {
        "name": "sort_by",
        "in": "query",
        "schema": {
            "type": "string",
            "enum": ["attendance_time", "id", "user_id", "branch_name"],
            "default": "attendance_time",
        },
        "description": "Use 'id' with sort_dir=asc when polling with since_id, so you process new rows in the order they were inserted.",
    },
    {
        "name": "sort_dir",
        "in": "query",
        "schema": {
            "type": "string",
            "enum": ["asc", "desc"],
            "default": "desc",
        },
    },
]

PAGINATION_PARAMS = [
    {
        "name": "page",
        "in": "query",
        "schema": {"type": "integer", "default": 1, "minimum": 1},
    },
    {
        "name": "per_page",
        "in": "query",
        "schema": {
            "type": "integer", "default": 50, "minimum": 1, "maximum": 500,
        },
    },
]


def build_spec(server_url):

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "ZKTeco Attendance API",
            "version": "1.0.0",
            "description": (
                "Read-only API over the attendance data collected from "
                "ZKTeco devices, plus device management. All endpoints "
                "under /api/v1 (except /health and /openapi.json) require "
                "the **X-API-Key** header - set it once under this "
                "collection's Authorization tab in Postman (type: API Key, "
                "key: X-API-Key, add to: Header) and every request below "
                "inherits it.\n\n"
                "This API only *reads* from / manages device rows in the "
                "database - it never talks to the physical devices "
                "directly. Device sync happens continuously via a "
                "separate background collector, independent of this API.\n\n"
                "### Common tasks\n\n"
                "**Get one employee's punches in a date range** — "
                "`GET /attendance?employee_id=23&from_date=2026-08-01&"
                "to_date=2026-08-31`\n\n"
                "**Get a specific record by its API id** — "
                "`GET /attendance/4821`\n\n"
                "**Filter by punch type or raw status code** — "
                "`GET /attendance?punch_type=Check In` or "
                "`GET /attendance?status=1` (see the field descriptions "
                "on `punch`/`punch_type`/`status` under AttendanceRecord "
                "below - `status` is a device verification code, not "
                "check-in/out state).\n\n"
                "**Find out what values exist right now** (branches, "
                "device IPs/serials, punch types) — "
                "`GET /attendance/filters`.\n\n"
                "**Check whether any new data has arrived** (for an "
                "integration/polling app) — use the `since_id` parameter "
                "on `GET /attendance`. See its full description under that "
                "parameter below for the exact polling loop. In short: "
                "remember the highest `id` you've seen, then ask for "
                "`since_id=<that id>&sort_by=id&sort_dir=asc` on your next "
                "poll.\n\n"
                "**Export to a spreadsheet** — "
                "`GET /attendance/export.csv` with any of the same filters."
            ),
        },
        "servers": [{"url": server_url}],
        "security": [{"ApiKeyAuth": []}],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                },
            },
            "schemas": {
                "AttendanceRecord": ATTENDANCE_RECORD_SCHEMA,
                "Device": DEVICE_SCHEMA,
            },
        },
        "paths": {
            "/api/v1/health": {
                "get": {
                    "summary": "Health check",
                    "security": [],
                    "tags": ["Meta"],
                    "responses": {
                        "200": {"description": "Service is up."},
                    },
                },
            },
            "/api/v1/attendance": {
                "get": {
                    "summary": "List attendance records",
                    "description": (
                        "Paginated, filterable, sortable list of attendance "
                        "punches. Combine any of the filters below "
                        "(they AND together) - e.g. employee_id + "
                        "from_date + to_date for one employee's month, or "
                        "since_id alone to poll for new data. "
                        "No filters at all returns everything, newest "
                        "first, paginated."
                    ),
                    "tags": ["Attendance"],
                    "parameters": FILTER_PARAMS + PAGINATION_PARAMS,
                    "responses": {
                        "200": {
                            "description": "A page of records.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "count": {"type": "integer"},
                                            "page": {"type": "integer"},
                                            "per_page": {"type": "integer"},
                                            "total_pages": {"type": "integer"},
                                            "next": {"type": "integer", "nullable": True},
                                            "previous": {"type": "integer", "nullable": True},
                                            "data": {
                                                "type": "array",
                                                "items": ATTENDANCE_RECORD_SCHEMA,
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "401": {"description": "Missing or invalid API key."},
                    },
                },
            },
            "/api/v1/attendance/{record_id}": {
                "get": {
                    "summary": "Get one attendance record",
                    "tags": ["Attendance"],
                    "parameters": [
                        {
                            "name": "record_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "The record.",
                            "content": {
                                "application/json": {
                                    "schema": ATTENDANCE_RECORD_SCHEMA,
                                },
                            },
                        },
                        "404": {"description": "Record not found."},
                    },
                },
            },
            "/api/v1/attendance/export.csv": {
                "get": {
                    "summary": "Export filtered attendance records as CSV",
                    "tags": ["Attendance"],
                    "parameters": FILTER_PARAMS,
                    "responses": {
                        "200": {
                            "description": "CSV file.",
                            "content": {"text/csv": {}},
                        },
                    },
                },
            },
            "/api/v1/attendance/filters": {
                "get": {
                    "summary": "Available filter values",
                    "description": (
                        "Distinct branches, device IPs/serials, punch "
                        "types, and status codes currently present in the "
                        "data - use this to populate dropdowns or to see "
                        "exactly what strings/codes are valid to pass to "
                        "the filters on GET /attendance. Cached briefly "
                        "server-side (a couple of minutes)."
                    ),
                    "tags": ["Attendance"],
                    "responses": {
                        "200": {
                            "description": "Filter option lists.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "branches": {"type": "array", "items": {"type": "string"}},
                                            "device_ips": {"type": "array", "items": {"type": "string"}},
                                            "device_serials": {"type": "array", "items": {"type": "string"}},
                                            "punch_types": {"type": "array", "items": {"type": "string"}},
                                            "statuses": {"type": "array", "items": {"type": "integer"}},
                                        },
                                    },
                                    "example": {
                                        "branches": ["CTG Office"],
                                        "device_ips": ["119.10.168.198"],
                                        "device_serials": ["AIOR211760103"],
                                        "punch_types": ["Break In", "Break Out", "Check In", "Check Out", "Overtime In", "Overtime Out", "Unknown"],
                                        "statuses": [1, 3, 4],
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "/api/v1/stats": {
                "get": {
                    "summary": "Summary statistics",
                    "description": (
                        "Total records, `latest_id` (the highest attendance "
                        "record id currently in the database - call this "
                        "once to get a starting cursor, then poll "
                        "`GET /attendance?since_id=...` from there), "
                        "records today, unique employees, and device "
                        "counts. Cached briefly server-side (a few seconds)."
                    ),
                    "tags": ["Attendance"],
                    "responses": {
                        "200": {
                            "description": "Stats object.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "total_records": {"type": "integer"},
                                            "latest_id": {"type": "integer", "description": "Highest attendance record id right now - use as your first since_id cursor."},
                                            "records_today": {"type": "integer"},
                                            "unique_employees": {"type": "integer"},
                                            "branch_count": {"type": "integer"},
                                            "latest_record_time": {"type": "string", "nullable": True},
                                            "total_devices": {"type": "integer"},
                                            "active_devices": {"type": "integer"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "/api/v1/devices": {
                "get": {
                    "summary": "List devices",
                    "tags": ["Devices"],
                    "responses": {
                        "200": {
                            "description": "All devices.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": DEVICE_SCHEMA,
                                    },
                                },
                            },
                        },
                    },
                },
                "post": {
                    "summary": "Add a device",
                    "description": "Connects to the device to read its serial/firmware/platform, then saves it. The background collector will pick it up automatically (polls every 10s).",
                    "tags": ["Devices"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["branch_name", "ip_address"],
                                    "properties": {
                                        "branch_name": {"type": "string", "example": "Dhaka Office"},
                                        "ip_address": {"type": "string", "example": "203.0.113.5"},
                                        "port": {"type": "integer", "default": 4370},
                                    },
                                },
                            },
                        },
                    },
                    "responses": {
                        "201": {"description": "Device added."},
                        "400": {"description": "Validation error or device unreachable."},
                        "409": {"description": "A device with this IP/port already exists."},
                    },
                },
            },
            "/api/v1/devices/{device_id}/activate": {
                "post": {
                    "summary": "Activate a device",
                    "description": "Marks the device active so the collector starts syncing it.",
                    "tags": ["Devices"],
                    "parameters": [
                        {"name": "device_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Device activated."}},
                },
            },
            "/api/v1/devices/{device_id}/deactivate": {
                "post": {
                    "summary": "Deactivate a device",
                    "description": "Marks the device inactive; the collector stops syncing it (existing data is kept).",
                    "tags": ["Devices"],
                    "parameters": [
                        {"name": "device_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Device deactivated."}},
                },
            },
        },
    }
