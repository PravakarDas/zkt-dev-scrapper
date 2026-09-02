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
        "status": {"type": "integer", "nullable": True},
        "punch": {"type": "integer", "example": 0},
        "punch_type": {"type": "string", "example": "Check In"},
        "record_hash": {"type": "string"},
        "created_at": {"type": "string"},
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
        "name": "employee_id",
        "in": "query",
        "schema": {"type": "string"},
        "description": "Exact match on user_id.",
    },
    {
        "name": "branch",
        "in": "query",
        "schema": {"type": "string"},
        "description": "Exact match on branch_name.",
    },
    {
        "name": "device_ip",
        "in": "query",
        "schema": {"type": "string"},
    },
    {
        "name": "device_serial",
        "in": "query",
        "schema": {"type": "string"},
    },
    {
        "name": "punch_type",
        "in": "query",
        "schema": {
            "type": "string",
            "enum": [
                "Check In", "Check Out", "Break Out",
                "Break In", "Overtime In", "Overtime Out",
            ],
        },
    },
    {
        "name": "status",
        "in": "query",
        "schema": {"type": "integer"},
    },
    {
        "name": "search",
        "in": "query",
        "schema": {"type": "string"},
        "description": "Case-insensitive match against employee name or employee ID.",
    },
    {
        "name": "from_date",
        "in": "query",
        "schema": {"type": "string", "format": "date"},
        "description": "Inclusive lower bound, e.g. 2026-01-01.",
    },
    {
        "name": "to_date",
        "in": "query",
        "schema": {"type": "string", "format": "date"},
        "description": "Inclusive upper bound, e.g. 2026-01-31.",
    },
    {
        "name": "sort_by",
        "in": "query",
        "schema": {
            "type": "string",
            "enum": ["attendance_time", "id", "user_id", "branch_name"],
            "default": "attendance_time",
        },
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
                "the X-API-Key header.\n\n"
                "This API only *reads* from / manages device rows in the "
                "database - it never talks to the physical devices "
                "directly. Device sync happens continuously via a "
                "separate background collector."
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
                    "description": "Paginated, filterable, sortable list of attendance punches.",
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
                    "description": "Distinct branches, device IPs/serials, punch types, and statuses currently in the data. Cached briefly server-side.",
                    "tags": ["Attendance"],
                    "responses": {"200": {"description": "Filter option lists."}},
                },
            },
            "/api/v1/stats": {
                "get": {
                    "summary": "Summary statistics",
                    "description": "Total records, records today, unique employees, device counts. Cached briefly server-side.",
                    "tags": ["Attendance"],
                    "responses": {"200": {"description": "Stats object."}},
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
