"""
robot_client.py — Pi-side command receiver and telemetry sender.

Flow:
  Server publishes commands → Pi SUBs and dispatches to MotorController
  Pi PUSHes telemetry → Server PULLs and forwards to Backend via WebSocket

Usage:
    python -m pi.core.robot_client --server 192.168.1.10
    python -m pi.core.robot_client --dry-run
"""

import argparse
import logging
import signal
import sys
import time

import zmq

from pi.hardware.motor_controller import MotorController
from pi.ipc.config import (
    CMD_PORT, TELEMETRY_PORT, EVENT_PORT, HEARTBEAT_PORT,
    HEARTBEAT_TIMEOUT, TELEMETRY_INTERVAL, POLL_TIMEOUT_MS,
)

log = logging.getLogger("robot_client")


# ── Command dispatch ──────────────────────────────────────────────────────────

def _do_move(motor, data):
    motor.move(data.get("direction", "forward"), float(data.get("speed", 0.5)))

def _do_turn(motor, data):
    motor.turn(float(data.get("angle", 0)))

def _do_stop(motor, _):
    motor.stop()

def _do_sit(motor, _):
    motor.sit()

def _do_stand(motor, _):
    motor.stand()

HANDLERS = {
    "move":  _do_move,
    "turn":  _do_turn,
    "stop":  _do_stop,
    "sit":   _do_sit,
    "stand": _do_stand,
}


# ── Telemetry collection ──────────────────────────────────────────────────────

def _collect_telemetry() -> dict:
    tel = {
        "type":      "telemetry",
        "timestamp": time.time(),
        "status":    "OK",
        "battery":   _read_battery(),
        "cpu_temp":  _read_cpu_temp(),
    }
    return tel


def _read_battery() -> float | None:
    # TODO: read from ADC
    return None


def _read_cpu_temp() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read()) / 1000, 1)
    except Exception:
        return None


# ── Robot client ──────────────────────────────────────────────────────────────

class RobotClient:
    def __init__(self, server="localhost", dry_run=False):
        self.motor   = MotorController(dry_run=dry_run)
        self._ctx    = zmq.Context.instance()
        self._running = False

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

        self._last_hb = time.monotonic()
        log.info("Connected to server=%s (dry_run=%s)", server, dry_run)

    def _check_heartbeat(self) -> bool:
        while self._hb_sub.poll(0):
            self._hb_sub.recv_json()
            self._last_hb = time.monotonic()
        return (time.monotonic() - self._last_hb) < HEARTBEAT_TIMEOUT

    def _push_telemetry(self):
        try:
            self._tel_push.send_json(_collect_telemetry(), zmq.NOBLOCK)
        except zmq.ZMQError:
            pass

    def _push_event(self, event: str, severity="info", data=None):
        try:
            self._evt_push.send_json({
                "type": "event", "event": event,
                "severity": severity, "timestamp": time.time(),
                "source": "robot_client", "data": data or {},
            }, zmq.NOBLOCK)
        except zmq.ZMQError:
            pass

    def _dispatch(self, msg: dict):
        if msg.get("type") != "command":
            return
        data   = msg.get("data", {})
        action = data.get("action", "")
        fn = HANDLERS.get(action)
        if fn:
            log.info("Command: %s", action)
            fn(self.motor, data)
        else:
            log.warning("Unknown action: %s", action)

    def run(self):
        self._running = True
        last_tel = 0.0
        log.info("Robot client running")

        try:
            while self._running:
                now = time.monotonic()

                if not self._check_heartbeat():
                    log.warning("Heartbeat lost — safe stop")
                    self.motor.stop()
                    self._push_event("system_error", "critical",
                                     {"detail": "heartbeat timeout"})

                while self._cmd_sub.poll(POLL_TIMEOUT_MS):
                    try:
                        self._dispatch(self._cmd_sub.recv_json())
                    except Exception as e:
                        log.error("Dispatch error: %s", e)

                if now - last_tel >= TELEMETRY_INTERVAL:
                    self._push_telemetry()
                    last_tel = now

        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self):
        self._running = False
        self.motor.stop()
        self.motor.close()
        for s in (self._cmd_sub, self._tel_push, self._evt_push, self._hb_sub):
            s.close(linger=0)
        self._ctx.term()
        log.info("Robot client shut down")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server",  default="localhost")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(name)-20s %(levelname)-8s  %(message)s",
    )

    client = RobotClient(server=args.server, dry_run=args.dry_run)
    signal.signal(signal.SIGTERM, lambda *_: client.shutdown() or sys.exit(0))
    client.run()


if __name__ == "__main__":
    main()