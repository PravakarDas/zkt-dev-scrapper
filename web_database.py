import csv
import io

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL


TABLE_NAME = "zkteco_attendance"


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=20,
        row_factory=dict_row
    )


def build_filters(args):
    """
    Build SQL WHERE conditions from request parameters.
    """

    conditions = []
    params = []

    employee_id = args.get("employee_id", "").strip()
    branch = args.get("branch", "").strip()
    device_ip = args.get("device_ip", "").strip()
    device_serial = args.get("device_serial", "").strip()

    punch_type = args.get("punch_type", "").strip()
    status = args.get("status", "").strip()

    from_date = args.get("from_date", "").strip()
    to_date = args.get("to_date", "").strip()

    if employee_id:
        conditions.append("user_id = %s")
        params.append(employee_id)

    if branch:
        conditions.append("branch_name = %s")
        params.append(branch)

    if device_ip:
        conditions.append("device_ip = %s")
        params.append(device_ip)

    if device_serial:
        conditions.append("device_serial = %s")
        params.append(device_serial)

    if punch_type:
        conditions.append("punch_type = %s")
        params.append(punch_type)

    if status:
        conditions.append("status = %s")
        params.append(int(status))

    if from_date:
        conditions.append(
            "attendance_time >= %s::date"
        )
        params.append(from_date)

    if to_date:
        conditions.append(
            "attendance_time < (%s::date + INTERVAL '1 day')"
        )
        params.append(to_date)

    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)
    else:
        where_sql = ""

    return where_sql, params


def get_attendance_records(
    args,
    page=1,
    per_page=50
):

    where_sql, params = build_filters(args)

    offset = (page - 1) * per_page

    query = f"""
        SELECT
            id,
            branch_name,
            device_ip,
            device_port,
            device_serial,
            device_name,
            device_platform,
            device_firmware,
            user_id,
            user_name,
            attendance_time,
            status,
            punch,
            punch_type,
            raw_data,
            created_at

        FROM {TABLE_NAME}

        {where_sql}

        ORDER BY attendance_time DESC, id DESC

        LIMIT %s
        OFFSET %s
    """

    query_params = params + [
        per_page,
        offset
    ]

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                query_params
            )

            records = cur.fetchall()

    return records


def count_attendance_records(args):

    where_sql, params = build_filters(args)

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

            return cur.fetchone()["count"]


def get_record(record_id):

    query = f"""
        SELECT
            id,
            branch_name,
            device_ip,
            device_port,
            device_serial,
            device_name,
            device_platform,
            device_firmware,
            user_id,
            user_name,
            attendance_time,
            status,
            punch,
            punch_type,
            raw_data,
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


def get_filter_options():

    with get_connection() as conn:

        with conn.cursor() as cur:

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

            cur.execute(f"""
                SELECT DISTINCT device_serial
                FROM {TABLE_NAME}
                WHERE device_serial IS NOT NULL
                ORDER BY device_serial
            """)

            device_serials = [
                row["device_serial"]
                for row in cur.fetchall()
            ]

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


def export_csv(args):

    where_sql, params = build_filters(args)

    query = f"""
        SELECT
            id,
            branch_name,
            device_ip,
            device_port,
            device_serial,
            device_name,
            device_platform,
            device_firmware,
            user_id,
            user_name,
            attendance_time,
            status,
            punch,
            punch_type,
            raw_data,
            created_at

        FROM {TABLE_NAME}

        {where_sql}

        ORDER BY attendance_time DESC, id DESC
    """

    output = io.StringIO()

    writer = csv.writer(output)

    headers = [
        "ID",
        "Branch Name",
        "Device IP",
        "Device Port",
        "Device Serial",
        "Device Name",
        "Device Platform",
        "Device Firmware",
        "Employee ID",
        "Employee Name",
        "Attendance Time",
        "Status",
        "Punch",
        "Punch Type",
        "Raw Data",
        "Created At"
    ]

    writer.writerow(headers)

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                params
            )

            for row in cur:

                writer.writerow([
                    row["id"],
                    row["branch_name"],
                    row["device_ip"],
                    row["device_port"],
                    row["device_serial"],
                    row["device_name"],
                    row["device_platform"],
                    row["device_firmware"],
                    row["user_id"],
                    row["user_name"],
                    row["attendance_time"],
                    row["status"],
                    row["punch"],
                    row["punch_type"],
                    row["raw_data"],
                    row["created_at"]
                ])

    return output.getvalue()