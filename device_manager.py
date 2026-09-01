from zk import ZK


def test_device(
    ip_address,
    port,
    password=0
):

    zk = None
    conn = None

    try:

        zk = ZK(
            ip_address,
            port=port,
            timeout=10,
            password=password,
            force_udp=False,
            ommit_ping=False
        )

        conn = zk.connect()

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
            "success": True,
            "firmware": firmware,
            "serial": serial,
            "device_name": device_name,
            "platform": platform,
            "users_count": users_count
        }

    except Exception as error:

        return {
            "success": False,
            "error_type": type(error).__name__,
            "error": str(error)
        }

    finally:

        if conn:

            try:
                conn.disconnect()
            except Exception:
                pass