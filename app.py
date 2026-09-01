from flask import (
    Flask,
    render_template,
    request,
    Response,
    redirect,
    url_for,
    flash,
    jsonify
)

from web_database import (
    get_attendance_records,
    count_attendance_records,
    get_record,
    get_filter_options,
    export_csv,
    get_attendance_api_data
)

from database import (
    get_all_devices,
    get_device,
    add_device,
    deactivate_device,
    activate_device
)

from device_manager import test_device


app = Flask(__name__)

app.secret_key = "zkteco-local-secret-key"


# ============================================================
# SETTINGS
# ============================================================

PER_PAGE = 50


# ============================================================
# PAGINATION URL HELPER
# ============================================================

@app.context_processor
def utility_processor():

    def pagination_url(page_number):

        args = request.args.to_dict()

        args["page"] = page_number

        return url_for(
            "index",
            **args
        )

    return {
        "pagination_url": pagination_url
    }


# ============================================================
# ATTENDANCE PAGE
# ============================================================

@app.route("/")
def index():

    try:

        # IMPORTANT:
        #
        # Do NOT load attendance records here.
        #
        # The browser will call /api/attendance
        # using JavaScript.

        return render_template(
            "index.html"
        )

    except Exception as error:

        return render_template(
            "error.html",
            error=str(error)
        ), 500


# ============================================================
# ATTENDANCE API
# ============================================================

@app.route("/api/attendance")
def attendance_api():

    try:

        page = request.args.get(
            "page",
            1,
            type=int
        )

        if page < 1:

            page = 1

        data = get_attendance_api_data(
            request.args,
            page=page,
            per_page=PER_PAGE
        )

        return jsonify(
            data
        )

    except Exception as error:

        return jsonify({

            "count": 0,

            "page": 1,

            "per_page": PER_PAGE,

            "total_pages": 0,

            "next": None,

            "previous": None,

            "data": [],

            "error": str(error)

        }), 500


# ============================================================
# RECORD DETAILS
# ============================================================

@app.route(
    "/record/<int:record_id>"
)
def record_details(record_id):

    try:

        record = get_record(
            record_id
        )

        if not record:

            return (
                "Record not found",
                404
            )

        return render_template(
            "record.html",
            record=record
        )

    except Exception as error:

        return render_template(
            "error.html",
            error=str(error)
        ), 500


# ============================================================
# CSV
# ============================================================

@app.route("/download.csv")
def download_csv():

    try:

        csv_data = export_csv(
            request.args
        )

        return Response(

            csv_data,

            mimetype="text/csv",

            headers={

                "Content-Disposition":
                    "attachment; "
                    "filename=zkteco_attendance.csv"

            }

        )

    except Exception as error:

        return render_template(
            "error.html",
            error=str(error)
        ), 500


# ============================================================
# DEVICES
# ============================================================

@app.route("/devices")
def devices():

    try:

        devices = get_all_devices()

        return render_template(
            "devices.html",
            devices=devices
        )

    except Exception as error:

        return render_template(
            "error.html",
            error=str(error)
        ), 500


# ============================================================
# ADD DEVICE
# ============================================================

@app.route(
    "/devices/add",
    methods=["GET", "POST"]
)
def add_device_page():

    if request.method == "GET":

        return render_template(
            "add_device.html"
        )

    branch_name = request.form.get(
        "branch_name",
        ""
    ).strip()

    ip_address = request.form.get(
        "ip_address",
        ""
    ).strip()

    port_value = request.form.get(
        "port",
        "4370"
    ).strip()

    if not branch_name:

        flash(
            "Branch name is required.",
            "error"
        )

        return redirect(
            url_for("add_device_page")
        )

    if not ip_address:

        flash(
            "IP address is required.",
            "error"
        )

        return redirect(
            url_for("add_device_page")
        )

    try:

        port = int(
            port_value
        )

    except ValueError:

        flash(
            "Port must be a number.",
            "error"
        )

        return redirect(
            url_for("add_device_page")
        )

    # --------------------------------------------------------
    # Check existing device
    # --------------------------------------------------------

    from database import get_device_by_ip

    existing = get_device_by_ip(
        ip_address,
        port
    )

    if existing:

        flash(
            "This IP and port already exists.",
            "error"
        )

        return redirect(
            url_for("devices")
        )

    # --------------------------------------------------------
    # Test device
    # --------------------------------------------------------

    result = test_device(
        ip_address,
        port
    )

    if not result["success"]:

        flash(
            "Could not connect to device: "
            + result["error"],
            "error"
        )

        return redirect(
            url_for("add_device_page")
        )

    serial = result.get(
        "serial"
    )

    if not serial:

        flash(
            "Device connected, but serial number could not be read.",
            "error"
        )

        return redirect(
            url_for("add_device_page")
        )

    # --------------------------------------------------------
    # Stable device ID
    # --------------------------------------------------------

    device_id = serial.strip()

    # --------------------------------------------------------
    # Save device
    # --------------------------------------------------------

    try:

        add_device(

            device_id=device_id,

            branch_name=branch_name,

            ip_address=ip_address,

            port=port,

            device_name=result.get(
                "device_name"
            ),

            serial_number=serial,

            firmware=result.get(
                "firmware"
            ),

            platform=result.get(
                "platform"
            )

        )

    except Exception as error:

        flash(
            "Database error: "
            + str(error),
            "error"
        )

        return redirect(
            url_for("add_device_page")
        )

    flash(
        "Device connected and added successfully.",
        "success"
    )

    return redirect(
        url_for("devices")
    )


# ============================================================
# REMOVE / DEACTIVATE DEVICE
# ============================================================

@app.route(
    "/devices/<device_id>/remove",
    methods=["POST"]
)
def remove_device(device_id):

    try:

        device = get_device(
            device_id
        )

        if not device:

            flash(
                "Device not found.",
                "error"
            )

            return redirect(
                url_for("devices")
            )

        deactivate_device(
            device_id
        )

        flash(
            f"Device {device_id} was removed from active collection.",
            "success"
        )

    except Exception as error:

        flash(
            "Error: " + str(error),
            "error"
        )

    return redirect(
        url_for("devices")
    )


# ============================================================
# ACTIVATE DEVICE
# ============================================================

@app.route(
    "/devices/<device_id>/activate",
    methods=["POST"]
)
def activate_device_page(device_id):

    try:

        activate_device(
            device_id
        )

        flash(
            "Device activated.",
            "success"
        )

    except Exception as error:

        flash(
            "Error: " + str(error),
            "error"
        )

    return redirect(
        url_for("devices")
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "status": "ok"

    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    print()

    print(
        "=" * 60
    )

    print(
        "ZKTeco Attendance Dashboard"
    )

    print(
        "=" * 60
    )

    print()

    print(
        "Open: http://127.0.0.1:5000"
    )

    print(
        "Devices: http://127.0.0.1:5000/devices"
    )

    print(
        "API: http://127.0.0.1:5000/api/attendance"
    )

    print()

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=False

    )