import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from config import DATABASE_URL


TABLE_NAME = "zkteco_attendance"


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=20
    )


def create_table():
    query = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id BIGSERIAL PRIMARY KEY,

        branch_name TEXT NOT NULL,

        device_ip TEXT NOT NULL,
        device_port INTEGER,

        device_serial TEXT,
        device_name TEXT,
        device_platform TEXT,
        device_firmware TEXT,

        user_id TEXT NOT NULL,
        user_name TEXT,

        attendance_time TIMESTAMP NOT NULL,

        status INTEGER,
        punch INTEGER,
        punch_type TEXT,

        raw_data TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT zkteco_attendance_unique
        UNIQUE (
            device_serial,
            user_id,
            attendance_time,
            status,
            punch
        )
    );

    CREATE INDEX IF NOT EXISTS idx_zkteco_time
    ON {TABLE_NAME}(attendance_time);

    CREATE INDEX IF NOT EXISTS idx_zkteco_user
    ON {TABLE_NAME}(user_id);

    CREATE INDEX IF NOT EXISTS idx_zkteco_device
    ON {TABLE_NAME}(device_serial);

    CREATE INDEX IF NOT EXISTS idx_zkteco_branch
    ON {TABLE_NAME}(branch_name);
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)

        conn.commit()

    print("Database initialized successfully.")


def insert_records(records):
    """
    Insert many attendance records efficiently.

    Uses PostgreSQL COPY into a temporary table, then performs
    one INSERT ... SELECT with ON CONFLICT DO NOTHING.
    """

    if not records:
        return 0, 0

    total = len(records)

    print()
    print("Preparing PostgreSQL bulk insert...")
    print(f"Records to process: {total:,}")

    with get_connection() as conn:

        with conn.cursor() as cur:

            # --------------------------------------------------
            # Temporary staging table
            # --------------------------------------------------

            cur.execute("""
                CREATE TEMP TABLE zkteco_attendance_stage (
                    branch_name TEXT,
                    device_ip TEXT,
                    device_port INTEGER,

                    device_serial TEXT,
                    device_name TEXT,
                    device_platform TEXT,
                    device_firmware TEXT,

                    user_id TEXT,
                    user_name TEXT,

                    attendance_time TIMESTAMP,

                    status INTEGER,
                    punch INTEGER,
                    punch_type TEXT,

                    raw_data TEXT
                ) ON COMMIT DROP;
            """)

            print("Temporary staging table created.")

            # --------------------------------------------------
            # COPY data into PostgreSQL
            # --------------------------------------------------

            copy_sql = """
                COPY zkteco_attendance_stage (
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

                    raw_data
                )
                FROM STDIN
            """

            print()
            print("Uploading records to PostgreSQL...")
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

            # --------------------------------------------------
            # Insert staged records
            # --------------------------------------------------

            print()
            print("Moving records into main table...")

            cur.execute(f"""
                INSERT INTO {TABLE_NAME} (
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

                    raw_data
                )

                SELECT
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

                    raw_data

                FROM zkteco_attendance_stage

                ON CONFLICT (
                    device_serial,
                    user_id,
                    attendance_time,
                    status,
                    punch
                )

                DO NOTHING;
            """)

            inserted = cur.rowcount

            conn.commit()

    duplicates = total - inserted

    return inserted, duplicates


def get_total_records():

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME}"
            )

            return cur.fetchone()[0]


def get_latest_record(device_serial):

    with get_connection() as conn:

        with conn.cursor(
            row_factory=dict_row
        ) as cur:

            cur.execute(
                f"""
                SELECT *
                FROM {TABLE_NAME}
                WHERE device_serial = %s
                ORDER BY attendance_time DESC
                LIMIT 1
                """,
                (device_serial,)
            )

            return cur.fetchone()