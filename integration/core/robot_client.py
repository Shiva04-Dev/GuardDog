"""
RobotClient — the single on-robot process.

Replaces both the old bridge.py (ZMQ SUB → serial) and robot.py (ZMQ REQ → serial).

Responsibilities
────────────────
  • Subscribe to commands from the server via ZMQ PUB/SUB
  • Dispatch commands to the MotorController
  • Push telemetry to the server at ~20 Hz
  • Push events (detections, errors, battery alerts)
  • Monitor the heartbeat; trigger a safe-stop if the server goes silent

Usage
─────
    python -m core.robot_client                  # real hardware
    python -m core.robot_client --dry-run        # no serial port needed
    python -m core.robot_client --server 192.168.1.10  # remote server
"""

import argparse
import logging
import signal
import sys
import time

import zmq

from hardware.motor_controller import MotorController
from ipc.config import (
    CMD_PORT, TELEMETRY_PORT, EVENT_PORT, HEARTBEAT_PORT,
    HEARTBEAT_TIMEOUT, TELEMETRY_INTERVAL, POLL_TIMEOUT_MS,
)

log = logging.getLogger("robot_client")


# ── Command dispatch table ────────────────────────────────────────────────────

def _handle_move(motor: MotorController, data: dict):
    direction = data.get("direction", "forward")
    speed     = float(data.get("speed", 0.5))
    motor.move(direction, speed)

def _handle_turn(motor: MotorController, data: dict):
    angle = float(data.get("angle", 0))
    motor.turn(angle)

def _handle_stop(motor: MotorController, _data: dict):
    motor.stop()

def _handle_sit(motor: MotorController, _data: dict):
    motor.sit()

def _handle_stand(motor: MotorController, _data: dict):
    motor.stand()

COMMAND_HANDLERS = {
    "move":   _handle_move,
    "turn":   _handle_turn,
    "stop":   _handle_stop,
    "sit":    _handle_sit,
    "stand":  _handle_stand,
}


# ── Telemetry helpers ─────────────────────────────────────────────────────────

def _collect_telemetry() -> dict:
    """
    Build a telemetry snapshot. Extend with real sensor reads (IMU, battery ADC,
    CPU usage, obstacle sensor) as hardware becomes available.
    """
    return {
        "type":        "telemetry",
        "timestamp":   time.time(),
        "status":      "OK",
        "battery":     _read_battery_pct(),
        "cpu_usage":   _read_cpu(),
        "temperature": _read_temperature(),
        "sensors": {
            "obstacle_distance": None,
            "imu_pitch":         None,
            "imu_roll":          None,
            "imu_yaw":           None,
        },
    }


def _read_battery_pct() -> float | None:
    """Stub — replace with real ADC read."""
    return None


def _read_cpu() -> float | None:
    try:
        import psutil
        return psutil.cpu_percent(interval=None)
    except ImportError:
        return None


def _read_temperature() -> float | None:
    try:
        import psutil
        temps = psutil.sensors_temperatures()
        if temps:
            first = next(iter(temps.values()))
            return first[0].current if first else None
    except Exception:
        return None


# ── Main client loop ──────────────────────────────────────────────────────────

class RobotClient:
    def __init__(self, server: str = "localhost", dry_run: bool = False):
        self.server   = server
        self.dry_run  = dry_run
        self._running = False

        # Hardware
        self.motor = MotorController(dry_run=dry_run)

        # ZMQ
        self._ctx      = zmq.Context.instance()
        self._cmd_sub  = self._ctx.socket(zmq.SUB)
        self._tel_push = self._ctx.socket(zmq.PUSH)
        self._evt_push = self._ctx.socket(zmq.PUSH)
        self._hb_sub   = self._ctx.socket(zmq.SUB)

        self._cmd_sub.connect(f"tcp://{server}:{CMD_PORT}")
        self._cmd_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        self._tel_push.connect(f"tcp://{server}:{TELEMETRY_PORT}")
        self._evt_push.connect(f"tcp://{server}:{EVENT_PORT}")

        self._hb_sub.connect(f"tcp://{server}:{HEARTBEAT_PORT}")
        self._hb_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        self._last_heartbeat = time.monotonic()
        self._last_command   = time.monotonic()

        log.info("RobotClient connected to server=%s (dry_run=%s)", server, dry_run)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _push_telemetry(self):
        try:
            self._tel_push.send_json(_collect_telemetry(), zmq.NOBLOCK)
        except zmq.ZMQError as exc:
            log.warning("Telemetry push failed: %s", exc)

    def _push_event(self, event: str, severity: str = "info", data: dict | None = None):
        try:
            self._evt_push.send_json({
                "type":      "event",
                "event":     event,
                "severity":  severity,
                "timestamp": time.time(),
                "source":    "robot_client",
                "data":      data or {},
            }, zmq.NOBLOCK)
        except zmq.ZMQError as exc:
            log.warning("Event push failed: %s", exc)

    def _check_heartbeat(self) -> bool:
        """Drain all pending heartbeat frames, update timestamp."""
        while self._hb_sub.poll(0):
            self._hb_sub.recv_json()
            self._last_heartbeat = time.monotonic()
        return (time.monotonic() - self._last_heartbeat) < HEARTBEAT_TIMEOUT

    def _dispatch_command(self, msg: dict):
        if msg.get("type") != "command":
            return
        data   = msg.get("data", {})
        action = data.get("action", "")
        handler = COMMAND_HANDLERS.get(action)
        if handler:
            log.info("Command: %s", action)
            handler(self.motor, data)
            self._last_command = time.monotonic()
        else:
            log.warning("Unknown action: %s", action)
            self._push_event("system_error", "warning", {"detail": f"unknown action '{action}'"})

    # ── Run loop ──────────────────────────────────────────────────────────────

    def run(self):
        self._running = True
        log.info("RobotClient loop started")
        last_tel_time = 0.0

        try:
            while self._running:
                now = time.monotonic()

                # 1. Check heartbeat — safe-stop if server silent
                if not self._check_heartbeat():
                    log.warning("Heartbeat lost — issuing safe stop")
                    self.motor.stop()
                    self._push_event("system_error", "critical", {"detail": "heartbeat timeout"})

                # 2. Drain pending commands
                while self._cmd_sub.poll(POLL_TIMEOUT_MS):
                    try:
                        msg = self._cmd_sub.recv_json()
                        self._dispatch_command(msg)
                    except Exception as exc:
                        log.error("Command handling error: %s", exc)
                        self._push_event("system_error", "warning", {"detail": str(exc)})

                # 3. Push telemetry at configured rate
                if now - last_tel_time >= TELEMETRY_INTERVAL:
                    self._push_telemetry()
                    last_tel_time = now

        except KeyboardInterrupt:
            log.info("Interrupted")
        finally:
            self.shutdown()

    def shutdown(self):
        log.info("Shutting down RobotClient")
        self._running = False
        self.motor.stop()
        self.motor.close()
        for sock in (self._cmd_sub, self._tel_push, self._evt_push, self._hb_sub):
            sock.close(linger=0)
        self._ctx.term()


# ── Entry point ───────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(name)-20s %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(description="Robot Dog client process")
    parser.add_argument("--server",   default="localhost", help="Server hostname/IP")
    parser.add_argument("--dry-run",  action="store_true",  help="Skip serial port (dev mode)")
    parser.add_argument("--verbose",  action="store_true",  help="Debug logging")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    client = RobotClient(server=args.server, dry_run=args.dry_run)

    # Graceful shutdown on SIGTERM (systemd, Docker)
    signal.signal(signal.SIGTERM, lambda *_: client.shutdown() or sys.exit(0))

    client.run()


if __name__ == "__main__":
    main()