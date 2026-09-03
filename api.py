"""
Versioned JSON REST API, meant to be queried directly (e.g. from
Postman) as well as by the dashboard's own frontend JavaScript.

Every route under /api/v1 requires the X-API-Key header, except
/api/v1/health and /api/v1/openapi.json.

Device WRITE actions (add/activate/deactivate) delegate straight
to database.py's existing functions - unchanged from before this
redesign. Only the read path is new here.
"""

from flask import Blueprint, request, jsonify, Response, url_for

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

from database import (
    add_device,
    activate_device,
    deactivate_device,
    get_device_by_ip,
    get_device,
)

from device_manager import test_device

from openapi_spec import build_spec


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
def health():

    return jsonify({"status": "ok"})


@api_bp.route("/openapi.json")
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
# DEVICES
# ============================================================

@api_bp.route("/devices", methods=["GET"])
def devices_list():

    return jsonify([dict(d) for d in list_devices()])


@api_bp.route("/devices", methods=["POST"])
def devices_add():

    payload = request.get_json(silent=True) or {}

    branch_name = str(payload.get("branch_name", "")).strip()
    ip_address = str(payload.get("ip_address", "")).strip()
    port = payload.get("port", 4370)

    if not branch_name:
        return jsonify({"error": "validation_error", "message": "branch_name is required."}), 400

    if not ip_address:
        return jsonify({"error": "validation_error", "message": "ip_address is required."}), 400

    try:
        port = int(port)
    except (TypeError, ValueError):
        return jsonify({"error": "validation_error", "message": "port must be a number."}), 400

    existing = get_device_by_ip(ip_address, port)

    if existing:
        return jsonify({
            "error": "conflict",
            "message": "A device with this IP and port already exists.",
        }), 409

    result = test_device(ip_address, port)

    if not result["success"]:
        return jsonify({
            "error": "device_unreachable",
            "message": result.get("error", "Could not connect to device."),
        }), 400

    serial = result.get("serial")

    if not serial:
        return jsonify({
            "error": "device_unreachable",
            "message": "Device connected, but serial number could not be read.",
        }), 400

    device = add_device(
        device_id=serial.strip(),
        branch_name=branch_name,
        ip_address=ip_address,
        port=port,
        device_name=result.get("device_name"),
        serial_number=serial,
        firmware=result.get("firmware"),
        platform=result.get("platform"),
    )

    return jsonify(dict(device)), 201


@api_bp.route("/devices/<device_id>/activate", methods=["POST"])
def devices_activate(device_id):

    device = get_device(device_id)

    if not device:
        return jsonify({"error": "not_found", "message": "Device not found."}), 404

    updated = activate_device(device_id)

    return jsonify(dict(updated))


@api_bp.route("/devices/<device_id>/deactivate", methods=["POST"])
def devices_deactivate(device_id):

    device = get_device(device_id)

    if not device:
        return jsonify({"error": "not_found", "message": "Device not found."}), 404

    updated = deactivate_device(device_id)

    return jsonify(dict(updated))
