"""
Versioned JSON REST API, meant to be queried directly (e.g. from
Postman) as well as by the dashboard's own frontend JavaScript.

Every route under /api/v1 requires the X-API-Key header, except
/api/v1/health and /api/v1/openapi.json.

Device management (add/activate/deactivate) is intentionally NOT
exposed here - those actions are only available through the web
app's own forms (app.py). This blueprint only lists devices
read-only; it never writes to zkt_devices.
"""

from flask import Blueprint, request, jsonify, Response

from config import API_KEY

from web_database import (
    get_attendance_api_data,
    get_record,
    serialize_record,
    get_filter_options,
    get_stats,
    export_csv,
    list_devices,
)

from openapi_spec import build_spec

from rate_limiter import limiter


api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

PER_PAGE_DEFAULT = 50

OPEN_ENDPOINTS = {"api_v1.health", "api_v1.openapi_json"}


# ============================================================
# AUTH
# ============================================================

@api_bp.before_request
def require_api_key():

    if request.endpoint in OPEN_ENDPOINTS:
        return None

    if not API_KEY:

        return jsonify({
            "error": "server_misconfigured",
            "message": "API_KEY is not set in the server's .env file.",
        }), 500

    provided = request.headers.get("X-API-Key") or request.args.get("api_key")

    if not provided or provided != API_KEY:

        return jsonify({
            "error": "unauthorized",
            "message": "Missing or invalid API key. Send it as the "
                        "'X-API-Key' header.",
        }), 401

    return None


# ============================================================
# META
# ============================================================

@api_bp.route("/health")
@limiter.exempt
def health():

    return jsonify({"status": "ok"})


@api_bp.route("/openapi.json")
@limiter.exempt
def openapi_json():

    server_url = request.url_root.rstrip("/")

    return jsonify(build_spec(server_url))


# ============================================================
# ATTENDANCE
# ============================================================

@api_bp.route("/attendance")
def attendance_list():

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", PER_PAGE_DEFAULT, type=int)

    page = max(page, 1)

    data = get_attendance_api_data(
        request.args,
        page=page,
        per_page=per_page,
    )

    return jsonify(data)


@api_bp.route("/attendance/filters")
def attendance_filters():

    return jsonify(get_filter_options())


@api_bp.route("/attendance/export.csv")
@limiter.limit("10 per minute")
def attendance_export_csv():

    csv_data = export_csv(request.args)

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=zkteco_attendance.csv",
        },
    )


@api_bp.route("/attendance/<int:record_id>")
def attendance_detail(record_id):

    record = get_record(record_id)

    if not record:

        return jsonify({
            "error": "not_found",
            "message": f"No attendance record with id {record_id}.",
        }), 404

    return jsonify(serialize_record(record))


# ============================================================
# STATS
# ============================================================

@api_bp.route("/stats")
def stats():

    return jsonify(get_stats())


# ============================================================
# DEVICES (read-only - management stays in the web app only)
# ============================================================

@api_bp.route("/devices", methods=["GET"])
def devices_list():

    return jsonify([dict(d) for d in list_devices()])
