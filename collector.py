import time
import signal
import sys

from datetime import datetime, timedelta

from zk import ZK

from database import (
    create_table,
    insert_records
)


# ============================================================
# CONFIGURATION
# ============================================================

RETRY_SECONDS = 5

SAFETY_SYNC_MINUTES = 20

DEVICES = [

    {
        "name": "CTG Office",
        "ip": "119.10.168.198",
        "port": 1111,
        "password": 0,
    },

    # Add more devices like this:
    #
    # {
    #     "name": "Dhaka Office",
    #     "ip": "xxx.xxx.xxx.xxx",
    #     "port": 1111,
    #     "password": 0,
    # },
]


# ============================================================
# PUNCH TYPES
# ============================================================

PUNCH_TYPES = {

    0: "Check In",
    1: "Check Out",
    2: "Break In",
    3: "Break Out",
    4: "Overtime In",
    5: "Out",

}


# ============================================================
# STOP FLAG
# ============================================================

STOP_REQUESTED = False


def signal_handler(signum, frame):

    global STOP_REQUESTED

    print()
    print("Stopping collector...")

    STOP_REQUESTED = True


signal.signal(
    signal.SIGINT,
    signal_handler
)

signal.signal(
    signal.SIGTERM,
    signal_handler
)


# ============================================================
# DEVICE INFORMATION
# ============================================================

def get_device_information(conn):

    firmware = None
    serial = None
    device_name = None
    platform = None
    users_count = 0

    try:
        firmware = conn.get_firmware_version()
    except Exception:
        pass

    try:
        serial = conn.get_serialnumber()
    except Exception:
        pass

    try:
        device_name = conn.get_device_name()
    except Exception:
        pass

    try:
        platform = conn.get_platform()
    except Exception:
        pass

    try:

        users = conn.get_users()

        users_count = len(users)

    except Exception:
        pass

    return {

        "firmware": firmware,

        "serial": serial,

        "device_name": device_name,

        "platform": platform,

        "users_count": users_count,

    }


# ============================================================
# PREPARE ATTENDANCE RECORD
# ============================================================

def prepare_record(
    attendance,
    device,
    device_info
):

    user_id = str(
        getattr(
            attendance,
            "user_id",
            ""
        )
    )

    timestamp = getattr(
        attendance,
        "timestamp",
        None
    )

    status = getattr(
        attendance,
        "status",
        None
    )

    punch = getattr(
        attendance,
        "punch",
        None
    )

    punch_type = PUNCH_TYPES.get(
        punch,
        "Unknown"
    )

    return (

        device["name"],

        device["ip"],

        device["port"],

        device_info.get(
            "serial"
        ),

        device_info.get(
            "device_name"
        ),

        device_info.get(
            "platform"
        ),

        device_info.get(
            "firmware"
        ),

        user_id,

        None,

        timestamp,

        status,

        punch,

        punch_type,

        str(attendance),

    )


# ============================================================
# FULL SYNC
# ============================================================

def full_sync(
    conn,
    device,
    device_info
):

    print()
    print("=" * 70)
    print(
        f"FULL SYNC - "
        f"{device['name']}"
    )
    print("=" * 70)

    print()
    print("Reading attendance records...")

    start_time = time.time()

    attendances = conn.get_attendance()

    reading_time = (
        time.time()
        - start_time
    )

    total = len(attendances)

    print()
    print(
        f"Device records : "
        f"{total:,}"
    )

    print(
        f"Reading time   : "
        f"{reading_time:.2f} seconds"
    )

    if total == 0:

        print(
            "No attendance records "
            "found on device."
        )

        return

    # --------------------------------------------------------
    # Prepare everything in memory
    # --------------------------------------------------------

    print()
    print("Preparing records...")
    print("--------------------------------")

    records = []

    for index, attendance in enumerate(
        attendances,
        start=1
    ):

        records.append(
            prepare_record(
                attendance,
                device,
                device_info
            )
        )

        if (
            index % 5000 == 0
            or index == total
        ):

            percent = (
                index / total
            ) * 100

            print(
                f"Prepare progress: "
                f"{index:,}/{total:,} "
                f"({percent:.1f}%)"
            )

    print("--------------------------------")
    print(
        f"Prepared records: "
        f"{len(records):,}"
    )

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    print()
    print("Saving records to PostgreSQL...")

    database_start = time.time()

    inserted, duplicates = insert_records(
        records
    )

    database_time = (
        time.time()
        - database_start
    )

    print()
    print("=" * 70)
    print("SYNC COMPLETED")
    print("=" * 70)

    print(
        f"Device records : "
        f"{total:,}"
    )

    print(
        f"Prepared       : "
        f"{len(records):,}"
    )

    print(
        f"New records    : "
        f"{inserted:,}"
    )

    print(
        f"Existing       : "
        f"{duplicates:,}"
    )

    print(
        f"Database time  : "
        f"{database_time:.2f} seconds"
    )


# ============================================================
# SAVE LIVE RECORD
# ============================================================

def save_live_record(
    attendance,
    device,
    device_info
):

    record = prepare_record(
        attendance,
        device,
        device_info
    )

    inserted, duplicates = insert_records(
        [record]
    )

    print()
    print("=" * 70)
    print("NEW ATTENDANCE")
    print("=" * 70)

    print(
        f"Branch   : "
        f"{device['name']}"
    )

    print(
        f"Device   : "
        f"{device['ip']}:{device['port']}"
    )

    print(
        f"Serial   : "
        f"{device_info.get('serial')}"
    )

    print(
        f"Employee : "
        f"{getattr(attendance, 'user_id', '')}"
    )

    print(
        f"Time     : "
        f"{getattr(attendance, 'timestamp', '')}"
    )

    print(
        f"Status   : "
        f"{getattr(attendance, 'status', '')}"
    )

    print(
        f"Punch    : "
        f"{getattr(attendance, 'punch', '')}"
    )

    punch = getattr(
        attendance,
        "punch",
        None
    )

    print(
        f"Type     : "
        f"{PUNCH_TYPES.get(punch, 'Unknown')}"
    )

    if inserted:

        print(
            "Database : SAVED"
        )

    else:

        print(
            "Database : DUPLICATE - IGNORED"
        )


# ============================================================
# LIVE MONITOR
# ============================================================

def live_monitor(
    conn,
    device,
    device_info
):

    print()
    print("=" * 70)
    print("LIVE MONITORING")
    print("=" * 70)

    print(
        f"Branch: "
        f"{device['name']}"
    )

    print(
        "Waiting for new attendance..."
    )

    print(
        f"Safety full sync after "
        f"{SAFETY_SYNC_MINUTES} minutes "
        f"without live event."
    )

    print()

    # --------------------------------------------------------
    # IMPORTANT
    #
    # pyzk 0.9 live_capture() is a blocking generator.
    #
    # Therefore the 20-minute safety check is handled by
    # checking the generator timeout behaviour below.
    # --------------------------------------------------------

    last_event = datetime.now()

    while not STOP_REQUESTED:

        try:

            for attendance in conn.live_capture():

                if STOP_REQUESTED:

                    return

                if attendance is None:

                    continue

                # New attendance received

                save_live_record(
                    attendance,
                    device,
                    device_info
                )

                # Reset safety timer

                last_event = datetime.now()

        except Exception as error:

            print()
            print("=" * 70)
            print("LIVE CAPTURE ERROR")
            print("=" * 70)

            print(
                f"Branch : "
                f"{device['name']}"
            )

            print(
                f"Device : "
                f"{device['ip']}:{device['port']}"
            )

            print(
                f"Error  : "
                f"{type(error).__name__}"
            )

            print(
                f"Message: "
                f"{error}"
            )

            return False

        # ----------------------------------------------------
        # Safety sync
        # ----------------------------------------------------

        elapsed = (
            datetime.now()
            - last_event
        )

        if elapsed >= timedelta(
            minutes=SAFETY_SYNC_MINUTES
        ):

            print()
            print(
                "No live attendance received "
                f"for {SAFETY_SYNC_MINUTES} minutes."
            )

            print(
                "Running safety full sync..."
            )

            try:

                full_sync(
                    conn,
                    device,
                    device_info
                )

                last_event = datetime.now()

            except Exception as error:

                print(
                    "Safety sync error:"
                )

                print(error)

    return True


# ============================================================
# CONNECT DEVICE
# ============================================================

def connect_device(device):

    print()
    print("=" * 70)
    print(
        f"DEVICE - "
        f"{device['name']}"
    )
    print("=" * 70)

    print(
        f"Connecting to "
        f"{device['ip']}:{device['port']}"
    )

    zk = ZK(

        device["ip"],

        port=device["port"],

        timeout=10,

        password=device.get(
            "password",
            0
        ),

        force_udp=False,

        ommit_ping=False,

    )

    conn = zk.connect()

    print(
        f"CONNECTED: "
        f"{device['ip']}:{device['port']}"
    )

    return zk, conn


# ============================================================
# RUN ONE DEVICE
# ============================================================

def run_device(device):

    while not STOP_REQUESTED:

        zk = None

        conn = None

        try:

            zk, conn = connect_device(
                device
            )

            # ------------------------------------------------
            # Device information
            # ------------------------------------------------

            device_info = (
                get_device_information(
                    conn
                )
            )

            print(
                f"Serial   : "
                f"{device_info.get('serial')}"
            )

            print(
                f"Firmware : "
                f"{device_info.get('firmware')}"
            )

            print(
                f"Device   : "
                f"{device_info.get('device_name')}"
            )

            print(
                f"Platform : "
                f"{device_info.get('platform')}"
            )

            print(
                f"Users    : "
                f"{device_info.get('users_count')}"
            )

            print(
                "Device database status: ONLINE"
            )

            # ------------------------------------------------
            # Full sync
            # ------------------------------------------------

            full_sync(
                conn,
                device,
                device_info
            )

            # ------------------------------------------------
            # Live monitoring
            # ------------------------------------------------

            live_monitor(
                conn,
                device,
                device_info
            )

        except Exception as error:

            print()
            print("=" * 70)
            print("DEVICE ERROR")
            print("=" * 70)

            print(
                f"Branch : "
                f"{device['name']}"
            )

            print(
                f"Device : "
                f"{device['ip']}:{device['port']}"
            )

            print(
                f"Error  : "
                f"{type(error).__name__}"
            )

            print(
                f"Message: "
                f"{error}"
            )

            print()
            print(
                "Device is offline "
                "or connection was lost."
            )

        finally:

            if conn:

                try:

                    conn.disconnect()

                    print(
                        "Disconnected."
                    )

                except Exception:

                    pass

        if STOP_REQUESTED:

            break

        print()
        print(
            f"Retrying in "
            f"{RETRY_SECONDS} seconds..."
        )

        for _ in range(
            RETRY_SECONDS
        ):

            if STOP_REQUESTED:

                break

            time.sleep(1)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("ZKTeco MULTI DEVICE COLLECTOR")
    print("=" * 70)

    print()

    create_table()

    print(
        f"Configured devices : "
        f"{len(DEVICES)}"
    )

    print(
        f"Device retry       : "
        f"{RETRY_SECONDS} seconds"
    )

    print(
        f"Safety full sync   : "
        f"{SAFETY_SYNC_MINUTES} minutes"
    )

    print()

    while not STOP_REQUESTED:

        for device in DEVICES:

            if STOP_REQUESTED:

                break

            run_device(device)

    print()
    print("=" * 70)
    print("COLLECTOR STOPPED")
    print("=" * 70)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()