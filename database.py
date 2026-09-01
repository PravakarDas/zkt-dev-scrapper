import psycopg
from psycopg.rows import dict_row


from config import DATABASE_URL


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
# CREATE / INITIALIZE TABLES
# ============================================================

def create_table():

    query = f"""

    CREATE TABLE IF NOT EXISTS {ATTENDANCE_TABLE} (

        id BIGSERIAL PRIMARY KEY,

        device_id TEXT,

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

        record_hash TEXT,

        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

    );


    CREATE INDEX IF NOT EXISTS
    idx_zkt_attendance_time

    ON {ATTENDANCE_TABLE}(attendance_time);


    CREATE INDEX IF NOT EXISTS
    idx_zkt_attendance_user

    ON {ATTENDANCE_TABLE}(user_id);


    CREATE INDEX IF NOT EXISTS
    idx_zkt_attendance_device

    ON {ATTENDANCE_TABLE}(device_id);


    CREATE INDEX IF NOT EXISTS
    idx_zkt_attendance_branch

    ON {ATTENDANCE_TABLE}(branch_name);


    CREATE TABLE IF NOT EXISTS {DEVICE_TABLE} (

        id BIGSERIAL PRIMARY KEY,

        device_id TEXT UNIQUE NOT NULL,

        branch_name TEXT NOT NULL,

        ip_address TEXT NOT NULL,

        port INTEGER NOT NULL DEFAULT 4370,

        device_name TEXT,

        serial_number TEXT,

        firmware TEXT,

        platform TEXT,

        status TEXT NOT NULL DEFAULT 'active',

        first_seen TIMESTAMPTZ,

        last_seen TIMESTAMPTZ,

        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

    );


    CREATE INDEX IF NOT EXISTS
    idx_zkt_devices_status

    ON {DEVICE_TABLE}(status);


    CREATE INDEX IF NOT EXISTS
    idx_zkt_devices_ip

    ON {DEVICE_TABLE}(ip_address);

    """

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query)

            # ------------------------------------------------
            # Make sure attendance unique constraint exists.
            #
            # This is needed because the table may already
            # exist from an older version of the project.
            # ------------------------------------------------

            cur.execute(
                f"""
                SELECT 1
                FROM pg_constraint
                WHERE conname =
                'zkt_attendance_device_record_unique'
                """
            )

            constraint_exists = cur.fetchone()

            if not constraint_exists:

                cur.execute(
                    f"""
                    ALTER TABLE {ATTENDANCE_TABLE}

                    ADD CONSTRAINT
                    zkt_attendance_device_record_unique

                    UNIQUE (
                        device_id,
                        user_id,
                        attendance_time,
                        status,
                        punch
                    )
                    """
                )

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
            last_seen

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

        SELECT *

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

        SELECT *

        FROM {DEVICE_TABLE}

        WHERE ip_address = %s

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


# ============================================================
# ADD DEVICE
# ============================================================

def add_device(

    device_id,
    branch_name,
    ip_address,
    port,
    device_name=None,
    serial_number=None,
    firmware=None,
    platform=None

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


# ============================================================
# UPDATE DEVICE
# ============================================================

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

            updated_at =
            CURRENT_TIMESTAMP

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


# ============================================================
# DEACTIVATE DEVICE
# ============================================================

def deactivate_device(device_id):

    query = f"""

        UPDATE {DEVICE_TABLE}

        SET

            status = 'inactive',

            updated_at =
            CURRENT_TIMESTAMP

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


# ============================================================
# ACTIVATE DEVICE
# ============================================================

def activate_device(device_id):

    query = f"""

        UPDATE {DEVICE_TABLE}

        SET

            status = 'active',

            updated_at =
            CURRENT_TIMESTAMP

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


# ============================================================
# DEVICE ONLINE UPDATE
# ============================================================

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

            status = 'active',

            last_seen =
            CURRENT_TIMESTAMP,

            updated_at =
            CURRENT_TIMESTAMP

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
# DEVICE OFFLINE UPDATE
# ============================================================

def update_device_offline(device_id):

    query = f"""

        UPDATE {DEVICE_TABLE}

        SET

            status = 'offline',

            updated_at =
            CURRENT_TIMESTAMP

        WHERE device_id = %s

    """

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (device_id,)
            )

        conn.commit()


# ============================================================
# BULK ATTENDANCE INSERT
# ============================================================

def insert_records(records):

    if not records:

        return 0, 0


    total = len(records)


    print()
    print(
        "Preparing PostgreSQL bulk insert..."
    )

    print(
        f"Records to process: "
        f"{total:,}"
    )


    with get_connection() as conn:

        with conn.cursor() as cur:

            # ------------------------------------------------
            # Temporary staging table
            # ------------------------------------------------

            cur.execute(
                """

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

                ON COMMIT DROP;

                """
            )


            print(
                "Temporary staging table created."
            )


            # ------------------------------------------------
            # COPY data
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

                WITH (
                    FORMAT CSV,
                    DELIMITER E'\\t',
                    NULL '\\N'
                )

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

                    values = []

                    for value in record:

                        if value is None:

                            values.append("\\N")

                        else:

                            value = str(value)

                            value = (
                                value
                                .replace("\\", "\\\\")
                                .replace("\t", " ")
                                .replace("\n", " ")
                                .replace("\r", " ")
                            )

                            values.append(value)


                    line = (
                        "\t".join(values)
                        + "\n"
                    )

                    copy.write(line)


                    if (

                        index % 5000 == 0

                        or index == total

                    ):

                        percent = (
                            index / total
                        ) * 100

                        print(

                            f"Upload progress: "
                            f"{index:,}/"
                            f"{total:,} "
                            f"({percent:.1f}%)"

                        )


            print("--------------------------------")

            print(
                "Upload completed."
            )


            # ------------------------------------------------
            # Move into main table
            # ------------------------------------------------

            print()
            print(
                "Moving records into main table..."
            )


            cur.execute(

                f"""

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

                """

            )


            # ------------------------------------------------
            # Get insert count
            # ------------------------------------------------

            inserted = cur.rowcount


        conn.commit()


    duplicates = total - inserted


    return inserted, duplicates


# ============================================================
# GET ATTENDANCE COUNT
# ============================================================

def get_attendance_count():

    query = f"""

        SELECT COUNT(*)

        FROM {ATTENDANCE_TABLE}

    """

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(query)

            return cur.fetchone()[0]