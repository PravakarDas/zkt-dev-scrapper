import time
import signal

from datetime import datetime, timedelta

from zk import ZK

from database import (
    create_table,
    get_active_devices,
    update_device_online,
    insert_records,
    update_attendance_names,
    make_record_hash
)


# ============================================================
# CONFIGURATION
# ============================================================

RETRY_SECONDS = 5

DEVICE_REFRESH_SECONDS = 10

SAFETY_SYNC_MINUTES = 20


# ============================================================
# PUNCH TYPES
# ============================================================

PUNCH_TYPES = {

    0: "Check In",

    1: "Check Out",

    2: "Break In",

    3: "Break Out",

    4: "Overtime In",

    5: "Out"

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

def get_device_information(
    conn
):

    firmware = None

    serial = None

    device_name = None

    platform = None

    users = []

    users_count = 0


    # --------------------------------------------------------
    # Firmware
    # --------------------------------------------------------

    try:

        firmware = (
            conn.get_firmware_version()
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # Serial
    # --------------------------------------------------------

    try:

        serial = (
            conn.get_serialnumber()
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # Device name
    # --------------------------------------------------------

    try:

        device_name = (
            conn.get_device_name()
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # Platform
    # --------------------------------------------------------

    try:

        platform = (
            conn.get_platform()
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # Users
    # --------------------------------------------------------

    try:

        users = conn.get_users()

        users_count = len(users)

    except Exception:

        users = []

        users_count = 0


    return {

        "firmware": firmware,

        "serial": serial,

        "device_name": device_name,

        "platform": platform,

        "users": users,

        "users_count": users_count

    }


# ============================================================
# BUILD USER MAP
# ============================================================

def build_user_map(
    users
):

    user_map = {}


    for user in users:

        try:

            user_id = getattr(
                user,
                "user_id",
                None
            )

            name = getattr(
                user,
                "name",
                None
            )


            if not user_id:

                continue


            if not name:

                continue


            name = str(
                name
            ).strip()


            if not name:

                continue


            user_map[
                str(user_id)
            ] = name

        except Exception:

            continue


    return user_map


# ============================================================
# PREPARE ATTENDANCE RECORD
# ============================================================

def prepare_record(
    attendance,
    device,
    device_info,
    user_map
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
    # Employee name
    # --------------------------------------------------------

    user_name = user_map.get(
        user_id
    )


    # --------------------------------------------------------
    # Stable device ID
    # --------------------------------------------------------

    device_id = (
        device.get("device_id")
        or device_info.get("serial")
        or device.get("ip")
    )


    serial_number = (
        device_info.get("serial")
        or device.get("serial_number")
    )


    # --------------------------------------------------------
    # Record hash
    # --------------------------------------------------------

    record_hash = make_record_hash(

        device_id,

        user_id,

        timestamp,

        status,

        punch

    )


    return (

        device_id,

        device["branch_name"],

        device["ip_address"],

        device["port"],

        device_info.get(
            "device_name"
        ),

        serial_number,

        device_info.get(
            "firmware"
        ),

        device_info.get(
            "platform"
        ),

        user_id,

        user_name,

        timestamp,

        status,

        punch,

        punch_type,

        record_hash

    )


# ============================================================
# FULL SYNC
# ============================================================

def full_sync(
    conn,
    device,
    device_info,
    user_map
):

    print()

    print(
        "=" * 70
    )

    print(
        f"FULL SYNC - "
        f"{device['branch_name']}"
    )

    print(
        "=" * 70
    )


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


    attendances = (
        conn.get_attendance()
    )


    reading_time = (
        time.time()
        - start_time
    )


    total = len(
        attendances
    )


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
    # Prepare
    # --------------------------------------------------------

    print()

    print(
        "Preparing records..."
    )

    print(
        "--------------------------------"
    )


    records = []


    for index, attendance in enumerate(
        attendances,
        start=1
    ):

        records.append(
            prepare_record(

                attendance,

                device,

                device_info,

                user_map

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


    print(
        "--------------------------------"
    )


    print(
        f"Prepared records: "
        f"{len(records):,}"
    )


    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    print()

    print(
        "Saving records to PostgreSQL..."
    )


    database_start = time.time()


    inserted, duplicates = (
        insert_records(
            records
        )
    )


    database_time = (
        time.time()
        - database_start
    )


    # --------------------------------------------------------
    # Update names in old records
    # --------------------------------------------------------

    names_updated = 0


    if user_map:

        try:

            names_updated = (
                update_attendance_names(

                    device["device_id"],

                    user_map

                )
            )

        except Exception as error:

            print()

            print(
                "Employee name update warning:"
            )

            print(
                error
            )


    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    print()

    print(
        "=" * 70
    )

    print(
        "SYNC COMPLETED"
    )

    print(
        "=" * 70
    )


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
        f"Names updated  : "
        f"{names_updated:,}"
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
    device_info,
    user_map
):

    record = prepare_record(

        attendance,

        device,

        device_info,

        user_map

    )


    inserted, duplicates = (
        insert_records(
            [record]
        )
    )


    print()

    print(
        "=" * 70
    )

    print(
        "NEW ATTENDANCE"
    )

    print(
        "=" * 70
    )


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


    employee_id = getattr(
        attendance,
        "user_id",
        ""
    )


    employee_name = user_map.get(
        str(employee_id)
    )


    print(
        f"Employee : "
        f"{employee_id}"
    )


    print(
        f"Name     : "
        f"{employee_name or '-'}"
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
    device_info,
    user_map
):

    print()

    print(
        "=" * 70
    )

    print(
        "LIVE MONITORING"
    )

    print(
        "=" * 70
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


    print()

    print(
        "Waiting for new attendance..."
    )


    print(
        f"Safety full sync after "
        f"{SAFETY_SYNC_MINUTES} minutes "
        f"without live event."
    )


    print()


    last_event = datetime.now()


    while not STOP_REQUESTED:

        try:

            for attendance in (
                conn.live_capture()
            ):

                if STOP_REQUESTED:

                    return False


                if attendance is None:

                    continue


                save_live_record(

                    attendance,

                    device,

                    device_info,

                    user_map

                )


                last_event = datetime.now()


                print()

                print(
                    "Live event received. "
                    "Safety timer reset."
                )


        except Exception as error:

            print()

            print(
                "=" * 70
            )

            print(
                "LIVE CAPTURE ERROR"
            )

            print(
                "=" * 70
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

                    device_info,

                    user_map

                )


                last_event = (
                    datetime.now()
                )


            except Exception as error:

                print(
                    "Safety sync error:"
                )

                print(
                    error
                )


    return True


# ============================================================
# CONNECT DEVICE
# ============================================================

def connect_device(
    device
):

    print()

    print(
        "=" * 70
    )

    print(
        f"DEVICE - "
        f"{device['branch_name']}"
    )

    print(
        "=" * 70
    )


    print(
        f"Connecting to "
        f"{device['ip_address']}:"
        f"{device['port']}"
    )


    zk = ZK(

        device["ip_address"],

        port=device["port"],

        timeout=10,

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
# RUN ONE DEVICE
# ============================================================

def run_device(
    device
):

    zk = None

    conn = None


    try:

        zk, conn = connect_device(
            device
        )


        # ----------------------------------------------------
        # Device information
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # Build employee map
        # ----------------------------------------------------

        user_map = build_user_map(
            device_info.get(
                "users",
                []
            )
        )


        print(
            f"Employee names loaded: "
            f"{len(user_map):,}"
        )


        # ----------------------------------------------------
        # Update device database
        # ----------------------------------------------------

        device_id = (
            device.get("device_id")
            or device_info.get("serial")
        )


        if device_id:

            update_device_online(

                device_id,

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


        print(
            "Device database status: ONLINE"
        )


        # ----------------------------------------------------
        # Full sync
        # ----------------------------------------------------

        full_sync(

            conn,

            device,

            device_info,

            user_map

        )


        # ----------------------------------------------------
        # Live monitoring
        # ----------------------------------------------------

        live_monitor(

            conn,

            device,

            device_info,

            user_map

        )


    except Exception as error:

        print()

        print(
            "=" * 70
        )

        print(
            "DEVICE ERROR"
        )

        print(
            "=" * 70
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


# ============================================================
# DEVICE MANAGER
# ============================================================

def device_manager():

    active_devices = {}


    while not STOP_REQUESTED:

        try:

            devices = (
                get_active_devices()
            )


            current_ids = {
                device["device_id"]
                for device in devices
            }


            # ------------------------------------------------
            # Detect newly active devices
            # ------------------------------------------------

            for device in devices:

                device_id = (
                    device["device_id"]
                )


                if device_id not in active_devices:

                    print()

                    print(
                        "=" * 70
                    )

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

                    print(
                        "=" * 70
                    )


                    active_devices[
                        device_id
                    ] = device


            # ------------------------------------------------
            # Remove inactive devices
            # ------------------------------------------------

            removed = (
                set(active_devices.keys())
                - current_ids
            )


            for device_id in removed:

                print()

                print(
                    "=" * 70
                )

                print(
                    "DEVICE NO LONGER ACTIVE"
                )

                print(
                    f"Device ID: "
                    f"{device_id}"
                )

                print(
                    "=" * 70
                )


                del active_devices[
                    device_id
                ]


            # ------------------------------------------------
            # Run active devices
            #
            # This version processes devices one by one.
            # ------------------------------------------------

            for device in list(
                active_devices.values()
            ):

                if STOP_REQUESTED:

                    break


                run_device(
                    device
                )


                if STOP_REQUESTED:

                    break


                print()

                print(
                    f"Waiting "
                    f"{RETRY_SECONDS} seconds "
                    f"before retry..."
                )


                for _ in range(
                    RETRY_SECONDS
                ):

                    if STOP_REQUESTED:

                        break

                    time.sleep(1)


            if not active_devices:

                time.sleep(
                    DEVICE_REFRESH_SECONDS
                )


        except Exception as error:

            print()

            print(
                "=" * 70
            )

            print(
                "DEVICE MANAGER ERROR"
            )

            print(
                "=" * 70
            )


            print(
                f"Error: "
                f"{type(error).__name__}"
            )


            print(
                f"Message: "
                f"{error}"
            )


            time.sleep(
                DEVICE_REFRESH_SECONDS
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 70
    )

    print(
        "ZKTeco MULTI DEVICE COLLECTOR"
    )

    print(
        "=" * 70
    )


    print()


    create_table()


    try:

        devices = (
            get_active_devices()
        )

        print(
            f"Configured active devices : "
            f"{len(devices)}"
        )

    except Exception:

        print(
            "Configured active devices : 0"
        )


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


    print()


    try:

        devices = (
            get_active_devices()
        )


        if not devices:

            print(
                "WARNING: No active devices "
                "found in zkt_devices."
            )


            print(
                "Add a device from the Devices page."
            )


    except Exception as error:

        print(
            "Could not read active devices:"
        )

        print(
            error
        )


    print()

    print(
        "=" * 70
    )

    print(
        "DEVICE MANAGER STARTED"
    )

    print(
        "=" * 70
    )


    print()


    device_manager()


    print()

    print(
        "=" * 70
    )

    print(
        "COLLECTOR STOPPED"
    )

    print(
        "=" * 70
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()