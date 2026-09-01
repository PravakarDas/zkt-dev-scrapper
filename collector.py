import time
import signal

from datetime import datetime

from zk import ZK

from database import (
    create_table,
    get_active_devices,
    update_device_online,
    update_device_offline,
    insert_records
)


# ============================================================
# CONFIGURATION
# ============================================================

RETRY_SECONDS = 5

DEVICE_REFRESH_SECONDS = 10

SAFETY_SYNC_MINUTES = 20

ZK_TIMEOUT = 15


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


def signal_handler(
    signum,
    frame
):

    global STOP_REQUESTED

    print()
    print(
        "Stopping collector..."
    )

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

        firmware = (
            conn.get_firmware_version()
        )

    except Exception:

        pass


    try:

        serial = (
            conn.get_serialnumber()
        )

    except Exception:

        pass


    try:

        device_name = (
            conn.get_device_name()
        )

    except Exception:

        pass


    try:

        platform = (
            conn.get_platform()
        )

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

        "users_count": users_count

    }


# ============================================================
# PREPARE RECORD
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


    # --------------------------------------------------------
    # Device ID
    #
    # Physical serial number is the best identifier.
    # If serial is unavailable, use IP + port.
    # --------------------------------------------------------

    device_id = (

        device_info.get("serial")

        or

        device.get("device_id")

        or

        f"{device['ip_address']}:{device['port']}"

    )


    return (

        device_id,

        device["branch_name"],

        device["ip_address"],

        device["port"],

        device_info.get("device_name"),

        device_info.get("serial"),

        device_info.get("firmware"),

        device_info.get("platform"),

        user_id,

        None,

        timestamp,

        status,

        punch,

        punch_type,

        str(attendance)

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
        f"{device['branch_name']}"

    )

    print("=" * 70)


    print()

    print(

        f"Device : "
        f"{device['ip_address']}:"
        f"{device['port']}"

    )


    print()

    print(
        "Reading attendance records..."
    )


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

        print()

        print(
            "No attendance records "
            "found on device."
        )

        return


    # ========================================================
    # PREPARE
    # ========================================================

    print()

    print(
        "Preparing records..."
    )

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

            or

            index == total

        ):

            percent = (

                index / total

            ) * 100


            print(

                f"Prepare progress: "
                f"{index:,}/"
                f"{total:,} "
                f"({percent:.1f}%)"

            )


    print("--------------------------------")


    print(

        f"Prepared records: "
        f"{len(records):,}"

    )


    # ========================================================
    # DATABASE
    # ========================================================

    print()

    print(
        "Saving records to PostgreSQL..."
    )


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

    print(
        "SYNC COMPLETED"
    )

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


    try:

        inserted, duplicates = insert_records(

            [record]

        )

    except Exception as error:

        print()

        print(
            "LIVE DATABASE ERROR"
        )

        print(
            f"Error : "
            f"{type(error).__name__}"
        )

        print(
            f"Message : "
            f"{error}"
        )

        return


    print()

    print("=" * 70)

    print(
        "NEW ATTENDANCE"
    )

    print("=" * 70)


    print(

        f"Branch   : "
        f"{device['branch_name']}"

    )


    print(

        f"Device   : "
        f"{device['ip_address']}:"
        f"{device['port']}"

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

    print(
        "LIVE MONITORING"
    )

    print("=" * 70)


    print(

        f"Branch : "
        f"{device['branch_name']}"

    )


    print(

        f"Device : "
        f"{device['ip_address']}:"
        f"{device['port']}"

    )


    print()

    print(
        "Waiting for new attendance..."
    )


    print(

        f"Safety full sync after "
        f"{SAFETY_SYNC_MINUTES} "
        f"minutes without live event."

    )


    print()


    # --------------------------------------------------------
    # pyzk live_capture() does not support callback=.
    #
    # It is a generator.
    #
    # We therefore run it directly.
    # --------------------------------------------------------

    last_event_time = time.time()


    while not STOP_REQUESTED:

        try:

            for attendance in conn.live_capture():

                if STOP_REQUESTED:

                    return


                if attendance is None:

                    continue


                # ------------------------------------------------
                # New live attendance received
                # ------------------------------------------------

                save_live_record(

                    attendance,

                    device,

                    device_info

                )


                # ------------------------------------------------
                # Reset 20-minute safety timer
                # ------------------------------------------------

                last_event_time = time.time()


                print()

                print(

                    "Live event received."
                    " Safety timer reset."

                )


                # ------------------------------------------------
                # Stop live capture temporarily.
                #
                # The outer device loop will check whether
                # 20 minutes have passed and can perform a
                # full sync.
                # ------------------------------------------------

                break


            # ----------------------------------------------------
            # Check safety timer
            # ----------------------------------------------------

            elapsed = (

                time.time()

                - last_event_time

            )


            if (

                elapsed

                >=

                SAFETY_SYNC_MINUTES * 60

            ):

                print()

                print(

                    f"No live event for "
                    f"{SAFETY_SYNC_MINUTES} "
                    f"minutes."

                )

                print(
                    "Starting safety full sync..."
                )

                full_sync(

                    conn,

                    device,

                    device_info

                )


                last_event_time = time.time()


            else:

                # Small delay before starting another
                # live_capture session.

                time.sleep(1)


        except Exception as error:

            raise error


# ============================================================
# CONNECT TO DEVICE
# ============================================================

def connect_device(device):

    print()

    print("=" * 70)

    print(

        f"DEVICE - "
        f"{device['branch_name']}"

    )

    print("=" * 70)


    print()

    print(

        f"Connecting to "
        f"{device['ip_address']}:"
        f"{device['port']}"

    )


    zk = ZK(

        device["ip_address"],

        port=device["port"],

        timeout=ZK_TIMEOUT,

        password=0,

        force_udp=False,

        ommit_ping=False

    )


    conn = zk.connect()


    print()

    print(

        f"CONNECTED: "
        f"{device['ip_address']}:"
        f"{device['port']}"

    )


    return zk, conn


# ============================================================
# PROCESS ONE DEVICE
# ============================================================

def process_device(device):

    zk = None

    conn = None


    try:

        zk, conn = connect_device(device)


        # ----------------------------------------------------
        # Device information
        # ----------------------------------------------------

        device_info = get_device_information(

            conn

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


        # ----------------------------------------------------
        # Device ID
        # ----------------------------------------------------

        actual_device_id = (

            device_info.get("serial")

            or

            device["device_id"]

        )


        # ----------------------------------------------------
        # Update device information
        # ----------------------------------------------------

        update_device_online(

            actual_device_id,

            device_name=device_info.get(
                "device_name"
            ),

            serial_number=device_info.get(
                "serial"
            ),

            firmware=device_info.get(
                "firmware"
            ),

            platform=device_info.get(
                "platform"
            )

        )


        print()

        print(
            "Device database status: ONLINE"
        )


        # ----------------------------------------------------
        # Full sync
        # ----------------------------------------------------

        full_sync(

            conn,

            device,

            device_info

        )


        # ----------------------------------------------------
        # Live monitor
        # ----------------------------------------------------

        live_monitor(

            conn,

            device,

            device_info

        )


    except Exception as error:

        print()

        print("=" * 70)

        print(
            "DEVICE ERROR"
        )

        print("=" * 70)


        print(

            f"Branch : "
            f"{device['branch_name']}"

        )


        print(

            f"Device : "
            f"{device['ip_address']}:"
            f"{device['port']}"

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
            "Device is offline or connection was lost."
        )


        try:

            device_id = (

                device.get("device_id")

            )

            if device_id:

                update_device_offline(

                    device_id

                )

        except Exception:

            pass


        return False


    finally:

        if conn:

            try:

                conn.disconnect()

                print(
                    "Disconnected."
                )

            except Exception:

                pass


        return True


# ============================================================
# DEVICE MANAGER
# ============================================================

def device_manager():

    print()

    print("=" * 70)

    print(
        "DEVICE MANAGER STARTED"
    )

    print("=" * 70)


    processed_devices = {}


    while not STOP_REQUESTED:

        try:

            devices = get_active_devices()


        except Exception as error:

            print()

            print(
                "DATABASE ERROR"
            )

            print(
                f"{type(error).__name__}: "
                f"{error}"
            )

            time.sleep(

                DEVICE_REFRESH_SECONDS

            )

            continue


        if not devices:

            print()

            print(
                "WARNING: No active devices "
                "found in zkt_devices."
            )

            print(
                "Add a device from the "
                "Devices page."
            )

            time.sleep(

                DEVICE_REFRESH_SECONDS

            )

            continue


        for device in devices:

            if STOP_REQUESTED:

                break


            device_key = device["device_id"]


            # ------------------------------------------------
            # New device
            # ------------------------------------------------

            if device_key not in processed_devices:

                print()

                print("=" * 70)

                print(
                    "NEW ACTIVE DEVICE DETECTED"
                )

                print(

                    f"Branch : "
                    f"{device['branch_name']}"

                )

                print(

                    f"Device : "
                    f"{device['ip_address']}:"
                    f"{device['port']}"

                )

                print("=" * 70)


                processed_devices[
                    device_key
                ] = {

                    "last_attempt":
                    0

                }


            # ------------------------------------------------
            # Process device
            # ------------------------------------------------

            last_attempt = processed_devices[
                device_key
            ]["last_attempt"]


            if (

                time.time()

                - last_attempt

                <

                RETRY_SECONDS

            ):

                continue


            processed_devices[
                device_key
            ]["last_attempt"] = time.time()


            success = process_device(

                device

            )


            if not success:

                print()

                print(

                    f"Retrying "
                    f"{device['branch_name']} "
                    f"in "
                    f"{RETRY_SECONDS} seconds..."

                )


            if success:

                # ------------------------------------------------
                # process_device() returns after:
                #
                # - connection lost
                # - live monitor ended
                # - error
                #
                # We then retry.
                # ------------------------------------------------

                processed_devices[
                    device_key
                ]["last_attempt"] = time.time()


        # ----------------------------------------------------
        # Refresh active device list
        # ----------------------------------------------------

        if not STOP_REQUESTED:

            time.sleep(

                DEVICE_REFRESH_SECONDS

            )


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print("=" * 70)

    print(
        "ZKTeco MULTI DEVICE COLLECTOR"
    )

    print("=" * 70)

    print()


    # --------------------------------------------------------
    # Database initialization
    # --------------------------------------------------------

    create_table()


    try:

        devices = get_active_devices()

        print(

            f"Configured active devices : "
            f"{len(devices)}"

        )

    except Exception as error:

        print()

        print(
            "Could not read devices."
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        return


    print(

        f"Device retry interval     : "
        f"{RETRY_SECONDS} seconds"

    )


    print(

        f"Device refresh interval   : "
        f"{DEVICE_REFRESH_SECONDS} seconds"

    )


    print(

        f"Safety full sync          : "
        f"{SAFETY_SYNC_MINUTES} minutes"

    )


    if not devices:

        print()

        print(
            "WARNING: No active devices "
            "found in zkt_devices."
        )

        print(
            "Add a device from the "
            "Devices page."
        )


    device_manager()


    print()

    print(
        "Collector stopped."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()