"""
One-off helper: register one or more devices without going through the
web UI. Used by deploy.sh (via `docker compose run`), but works standalone
too:

    python3 seed_devices.py "CTG Office,119.10.168.198,1111;Chapai Office,118.179.113.115,8121"

Format: devices separated by ";", each one "Branch Name,ip,port".

Reuses the exact same connect-then-save flow as the "Add Device" form
(device_manager.test_device + database.add_device) - a device already
registered at that IP/port is skipped, not duplicated, so this is safe
to run again (e.g. on every deploy.sh run) without side effects.
"""

import sys

from database import get_device_by_ip, add_device
from device_manager import test_device


def parse_devices(spec):

    devices = []

    for raw_entry in spec.split(";"):

        raw_entry = raw_entry.strip()

        if not raw_entry:
            continue

        parts = [p.strip() for p in raw_entry.split(",")]

        if len(parts) != 3:

            raise ValueError(
                f"invalid device entry {raw_entry!r} - "
                f"expected 'Branch Name,ip,port'"
            )

        branch_name, ip_address, port_str = parts

        if not branch_name or not ip_address:

            raise ValueError(
                f"invalid device entry {raw_entry!r} - "
                f"branch name and ip are required"
            )

        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(
                f"invalid port in entry {raw_entry!r}: {port_str!r}"
            )

        devices.append((branch_name, ip_address, port))

    return devices


def seed_device(branch_name, ip_address, port):

    print(f"--- {branch_name} ({ip_address}:{port}) ---")

    existing = get_device_by_ip(ip_address, port)

    if existing:

        print(
            f"Already registered "
            f"(device_id={existing['device_id']}) - skipping."
        )

        return "skipped"

    result = test_device(ip_address, port)

    if not result["success"]:

        print(f"Could not connect: {result.get('error')}")

        return "failed"

    serial = result.get("serial")

    if not serial:

        print("Connected, but no serial number was returned - skipping.")

        return "failed"

    device = add_device(
        device_id=serial.strip(),
        branch_name=branch_name,
        ip_address=ip_address,
        port=port,
        device_name=result.get("device_name"),
        serial_number=serial,
        firmware=result.get("firmware"),
        platform=result.get("platform"),
    )

    print(f"Added: device_id={device['device_id']}, serial={serial}")

    return "added"


def main():

    if len(sys.argv) < 2 or not sys.argv[1].strip():

        print(
            "Usage: python3 seed_devices.py "
            "'Branch Name,ip,port;Branch Name,ip,port'"
        )

        sys.exit(1)

    try:
        devices = parse_devices(sys.argv[1])
    except ValueError as error:
        print(f"DEVICES value is malformed: {error}")
        sys.exit(1)

    if not devices:
        print("No devices to add.")
        return

    print()
    print("=" * 60)
    print("SEEDING DEVICES")
    print("=" * 60)
    print()

    results = {"added": 0, "skipped": 0, "failed": 0}

    for branch_name, ip_address, port in devices:

        outcome = seed_device(branch_name, ip_address, port)
        results[outcome] += 1

        print()

    print("=" * 60)
    print(
        f"Done: {results['added']} added, "
        f"{results['skipped']} already registered, "
        f"{results['failed']} failed"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
