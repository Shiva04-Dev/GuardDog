"""
MotorController — serial interface to the motor/servo board.
Packet format: <CMD_TYPE|MSG_ID|PAYLOAD|00>
"""

import logging
import threading
import serial
from serial import SerialException
from pi.ipc.config import SERIAL_PORT, SERIAL_BAUD

log = logging.getLogger(__name__)


class MotorController:
    def __init__(self, port=SERIAL_PORT, baud=SERIAL_BAUD, dry_run=False):
        self._lock = threading.Lock()
        self._dry_run = dry_run
        self._ser = None

        if not dry_run:
            try:
                self._ser = serial.Serial(port, baud, timeout=1)
                log.info("Serial port %s opened", port)
            except SerialException as e:
                log.error("Failed to open serial port: %s", e)
                raise

    def send(self, cmd_type: str, msg_id: int, payload: str):
        packet = f"<{cmd_type}|{msg_id}|{payload}|00>"
        with self._lock:
            if self._dry_run:
                log.debug("[DRY RUN] %s", packet)
            else:
                self._ser.write(packet.encode())
                log.debug("TX: %s", packet)

    def move(self, direction: str, speed: float):
        spd = max(0, min(100, int(speed * 100)))
        self.send("CMD", 1, f"Move:{direction.capitalize()}:{spd}")

    def turn(self, angle: float):
        self.send("CMD", 2, f"Turn:{angle:.1f}")

    def sit(self):
        self.send("CMD", 10, "Pose:Sit")

    def stand(self):
        self.send("CMD", 11, "Pose:Stand")

    def stop(self):
        self.send("CMD", 99, "STOP")

    def close(self):
        self.stop()
        if self._ser and self._ser.is_open:
            self._ser.close()