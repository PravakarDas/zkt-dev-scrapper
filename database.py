import hashlib

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL


# ============================================================
# TABLE NAMES
# ============================================================

ATTENDANCE_TABLE = "zkt_attendance"

DEVICE_TABLE = "zkt_devices"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=20
    )


def get_dict_connection():

    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=20,
        row_factory=dict_row
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def create_table():

    with get_connection() as conn:

        with conn.cursor() as cur:

            # ------------------------------------------------
            # ATTENDANCE TABLE
            # ------------------------------------------------

            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {ATTENDANCE_TABLE} (

                    id BIGSERIAL PRIMARY KEY,

                    device_id TEXT NOT NULL,

                    branch_name TEXT NOT NULL,

                    device_ip TEXT NOT NULL,
                    device_port INTEGER,

                    device_name TEXT,

                    serial_number TEXT,

                    firmware TEXT,

                    platform TEXT,

                    user_id TEXT NOT NULL,

                    user_name TEXT,

                    attendance_time TIMESTAMP NOT NULL,

                    status INTEGER,

                    punch INTEGER,

                    punch_type TEXT,

                    record_hash TEXT UNIQUE,

                    created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ------------------------------------------------
            # DEVICE TABLE
            # ------------------------------------------------

            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {DEVICE_TABLE} (

                    id BIGSERIAL PRIMARY KEY,

                    device_id TEXT NOT NULL UNIQUE,

                    branch_name TEXT NOT NULL,

                    ip_address TEXT NOT NULL,

                    port INTEGER NOT NULL,

                    device_name TEXT,

                    serial_number TEXT,

                    firmware TEXT,

                    platform TEXT,

                    status TEXT NOT NULL
                    DEFAULT 'active',

                    first_seen TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                    last_seen TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                    created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                    updated_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ------------------------------------------------
            # ATTENDANCE INDEXES
            # ------------------------------------------------

            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS
                idx_zkt_attendance_device
                ON {ATTENDANCE_TABLE}(device_id)
            """)

            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS
                idx_zkt_attendance_user
                ON {ATTENDANCE_TABLE}(user_id)
            """)

            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS
                idx_zkt_attendance_time
                ON {ATTENDANCE_TABLE}(attendance_time)
            """)

            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS
                idx_zkt_attendance_branch
                ON {ATTENDANCE_TABLE}(branch_name)
            """)

            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS
                idx_zkt_attendance_record_hash
                ON {ATTENDANCE_TABLE}(record_hash)
            """)

            # ------------------------------------------------
            # DEDUPLICATION CONSTRAINT
            #
            # insert_records()'s ON CONFLICT clause requires this
            # exact composite constraint to exist. Postgres has no
            # "ADD CONSTRAINT IF NOT EXISTS", so this uses the
            # standard DO-block workaround: try to add it, and
            # silently do nothing if it's already there (e.g. an
            # existing database that already has it).
            # ------------------------------------------------

            cur.execute(f"""
                DO $$
                BEGIN
                    ALTER TABLE {ATTENDANCE_TABLE}
                        ADD CONSTRAINT
                        zkt_attendance_device_record_unique
                        UNIQUE (
                            device_id,
                            user_id,
                            attendance_time,
                            status,
                            punch
                        );
                EXCEPTION
                    WHEN duplicate_object OR duplicate_table THEN
                        NULL;
                END $$;
            """)

            # ------------------------------------------------
            # DEVICE INDEXES
            # ------------------------------------------------

            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS
                idx_zkt_devices_status
                ON {DEVICE_TABLE}(status)
            """)

            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS
                idx_zkt_devices_ip
                ON {DEVICE_TABLE}(ip_address)
            """)

        conn.commit()

    print("Database initialized successfully.")


# ============================================================
# DEVICE MANAGEMENT
# ============================================================

def get_all_devices():

    query = f"""
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

        FROM {DEVICE_TABLE}

        ORDER BY id ASC
    """

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query)

            return cur.fetchall()


def get_active_devices():

    query = f"""
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

        FROM {DEVICE_TABLE}

        WHERE status = 'active'

        ORDER BY id ASC
    """

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query)

            return cur.fetchall()


def get_device(device_id):

    query = f"""
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

        FROM {DEVICE_TABLE}

        WHERE device_id = %s

        LIMIT 1
    """

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (device_id,)
            )

            return cur.fetchone()


def get_device_by_ip(
    ip_address,
    port
):

    query = f"""
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

        FROM {DEVICE_TABLE}

        WHERE
            ip_address = %s
            AND port = %s

        LIMIT 1
    """

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (
                    ip_address,
                    port
                )
            )

            return cur.fetchone()


def add_device(
    device_id,
    branch_name,
    ip_address,
    port,
    device_name,
    serial_number,
    firmware,
    platform
):

    query = f"""
        INSERT INTO {DEVICE_TABLE} (

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

        )

        VALUES (

            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,

            'active',

            CURRENT_TIMESTAMP,

            CURRENT_TIMESTAMP,

            CURRENT_TIMESTAMP,

            CURRENT_TIMESTAMP

        )

        RETURNING *
    """

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (
                    device_id,
                    branch_name,
                    ip_address,
                    port,
                    device_name,
                    serial_number,
                    firmware,
                    platform
                )
            )

            result = cur.fetchone()

        conn.commit()

    return result


def update_device(
    device_id,
    branch_name,
    ip_address,
    port
):

    query = f"""
        UPDATE {DEVICE_TABLE}

        SET

            branch_name = %s,

            ip_address = %s,

            port = %s,

            updated_at = CURRENT_TIMESTAMP

        WHERE device_id = %s

        RETURNING *
    """

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (
                    branch_name,
                    ip_address,
                    port,
                    device_id
                )
            )

            result = cur.fetchone()

        conn.commit()

    return result


def deactivate_device(device_id):

    query = f"""
        UPDATE {DEVICE_TABLE}

        SET

            status = 'inactive',

            updated_at = CURRENT_TIMESTAMP

        WHERE device_id = %s

        RETURNING *
    """

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (device_id,)
            )

            result = cur.fetchone()

        conn.commit()

    return result


def activate_device(device_id):

    query = f"""
        UPDATE {DEVICE_TABLE}

        SET

            status = 'active',

            updated_at = CURRENT_TIMESTAMP

        WHERE device_id = %s

        RETURNING *
    """

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (device_id,)
            )

            result = cur.fetchone()

        conn.commit()

    return result


def update_device_online(
    device_id,
    device_name=None,
    serial_number=None,
    firmware=None,
    platform=None
):

    query = f"""
        UPDATE {DEVICE_TABLE}

        SET

            device_name =
                COALESCE(%s, device_name),

            serial_number =
                COALESCE(%s, serial_number),

            firmware =
                COALESCE(%s, firmware),

            platform =
                COALESCE(%s, platform),

            last_seen = CURRENT_TIMESTAMP,

            updated_at = CURRENT_TIMESTAMP

        WHERE device_id = %s
    """

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (
                    device_name,
                    serial_number,
                    firmware,
                    platform,
                    device_id
                )
            )

        conn.commit()


# ============================================================
# DEVICE ACTIVE CHECK
#
# Used by collector.py to notice a device being deactivated
# (e.g. via the "Remove" button) without waiting for its next
# natural reconnect. Deliberately does NOT touch status - only
# admin actions (add_device / activate_device / deactivate_device)
# are allowed to change it.
# ============================================================

def is_device_active(device_id):

    query = f"""
        SELECT status

        FROM {DEVICE_TABLE}

        WHERE device_id = %s

        LIMIT 1
    """

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (device_id,)
            )

            row = cur.fetchone()

    return bool(row) and row[0] == "active"


# ============================================================
# RECORD HASH
# ============================================================

def make_record_hash(
    device_id,
    user_id,
    attendance_time,
    status,
    punch
):

    value = "|".join([
        str(device_id or ""),
        str(user_id or ""),
        str(attendance_time or ""),
        str(status if status is not None else ""),
        str(punch if punch is not None else "")
    ])

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# ============================================================
# ATTENDANCE BULK INSERT
# ============================================================

def insert_records(records):

    if not records:

        return 0, 0

    total = len(records)

    print()
    print("Preparing PostgreSQL bulk insert...")
    print(f"Records to process: {total:,}")

    with get_connection() as conn:

        with conn.cursor() as cur:

            # ------------------------------------------------
            # TEMPORARY TABLE
            # ------------------------------------------------

            cur.execute("""
                CREATE TEMP TABLE
                zkteco_attendance_stage (

                    device_id TEXT,

                    branch_name TEXT,

                    device_ip TEXT,

                    device_port INTEGER,

                    device_name TEXT,

                    serial_number TEXT,

                    firmware TEXT,

                    platform TEXT,

                    user_id TEXT,

                    user_name TEXT,

                    attendance_time TIMESTAMP,

                    status INTEGER,

                    punch INTEGER,

                    punch_type TEXT,

                    record_hash TEXT

                )

                ON COMMIT DROP
            """)

            print(
                "Temporary staging table created."
            )

            # ------------------------------------------------
            # COPY
            # ------------------------------------------------

            copy_sql = """
                COPY zkteco_attendance_stage (

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

                    record_hash

                )

                FROM STDIN
            """

            print()
            print(
                "Uploading records to PostgreSQL..."
            )
            print("--------------------------------")

            with cur.copy(copy_sql) as copy:

                for index, record in enumerate(
                    records,
                    start=1
                ):

                    copy.write_row(record)

                    if (
                        index % 5000 == 0
                        or index == total
                    ):

                        percent = (
                            index / total
                        ) * 100

                        print(
                            f"Upload progress: "
                            f"{index:,}/{total:,} "
                            f"({percent:.1f}%)"
                        )

            print("--------------------------------")
            print("Upload completed.")

            # ------------------------------------------------
            # INSERT
            #
            # The composite UNIQUE constraint already exists
            # in your current database:
            #
            # UNIQUE (
            #     device_id,
            #     user_id,
            #     attendance_time,
            #     status,
            #     punch
            # )
            #
            # ------------------------------------------------

            print()
            print(
                "Moving records into main table..."
            )

            cur.execute(f"""
                INSERT INTO {ATTENDANCE_TABLE} (

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

                    record_hash

                )

                SELECT

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

                    record_hash

                FROM zkteco_attendance_stage

                ON CONFLICT (
                    device_id,
                    user_id,
                    attendance_time,
                    status,
                    punch
                )

                DO NOTHING
            """)

            inserted = cur.rowcount

        conn.commit()

    duplicates = total - inserted

    return inserted, duplicates


# ============================================================
# UPDATE ATTENDANCE EMPLOYEE NAMES
# ============================================================

def update_attendance_names(
    device_id,
    user_map
):

    if not user_map:

        return 0

    updated = 0

    with get_connection() as conn:

        with conn.cursor() as cur:

            for user_id, user_name in user_map.items():

                if not user_id:

                    continue

                if not user_name:

                    continue

                cur.execute(
                    f"""
                    UPDATE {ATTENDANCE_TABLE}

                    SET
                        user_name = %s

                    WHERE

                        device_id = %s

                        AND user_id = %s

                        AND (
                            user_name IS NULL
                            OR user_name = ''
                        )
                    """,
                    (
                        user_name,
                        device_id,
                        str(user_id)
                    )
                )

                updated += cur.rowcount

        conn.commit()

    return updated


# ============================================================
# TOTAL RECORDS
# ============================================================

def get_total_records():

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM {ATTENDANCE_TABLE}
                """
            )

            return cur.fetchone()[0]


# ============================================================
# LATEST RECORD
# ============================================================

def get_latest_record(
    device_id
):

    with get_dict_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                f"""
                SELECT *

                FROM {ATTENDANCE_TABLE}

                WHERE device_id = %s

                ORDER BY
                    attendance_time DESC,
                    id DESC

                LIMIT 1
                """,
                (device_id,)
            )

            return cur.fetchone()