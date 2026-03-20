"""
MotorController — serial interface to the dog's motor/servo board.

Packet format:  <CMD_TYPE|MSG_ID|PAYLOAD|CHECKSUM>
Example:        <CMD|1|Move:Forward:75|00>

All serial writes go through here. Nothing else should touch the port.
"""

import logging
import threading
import serial
from serial import SerialException

from ipc.config import SERIAL_PORT, SERIAL_BAUD, SERIAL_TIMEOUT, CMD_ID_STOP

log = logging.getLogger(__name__)


class MotorController:
    def __init__(
        self,
        port: str = SERIAL_PORT,
        baud: int = SERIAL_BAUD,
        timeout: float = SERIAL_TIMEOUT,
        dry_run: bool = False,
    ):
        """
        dry_run=True: log packets instead of opening a real serial port.
        Useful for development on a non-robot machine.
        """
        self._lock = threading.Lock()
        self._dry_run = dry_run
        self._ser: serial.Serial | None = None

        if not dry_run:
            try:
                self._ser = serial.Serial(port, baud, timeout=timeout)
                log.info("Serial port %s opened at %d baud", port, baud)
            except SerialException as exc:
                log.error("Failed to open serial port %s: %s", port, exc)
                raise

    # ── Core send ─────────────────────────────────────────────────────────────

    def send(self, cmd_type: str, msg_id: int, payload: str):
        """Build and send a single packet."""
        packet = f"<{cmd_type}|{msg_id}|{payload}|00>"
        with self._lock:
            if self._dry_run:
                log.debug("[DRY RUN] %s", packet)
            else:
                self._ser.write(packet.encode())
                log.debug("Serial TX: %s", packet)

    # ── High-level commands ───────────────────────────────────────────────────

    def move(self, direction: str, speed_norm: float):
        """
        direction : forward | backward | left | right
        speed_norm: 0.0–1.0 (normalised, converted to 0–100)
        """
        speed = max(0, min(100, int(speed_norm * 100)))
        self.send("CMD", CMD_ID_MOVE, f"Move:{direction.capitalize()}:{speed}")

    def turn(self, angle: float):
        """angle: degrees, positive = right"""
        self.send("CMD", 2, f"Turn:{angle:.1f}")

    def sit(self):
        self.send("CMD", 10, "Pose:Sit")

    def stand(self):
        self.send("CMD", 11, "Pose:Stand")

    def stop(self):
        self.send("CMD", CMD_ID_STOP, "STOP")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self):
        if self._ser and self._ser.is_open:
            self.stop()
            self._ser.close()
            log.info("Serial port closed")