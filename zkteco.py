from zk import ZK


class ZKTecoDevice:

    def __init__(self, ip, port, timeout=10):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.conn = None

    # ========================================================
    # CONNECT
    # ========================================================

    def connect(self):

        zk = ZK(
            self.ip,
            port=self.port,
            timeout=self.timeout,
            password=0,
            force_udp=False,
            ommit_ping=True,
        )

        self.conn = zk.connect()

        return self.conn

    # ========================================================
    # DISCONNECT
    # ========================================================

    def disconnect(self):

        if self.conn:

            try:
                self.conn.disconnect()
            except Exception:
                pass

            self.conn = None

    # ========================================================
    # DEVICE INFORMATION
    # ========================================================

    def get_device_info(self):

        if not self.conn:
            raise RuntimeError("Device not connected")

        return {
            "serial": self.conn.get_serialnumber(),
            "firmware": self.conn.get_firmware_version(),
            "device_name": self.conn.get_device_name(),
            "platform": self.conn.get_platform(),
        }

    # ========================================================
    # USERS
    # ========================================================

    def get_users(self):

        if not self.conn:
            raise RuntimeError("Device not connected")

        return self.conn.get_users()

    # ========================================================
    # ATTENDANCE
    # ========================================================

    def get_attendance(self):

        if not self.conn:
            raise RuntimeError("Device not connected")

        return self.conn.get_attendance()

    # ========================================================
    # LIVE CAPTURE
    # ========================================================

    def live_capture(self, callback):

        if not self.conn:
            raise RuntimeError("Device not connected")

        return self.conn.live_capture(
            callback=callback,
            timeout=60,
        )