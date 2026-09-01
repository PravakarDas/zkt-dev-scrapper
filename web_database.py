import csv
import io

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL


TABLE_NAME = "zkt_attendance"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=20,
        row_factory=dict_row
    )


# ============================================================
# BUILD FILTERS
# ============================================================

def build_filters(args):

    conditions = []
    params = []


    # --------------------------------------------------------
    # Record ID
    # --------------------------------------------------------

    record_id = args.get(
        "record_id",
        ""
    ).strip()

    if record_id:

        try:

            conditions.append(
                "id = %s"
            )

            params.append(
                int(record_id)
            )

        except ValueError:

            conditions.append(
                "1 = 0"
            )


    # --------------------------------------------------------
    # Employee ID
    # --------------------------------------------------------

    employee_id = args.get(
        "employee_id",
        ""
    ).strip()

    if employee_id:

        conditions.append(
            "user_id = %s"
        )

        params.append(
            employee_id
        )


    # --------------------------------------------------------
    # Branch
    # --------------------------------------------------------

    branch = args.get(
        "branch",
        ""
    ).strip()

    if branch:

        conditions.append(
            "branch_name = %s"
        )

        params.append(
            branch
        )


    # --------------------------------------------------------
    # Device IP
    # --------------------------------------------------------

    device_ip = args.get(
        "device_ip",
        ""
    ).strip()

    if device_ip:

        conditions.append(
            "device_ip = %s"
        )

        params.append(
            device_ip
        )


    # --------------------------------------------------------
    # Device Serial
    # --------------------------------------------------------

    device_serial = args.get(
        "device_serial",
        ""
    ).strip()

    if device_serial:

        conditions.append(
            "serial_number = %s"
        )

        params.append(
            device_serial
        )


    # --------------------------------------------------------
    # Punch Type
    # --------------------------------------------------------

    punch_type = args.get(
        "punch_type",
        ""
    ).strip()

    if punch_type:

        conditions.append(
            "punch_type = %s"
        )

        params.append(
            punch_type
        )


    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    status = args.get(
        "status",
        ""
    ).strip()

    if status:

        try:

            conditions.append(
                "status = %s"
            )

            params.append(
                int(status)
            )

        except ValueError:

            conditions.append(
                "1 = 0"
            )


    # --------------------------------------------------------
    # From Date
    # --------------------------------------------------------

    from_date = args.get(
        "from_date",
        ""
    ).strip()

    if from_date:

        conditions.append(
            "attendance_time >= %s::date"
        )

        params.append(
            from_date
        )


    # --------------------------------------------------------
    # To Date
    # --------------------------------------------------------

    to_date = args.get(
        "to_date",
        ""
    ).strip()

    if to_date:

        conditions.append(
            "attendance_time < "
            "(%s::date + INTERVAL '1 day')"
        )

        params.append(
            to_date
        )


    # --------------------------------------------------------
    # WHERE
    # --------------------------------------------------------

    if conditions:

        where_sql = (
            "WHERE "
            + " AND ".join(conditions)
        )

    else:

        where_sql = ""


    return where_sql, params


# ============================================================
# GET ATTENDANCE RECORDS
# ============================================================

def get_attendance_records(
    args,
    page=1,
    per_page=50
):

    where_sql, params = build_filters(
        args
    )


    offset = (
        page - 1
    ) * per_page


    query = f"""

        SELECT

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

        FROM {TABLE_NAME}

        {where_sql}

        ORDER BY
            attendance_time DESC,
            id DESC

        LIMIT %s

        OFFSET %s

    """


    query_params = (
        params
        + [
            per_page,
            offset
        ]
    )


    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                query_params
            )

            records = cur.fetchall()


    return records


# ============================================================
# COUNT RECORDS
# ============================================================

def count_attendance_records(args):

    where_sql, params = build_filters(
        args
    )


    query = f"""

        SELECT COUNT(*)

        FROM {TABLE_NAME}

        {where_sql}

    """


    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                params
            )

            result = cur.fetchone()


    return result["count"]


# ============================================================
# GET SINGLE RECORD
# ============================================================

def get_record(record_id):

    query = f"""

        SELECT

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

        FROM {TABLE_NAME}

        WHERE id = %s

        LIMIT 1

    """


    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (record_id,)
            )

            return cur.fetchone()


# ============================================================
# FILTER OPTIONS
# ============================================================

def get_filter_options():

    with get_connection() as conn:

        with conn.cursor() as cur:


            # ------------------------------------------------
            # Branches
            # ------------------------------------------------

            cur.execute(f"""

                SELECT DISTINCT branch_name

                FROM {TABLE_NAME}

                WHERE branch_name IS NOT NULL

                ORDER BY branch_name

            """)


            branches = [

                row["branch_name"]

                for row in cur.fetchall()

            ]


            # ------------------------------------------------
            # Device IPs
            # ------------------------------------------------

            cur.execute(f"""

                SELECT DISTINCT device_ip

                FROM {TABLE_NAME}

                WHERE device_ip IS NOT NULL

                ORDER BY device_ip

            """)


            device_ips = [

                row["device_ip"]

                for row in cur.fetchall()

            ]


            # ------------------------------------------------
            # Device serials
            # ------------------------------------------------

            cur.execute(f"""

                SELECT DISTINCT serial_number

                FROM {TABLE_NAME}

                WHERE serial_number IS NOT NULL

                ORDER BY serial_number

            """)


            device_serials = [

                row["serial_number"]

                for row in cur.fetchall()

            ]


            # ------------------------------------------------
            # Punch types
            # ------------------------------------------------

            cur.execute(f"""

                SELECT DISTINCT punch_type

                FROM {TABLE_NAME}

                WHERE punch_type IS NOT NULL

                ORDER BY punch_type

            """)


            punch_types = [

                row["punch_type"]

                for row in cur.fetchall()

            ]


    return {

        "branches": branches,

        "device_ips": device_ips,

        "device_serials": device_serials,

        "punch_types": punch_types

    }


# ============================================================
# EXPORT CSV
# ============================================================

def export_csv(args):

    where_sql, params = build_filters(
        args
    )


    query = f"""

        SELECT

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

        FROM {TABLE_NAME}

        {where_sql}

        ORDER BY

            attendance_time DESC,

            id DESC

    """


    output = io.StringIO()

    writer = csv.writer(
        output
    )


    headers = [

        "ID",

        "Device ID",

        "Branch Name",

        "Device IP",

        "Device Port",

        "Device Name",

        "Serial Number",

        "Firmware",

        "Platform",

        "Employee ID",

        "Employee Name",

        "Attendance Time",

        "Status",

        "Punch",

        "Punch Type",

        "Record Hash",

        "Created At"

    ]


    writer.writerow(
        headers
    )


    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                params
            )


            for row in cur:

                writer.writerow([

                    row["id"],

                    row["device_id"],

                    row["branch_name"],

                    row["device_ip"],

                    row["device_port"],

                    row["device_name"],

                    row["serial_number"],

                    row["firmware"],

                    row["platform"],

                    row["user_id"],

                    row["user_name"],

                    row["attendance_time"],

                    row["status"],

                    row["punch"],

                    row["punch_type"],

                    row["record_hash"],

                    row["created_at"]

                ])


    return output.getvalue()