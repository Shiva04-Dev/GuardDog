"""
Basic tests for RobotClient command dispatch (dry-run, no hardware needed).
Run with:  python -m pytest tests/ -v
"""

import time
import threading
import pytest
import zmq

from ipc.config import CMD_PORT, TELEMETRY_PORT, EVENT_PORT, HEARTBEAT_PORT
from core.robot_client import RobotClient, COMMAND_HANDLERS
from hardware.motor_controller import MotorController


# ── MotorController dry-run ───────────────────────────────────────────────────

class TestMotorController:
    def setup_method(self):
        self.motor = MotorController(dry_run=True)

    def test_move_clamps_speed(self):
        # Should not raise even with out-of-range speed
        self.motor.move("forward", 1.5)
        self.motor.move("forward", -0.5)

    def test_stop(self):
        self.motor.stop()

    def test_sit_stand(self):
        self.motor.sit()
        self.motor.stand()

    def teardown_method(self):
        self.motor.close()


# ── Command handlers ──────────────────────────────────────────────────────────

class TestCommandHandlers:
    def setup_method(self):
        self.motor = MotorController(dry_run=True)
        self.calls = []
        # Monkey-patch send to capture packets
        original_send = self.motor.send
        def recording_send(cmd_type, msg_id, payload):
            self.calls.append((cmd_type, msg_id, payload))
            original_send(cmd_type, msg_id, payload)
        self.motor.send = recording_send

    def test_move_handler(self):
        COMMAND_HANDLERS["move"](self.motor, {"direction": "forward", "speed": 0.75})
        assert any("Move:Forward:75" in c[2] for c in self.calls)

    def test_stop_handler(self):
        COMMAND_HANDLERS["stop"](self.motor, {})
        assert any("STOP" in c[2] for c in self.calls)

    def test_unknown_action_not_in_handlers(self):
        assert "fly" not in COMMAND_HANDLERS