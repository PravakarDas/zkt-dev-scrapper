from zk import ZK
import csv
import os
from datetime import datetime


# ============================================================
# ZKTeco Device Configuration
# ============================================================

DEVICE_IP = "119.10.168.198"
DEVICE_PORT = 1111

# CSV file name
CSV_FILE = "attendance_records.csv"


# ============================================================
# Connect to ZKTeco device
# ============================================================

def connect_device():
    print("=" * 70)
    print("ZKTECO ATTENDANCE CSV EXPORT")
    print("=" * 70)

    print(f"Connecting to {DEVICE_IP}:{DEVICE_PORT}...")

    zk = ZK(
        DEVICE_IP,
        port=DEVICE_PORT,
        timeout=30,
        password=0,
        force_udp=False,
        ommit_ping=True
    )

    try:
        conn = zk.connect()

        print("CONNECTED!")
        print()

        return conn

    except Exception as e:
        print()
        print("ERROR connecting to device")
        print(type(e).__name__, ":", e)

        return None


# ============================================================
# Main
# ============================================================

def main():

    conn = None

    try:

        # ----------------------------------------------------
        # Connect
        # ----------------------------------------------------

        conn = connect_device()

        if conn is None:
            return

        # ----------------------------------------------------
        # Device information
        # ----------------------------------------------------

        print("Device Information")
        print("-" * 70)

        try:
            print("Firmware :", conn.get_firmware_version())
        except Exception:
            print("Firmware : Unable to read")

        try:
            print("Serial   :", conn.get_serialnumber())
        except Exception:
            print("Serial   : Unable to read")

        try:
            print("Device   :", conn.get_device_name())
        except Exception:
            print("Device   : Unable to read")

        try:
            print("Platform :", conn.get_platform())
        except Exception:
            print("Platform : Unable to read")

        print()

        # ----------------------------------------------------
        # Read attendance records
        # ----------------------------------------------------

        print("Reading attendance records...")
        print("-" * 70)

        attendances = conn.get_attendance()

        if attendances is None:
            print("No attendance records found.")
            return

        print(f"Total records: {len(attendances)}")
        print()

        # ----------------------------------------------------
        # CSV headers
        # ----------------------------------------------------

        fieldnames = [
            "record_number",
            "user_id",
            "timestamp",
            "status",
            "punch",
            "punch_type",
            "uid",
            "raw_record"
        ]

        # ----------------------------------------------------
        # Write CSV
        # ----------------------------------------------------

        with open(
            CSV_FILE,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as csvfile:

            writer = csv.DictWriter(
                csvfile,
                fieldnames=fieldnames
            )

            writer.writeheader()

            for index, attendance in enumerate(attendances, start=1):

                # --------------------------------------------
                # Get values safely
                # --------------------------------------------

                user_id = getattr(
                    attendance,
                    "user_id",
                    ""
                )

                timestamp = getattr(
                    attendance,
                    "timestamp",
                    ""
                )

                status = getattr(
                    attendance,
                    "status",
                    ""
                )

                punch = getattr(
                    attendance,
                    "punch",
                    ""
                )

                uid = getattr(
                    attendance,
                    "uid",
                    ""
                )

                # --------------------------------------------
                # Convert timestamp
                # --------------------------------------------

                if isinstance(timestamp, datetime):
                    timestamp_value = timestamp.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                else:
                    timestamp_value = str(timestamp)

                # --------------------------------------------
                # Punch type
                # --------------------------------------------

                punch_types = {
                    0: "Check In",
                    1: "Check Out",
                    2: "Break In",
                    3: "Break Out",
                    4: "Overtime In",
                    5: "Out"
                }

                try:
                    punch_number = int(punch)
                except (ValueError, TypeError):
                    punch_number = None

                punch_type = punch_types.get(
                    punch_number,
                    f"Unknown ({punch})"
                )

                # --------------------------------------------
                # Write row
                # --------------------------------------------

                writer.writerow({
                    "record_number": index,
                    "user_id": user_id,
                    "timestamp": timestamp_value,
                    "status": status,
                    "punch": punch,
                    "punch_type": punch_type,
                    "uid": uid,
                    "raw_record": str(attendance)
                })

        # ----------------------------------------------------
        # Finished
        # ----------------------------------------------------

        print("=" * 70)
        print("SUCCESS!")
        print("=" * 70)

        print()
        print(f"CSV file created: {CSV_FILE}")

        # Absolute path
        absolute_path = os.path.abspath(CSV_FILE)

        print(f"Full path: {absolute_path}")

        print()
        print("Records exported:", len(attendances))

    except KeyboardInterrupt:

        print()
        print("Stopped by user.")

    except Exception as e:

        print()
        print("=" * 70)
        print("ERROR")
        print("=" * 70)

        print(type(e).__name__, ":", e)

    finally:

        # ----------------------------------------------------
        # Disconnect
        # ----------------------------------------------------

        if conn:

            try:
                conn.disconnect()
                print()
                print("Disconnected.")

            except Exception:
                pass


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    main()
