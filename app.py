from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)

from config import API_KEY

from web_database import (
    get_record,
    list_devices,
)

from database import (
    get_device,
    get_device_by_ip,
    add_device,
    deactivate_device,
    activate_device,
)

from device_manager import test_device

from api import api_bp


app = Flask(__name__)

app.secret_key = "zkteco-local-secret-key"

app.register_blueprint(api_bp)


@app.context_processor
def inject_globals():

    return {
        # The dashboard's own JS needs to call /api/v1/* like any
        # other client, so the key is exposed to pages it renders.
        # This does not widen access versus the old no-auth app -
        # it only gates the raw API from people who don't have the
        # dashboard open.
        "api_key": API_KEY or "",
    }


# ============================================================
# ATTENDANCE PAGE
#
# No data is queried here - the browser calls /api/v1/attendance
# via JavaScript once the page has loaded (see static/app.js).
# ============================================================

@app.route("/")
def index():

    try:
        return render_template("index.html")

    except Exception as error:

        return render_template("error.html", error=str(error)), 500


# ============================================================
# RECORD DETAILS
# ============================================================

@app.route("/record/<int:record_id>")
def record_details(record_id):

    try:

        record = get_record(record_id)

        if not record:
            return render_template(
                "error.html",
                error=f"Record #{record_id} was not found.",
            ), 404

        return render_template("record.html", record=record)

    except Exception as error:

        return render_template("error.html", error=str(error)), 500


# ============================================================
# API DOCS (Swagger UI)
# ============================================================

@app.route("/api/docs")
def api_docs():

    return render_template("api_docs.html")


# ============================================================
# DEVICES
# ============================================================

@app.route("/devices")
def devices():

    try:
        return render_template("devices.html", devices=list_devices())

    except Exception as error:

        return render_template("error.html", error=str(error)), 500


@app.route("/devices/add", methods=["GET", "POST"])
def add_device_page():

    if request.method == "GET":
        return render_template("add_device.html")

    branch_name = request.form.get("branch_name", "").strip()
    ip_address = request.form.get("ip_address", "").strip()
    port_value = request.form.get("port", "4370").strip()

    if not branch_name:
        flash("Branch name is required.", "error")
        return redirect(url_for("add_device_page"))

    if not ip_address:
        flash("IP address is required.", "error")
        return redirect(url_for("add_device_page"))

    try:
        port = int(port_value)
    except ValueError:
        flash("Port must be a number.", "error")
        return redirect(url_for("add_device_page"))

    existing = get_device_by_ip(ip_address, port)

    if existing:
        flash("This IP and port already exists.", "error")
        return redirect(url_for("devices"))

    result = test_device(ip_address, port)

    if not result["success"]:
        flash("Could not connect to device: " + result["error"], "error")
        return redirect(url_for("add_device_page"))

    serial = result.get("serial")

    if not serial:
        flash(
            "Device connected, but serial number could not be read.",
            "error",
        )
        return redirect(url_for("add_device_page"))

    device_id = serial.strip()

    try:

        add_device(
            device_id=device_id,
            branch_name=branch_name,
            ip_address=ip_address,
            port=port,
            device_name=result.get("device_name"),
            serial_number=serial,
            firmware=result.get("firmware"),
            platform=result.get("platform"),
        )

    except Exception as error:

        flash("Database error: " + str(error), "error")
        return redirect(url_for("add_device_page"))

    flash("Device connected and added successfully.", "success")

    return redirect(url_for("devices"))


@app.route("/devices/<device_id>/remove", methods=["POST"])
def remove_device(device_id):

    try:

        device = get_device(device_id)

        if not device:
            flash("Device not found.", "error")
            return redirect(url_for("devices"))

        deactivate_device(device_id)

        flash(
            f"Device {device_id} was removed from active collection.",
            "success",
        )

    except Exception as error:

        flash("Error: " + str(error), "error")

    return redirect(url_for("devices"))


@app.route("/devices/<device_id>/activate", methods=["POST"])
def activate_device_page(device_id):

    try:

        activate_device(device_id)
        flash("Device activated.", "success")

    except Exception as error:

        flash("Error: " + str(error), "error")

    return redirect(url_for("devices"))


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("ZKTeco Attendance Dashboard")
    print("=" * 60)
    print()
    print("Dashboard : http://127.0.0.1:5000")
    print("Devices   : http://127.0.0.1:5000/devices")
    print("API       : http://127.0.0.1:5000/api/v1/attendance")
    print("API docs  : http://127.0.0.1:5000/api/docs")
    print()

    if not API_KEY:
        print("WARNING: API_KEY is not set in .env - all /api/v1 "
              "requests will fail with 500 until it is set.")
        print()

    app.run(host="0.0.0.0", port=5000, debug=False)
