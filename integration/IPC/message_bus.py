"""
MessageBus — single interface for all ZeroMQ communication.

Server role  : binds sockets, publishes commands, receives telemetry/events.
Client role  : connects sockets, subscribes to commands, pushes telemetry/events.
"""

import time
import threading
import logging
import zmq

from .config import (
    CMD_PORT, TELEMETRY_PORT, EVENT_PORT, HEARTBEAT_PORT,
    TOPIC_COMMAND, TOPIC_TELEMETRY, TOPIC_EVENT, TOPIC_HEARTBEAT,
    HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT, POLL_TIMEOUT_MS,
)

log = logging.getLogger(__name__)


class MessageBus:
    def __init__(self, role: str = "client"):
        """
        role: 'server' binds sockets | 'client' connects to them
        """
        assert role in ("server", "client"), "role must be 'server' or 'client'"
        self.role = role
        self._ctx = zmq.Context.instance()
        self._lock = threading.Lock()
        self._last_heartbeat = time.monotonic()
        self._running = False

        self._cmd_pub:  zmq.Socket | None = None   # server publishes commands
        self._cmd_sub:  zmq.Socket | None = None   # client subscribes to commands
        self._tel_push: zmq.Socket | None = None   # client pushes telemetry
        self._tel_pull: zmq.Socket | None = None   # server pulls telemetry
        self._evt_push: zmq.Socket | None = None   # client pushes events
        self._evt_pull: zmq.Socket | None = None   # server pulls events
        self._hb_pub:   zmq.Socket | None = None   # server publishes heartbeats
        self._hb_sub:   zmq.Socket | None = None   # client subscribes to heartbeats

        self._setup_sockets()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_sockets(self):
        is_server = self.role == "server"

        # Commands: PUB (server) / SUB (client)
        self._cmd_pub = self._ctx.socket(zmq.PUB)
        self._cmd_sub = self._ctx.socket(zmq.SUB)
        self._cmd_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        addr = f"tcp://*:{CMD_PORT}" if is_server else f"tcp://localhost:{CMD_PORT}"
        if is_server:
            self._cmd_pub.bind(f"tcp://*:{CMD_PORT}")
            self._cmd_sub.connect(f"tcp://localhost:{CMD_PORT}")
        else:
            self._cmd_sub.connect(f"tcp://localhost:{CMD_PORT}")

        # Telemetry: PUSH (client) / PULL (server)
        self._tel_push = self._ctx.socket(zmq.PUSH)
        self._tel_pull = self._ctx.socket(zmq.PULL)
        if is_server:
            self._tel_pull.bind(f"tcp://*:{TELEMETRY_PORT}")
        else:
            self._tel_push.connect(f"tcp://localhost:{TELEMETRY_PORT}")

        # Events: PUSH (client) / PULL (server)
        self._evt_push = self._ctx.socket(zmq.PUSH)
        self._evt_pull = self._ctx.socket(zmq.PULL)
        if is_server:
            self._evt_pull.bind(f"tcp://*:{EVENT_PORT}")
        else:
            self._evt_push.connect(f"tcp://localhost:{EVENT_PORT}")

        # Heartbeat: PUB (server) / SUB (client)
        self._hb_pub = self._ctx.socket(zmq.PUB)
        self._hb_sub = self._ctx.socket(zmq.SUB)
        self._hb_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        if is_server:
            self._hb_pub.bind(f"tcp://*:{HEARTBEAT_PORT}")
        else:
            self._hb_sub.connect(f"tcp://localhost:{HEARTBEAT_PORT}")

        log.info("MessageBus sockets initialised (role=%s)", self.role)

    # ── Commands ──────────────────────────────────────────────────────────────

    def publish_command(self, cmd: dict):
        """Server: publish a command to all connected clients."""
        with self._lock:
            self._cmd_pub.send_json(cmd)

    def poll_command(self, timeout_ms: int = POLL_TIMEOUT_MS) -> dict | None:
        """Client: non-blocking poll for a new command. Returns None if none ready."""
        if self._cmd_sub.poll(timeout_ms):
            return self._cmd_sub.recv_json()
        return None

    # ── Telemetry / Events ────────────────────────────────────────────────────

    def push_telemetry(self, data: dict):
        """Client: push telemetry to server."""
        with self._lock:
            self._tel_push.send_json(data)

    def push_event(self, event: dict):
        """Client: push event to server."""
        with self._lock:
            self._evt_push.send_json(event)

    def poll_telemetry(self, timeout_ms: int = 0) -> dict | None:
        """Server: non-blocking poll for telemetry."""
        if self._tel_pull.poll(timeout_ms):
            return self._tel_pull.recv_json()
        return None

    def poll_event(self, timeout_ms: int = 0) -> dict | None:
        """Server: non-blocking poll for events."""
        if self._evt_pull.poll(timeout_ms):
            return self._evt_pull.recv_json()
        return None

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def send_heartbeat(self):
        """Server: publish a heartbeat tick."""
        with self._lock:
            self._hb_pub.send_json({
                "type": TOPIC_HEARTBEAT,
                "timestamp": time.time(),
            })

    def check_heartbeat(self, timeout: float = HEARTBEAT_TIMEOUT) -> bool:
        """Client: True if a heartbeat arrived within `timeout` seconds."""
        if self.role == "server":
            return True
        if self._hb_sub.poll(0):
            self._hb_sub.recv_json()
            self._last_heartbeat = time.monotonic()
        return (time.monotonic() - self._last_heartbeat) < timeout

    def start_heartbeat_thread(self):
        """Server: start background thread that ticks heartbeat every interval."""
        self._running = True

        def _tick():
            while self._running:
                self.send_heartbeat()
                time.sleep(HEARTBEAT_INTERVAL)

        t = threading.Thread(target=_tick, daemon=True, name="heartbeat")
        t.start()
        log.info("Heartbeat thread started (interval=%.1fs)", HEARTBEAT_INTERVAL)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self):
        self._running = False
        for sock in (
            self._cmd_pub, self._cmd_sub,
            self._tel_push, self._tel_pull,
            self._evt_push, self._evt_pull,
            self._hb_pub, self._hb_sub,
        ):
            if sock:
                sock.close(linger=0)
        log.info("MessageBus closed")