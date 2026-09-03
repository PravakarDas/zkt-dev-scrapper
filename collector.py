import time
import signal
import sys
import queue
import threading

from datetime import datetime

from zk import ZK

from database import (
    create_table,
    insert_records,
    get_active_devices,
    update_device_online,
    update_attendance_names,
)


# ============================================================
# CONFIGURATION
# ============================================================

RETRY_SECONDS = 5

# Keep 1 minutes for testing.
# Change to 45 after testing.
SAFETY_SYNC_MINUTES = 60

DEVICE_REFRESH_SECONDS = 10


# ============================================================
# PUNCH TYPES
# ============================================================

PUNCH_TYPES = {
    0: "Check In",
    1: "Check Out",
    2: "Break Out",
    3: "Break In",
    4: "Overtime In",
    5: "Overtime Out",
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
    user_map = {}

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

    # --------------------------------------------------------
    # Get employees/users
    # --------------------------------------------------------

    try:

        users = conn.get_users()

        users_count = len(users)

        for user in users:

            user_id = getattr(
                user,
                "user_id",
                None
            )

            if user_id is None:
                continue

            user_id = str(user_id).strip()

            if not user_id:
                continue

            # pyzk normally provides name here
            user_name = getattr(
                user,
                "name",
                None
            )

            if user_name:

                user_name = str(
                    user_name
                ).strip()

            if user_name:

                user_map[user_id] = user_name

    except Exception:
        pass

    return {

        "firmware": firmware,

        "serial": serial,

        "device_name": device_name,

        "platform": platform,

        "users_count": users_count,

        "user_map": user_map,

    }


# ============================================================
# PREPARE ATTENDANCE RECORD
# ============================================================

def prepare_record(
    attendance,
    device,
    device_info
):

    # --------------------------------------------------------
    # IMPORTANT
    #
    # This order MUST match database.py / staging table:
    #
    # device_id
    # branch_name
    # device_ip
    # device_port
    # device_name
    # serial_number
    # firmware
    # platform
    # user_id
    # user_name
    # attendance_time
    # status
    # punch
    # punch_type
    # record_hash
    # --------------------------------------------------------

    user_id = str(
        getattr(
            attendance,
            "user_id",
            ""
        )
    ).strip()

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

    user_map = device_info.get(
        "user_map",
        {}
    )

    user_name = user_map.get(
        user_id
    )

    # --------------------------------------------------------
    # Device ID
    #
    # For ZKTeco devices, serial number is the most reliable
    # unique identifier available from the device.
    # --------------------------------------------------------

    device_id = device_info.get(
        "serial"
    )

    if not device_id:

        device_id = (
            f"{device['ip']}:"
            f"{device['port']}"
        )

    # --------------------------------------------------------
    # Record hash
    #
    # Keep the raw attendance string as the final value.
    # database.py generates/uses the hash if configured there.
    # --------------------------------------------------------

    record_hash = str(
        attendance
    )

    return (

        device_id,

        device["name"],

        device["ip"],

        device["port"],

        device_info.get(
            "device_name"
        ),

        device_info.get(
            "serial"
        ),

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

        record_hash,

    )


# ============================================================
# UPDATE EMPLOYEE NAMES
# ============================================================

def save_employee_names(
    device,
    device_info
):

    user_map = device_info.get(
        "user_map",
        {}
    )

    if not user_map:
        return

    device_id = device_info.get(
        "serial"
    )

    if not device_id:
        device_id = (
            f"{device['ip']}:"
            f"{device['port']}"
        )

    try:

        updated = update_attendance_names(
            device_id,
            user_map
        )

        if updated:

            print(
                f"Employee names updated: "
                f"{updated:,}"
            )

    except Exception as error:

        print(
            "Could not update employee names: "
            f"{error}"
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

        save_employee_names(
            device,
            device_info
        )

        return True

    # --------------------------------------------------------
    # Prepare records
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

    # --------------------------------------------------------
    # Update names
    # --------------------------------------------------------

    save_employee_names(
        device,
        device_info
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

    return True


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
        f"Name     : "
        f"{device_info.get('user_map', {}).get(
            str(getattr(attendance, 'user_id', '')),
            ''
        )}"
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
        f"Branch : "
        f"{device['name']}"
    )

    print(
        f"Device : "
        f"{device['ip']}:{device['port']}"
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

    last_event = time.time()

    # --------------------------------------------------------
    # live_capture() is a blocking generator.
    #
    # We run it in a separate thread so that the main
    # monitoring loop can enforce the safety timeout.
    # --------------------------------------------------------

    event_queue = queue.Queue()

    capture_stop = threading.Event()

    def capture_worker():

        try:

            for attendance in conn.live_capture():

                if capture_stop.is_set():
                    break

                if attendance is None:
                    continue

                event_queue.put(
                    (
                        "attendance",
                        attendance
                    )
                )

        except Exception as error:

            event_queue.put(
                (
                    "error",
                    error
                )
            )

    capture_thread = threading.Thread(
        target=capture_worker,
        daemon=True
    )

    capture_thread.start()

    try:

        while not STOP_REQUESTED:

            # ------------------------------------------------
            # Check for live event
            # ------------------------------------------------

            try:

                event_type, value = (
                    event_queue.get(
                        timeout=1
                    )
                )

            except queue.Empty:

                event_type = None
                value = None

            if event_type == "attendance":

                save_live_record(
                    value,
                    device,
                    device_info
                )

                last_event = time.time()

                print()
                print(
                    "Live event received. "
                    "Safety timer reset."
                )

            elif event_type == "error":

                raise value

            # ------------------------------------------------
            # SAFETY TIMEOUT
            # ------------------------------------------------

            elapsed_minutes = (
                time.time()
                - last_event
            ) / 60

            if (
                elapsed_minutes
                >= SAFETY_SYNC_MINUTES
            ):

                print()
                print("=" * 70)
                print(
                    "SAFETY SYNC TRIGGERED"
                )
                print("=" * 70)

                print(
                    f"No live event for "
                    f"{elapsed_minutes:.1f} minutes."
                )

                print(
                    "Stopping live monitor..."
                )

                return "resync"

        return "stop"

    finally:

        capture_stop.set()


# ============================================================
# CONNECT + RUN ONE DEVICE
# ============================================================

def run_device(device):

    while not STOP_REQUESTED:

        conn = None

        try:

            print()
            print("=" * 70)
            print(
                f"DEVICE - "
                f"{device['name']}"
            )
            print("=" * 70)

            print()
            print(
                f"Connecting to "
                f"{device['ip']}:{device['port']}"
            )

            zk = ZK(
                device["ip"],
                port=int(device["port"]),
                timeout=10,
                password=device.get(
                    "password",
                    0
                ),
                force_udp=False,
                ommit_ping=False
            )

            conn = zk.connect()

            print()
            print(
                f"CONNECTED: "
                f"{device['ip']}:{device['port']}"
            )

            # ------------------------------------------------
            # Device information
            # ------------------------------------------------

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
                f"{device_info.get('users_count', 0)}"
            )

            # ------------------------------------------------
            # Update device information in DB
            # ------------------------------------------------

            device_id = device_info.get(
                "serial"
            )

            if not device_id:

                device_id = (
                    f"{device['ip']}:"
                    f"{device['port']}"
                )

            try:

                update_device_online(
                    device_id,
                    device_info.get(
                        "device_name"
                    ),
                    device_info.get(
                        "serial"
                    ),
                    device_info.get(
                        "firmware"
                    ),
                    device_info.get(
                        "platform"
                    )
                )

            except Exception as error:

                print(
                    "Warning: Could not update "
                    f"device status: {error}"
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

            result = live_monitor(
                conn,
                device,
                device_info
            )

            if result == "stop":

                break

            # ------------------------------------------------
            # Safety sync requested
            #
            # We disconnect and reconnect before doing the
            # next full sync. This gives us a fresh connection.
            # ------------------------------------------------

            if result == "resync":

                print()
                print(
                    "Preparing for safety full sync..."
                )

                try:
                    conn.disconnect()
                except Exception:
                    pass

                conn = None

                time.sleep(1)

                continue

        except KeyboardInterrupt:

            break

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
                "Device is offline or connection "
                "was lost."
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

        if not STOP_REQUESTED:

            print()
            print(
                f"Reconnecting "
                f"{device['name']} "
                f"in {RETRY_SECONDS} seconds..."
            )

            for _ in range(
                RETRY_SECONDS
            ):

                if STOP_REQUESTED:
                    break

                time.sleep(1)


# ============================================================
# DEVICE MANAGER
# ============================================================

def device_manager():

    running_devices = {}

    print()
    print("=" * 70)
    print("ZKTeco MULTI DEVICE COLLECTOR")
    print("=" * 70)

    print()
    print(
        "Database initialized."
    )

    while not STOP_REQUESTED:

        try:

            active_devices = get_active_devices()

        except Exception as error:

            print()
            print(
                "Could not load active devices:"
            )

            print(error)

            time.sleep(
                DEVICE_REFRESH_SECONDS
            )

            continue

        if not active_devices:

            if not running_devices:

                print()
                print(
                    "WARNING: No active devices "
                    "found in zkt_devices."
                )

                print(
                    "Add a device from the "
                    "Devices page."
                )

                print()

        for db_device in active_devices:

            device_id = db_device[
                "device_id"
            ]

            if device_id in running_devices:

                continue

            device = {

                "name": db_device[
                    "branch_name"
                ],

                "ip": db_device[
                    "ip_address"
                ],

                "port": db_device[
                    "port"
                ],

                "password": 0,

            }

            print()
            print("=" * 70)
            print(
                "NEW ACTIVE DEVICE DETECTED"
            )
            print(
                f"Branch : "
                f"{device['name']}"
            )
            print(
                f"Device : "
                f"{device['ip']}:{device['port']}"
            )
            print("=" * 70)

            thread = threading.Thread(
                target=run_device,
                args=(device,),
                daemon=True
            )

            thread.start()

            running_devices[
                device_id
            ] = thread

        # ----------------------------------------------------
        # Remove inactive devices from manager tracking.
        #
        # The actual device thread will finish on its own
        # after its current retry cycle.
        # ----------------------------------------------------

        active_ids = {
            device["device_id"]
            for device in active_devices
        }

        for device_id in list(
            running_devices.keys()
        ):

            if device_id not in active_ids:

                print()
                print(
                    f"Device {device_id} "
                    f"is no longer active."
                )

                del running_devices[
                    device_id
                ]

        # ----------------------------------------------------
        # Wait before checking device list again.
        # ----------------------------------------------------

        for _ in range(
            DEVICE_REFRESH_SECONDS
        ):

            if STOP_REQUESTED:
                break

            time.sleep(1)

    print()
    print(
        "Device manager stopped."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("ZKTeco MULTI DEVICE COLLECTOR")
    print("=" * 70)

    try:

        create_table()

    except Exception as error:

        print()
        print(
            "Database initialization failed:"
        )

        print(error)

        sys.exit(1)

    print()
    print(
        "Device retry interval     : "
        f"{RETRY_SECONDS} seconds"
    )

    print(
        "Device refresh interval   : "
        f"{DEVICE_REFRESH_SECONDS} seconds"
    )

    print(
        "Safety full sync          : "
        f"{SAFETY_SYNC_MINUTES} minutes"
    )

    print()
    print("=" * 70)
    print("DEVICE MANAGER STARTED")
    print("=" * 70)

    try:

        device_manager()

    except KeyboardInterrupt:

        pass

    finally:

        print()
        print(
            "Collector stopped."
        )


if __name__ == "__main__":

    main()