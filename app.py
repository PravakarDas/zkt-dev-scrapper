from flask import (
    Flask,
    render_template,
    request,
    Response
)

from web_database import (
    get_attendance_records,
    count_attendance_records,
    get_record,
    get_filter_options,
    export_csv
)


app = Flask(__name__)


# ============================================================
# SETTINGS
# ============================================================

PER_PAGE = 50


# ============================================================
# HOME / ATTENDANCE
# ============================================================

@app.route("/")
def index():

    try:

        page = request.args.get(
            "page",
            1,
            type=int
        )

        if page < 1:
            page = 1

        records = get_attendance_records(
            request.args,
            page=page,
            per_page=PER_PAGE
        )

        total_records = count_attendance_records(
            request.args
        )

        total_pages = (
            (total_records + PER_PAGE - 1)
            // PER_PAGE
        )

        options = get_filter_options()

        return render_template(
            "index.html",

            records=records,

            total_records=total_records,

            page=page,

            total_pages=total_pages,

            options=options,

            filters=request.args
        )

    except Exception as error:

        return render_template(
            "error.html",
            error=str(error)
        ), 500


# ============================================================
# RECORD DETAILS
# ============================================================

@app.route("/record/<int:record_id>")
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
# CSV DOWNLOAD
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
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok"
    }


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("ZKTeco Attendance Dashboard")
    print("=" * 60)
    print()
    print("Open:")
    print("http://127.0.0.1:5000")
    print()
    print("For VPS/public access use:")
    print("http://YOUR_SERVER_IP:5000")
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )