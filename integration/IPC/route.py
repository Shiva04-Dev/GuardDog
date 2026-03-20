"""
IPCRouter — server-side message router.
Bridges server.py (AI / operator) ↔ robot client over ZMQ.
"""

import logging
import threading
from .message_bus import MessageBus
from .config import TOPIC_COMMAND, TOPIC_TELEMETRY, TOPIC_EVENT

log = logging.getLogger(__name__)


class IPCRouter:
    def __init__(self):
        self.bus = MessageBus(role="server")
        self._handlers: dict[str, list] = {
            TOPIC_TELEMETRY: [],
            TOPIC_EVENT: [],
        }

    def on_telemetry(self, fn):
        """Register a callback for incoming telemetry messages."""
        self._handlers[TOPIC_TELEMETRY].append(fn)
        return fn

    def on_event(self, fn):
        """Register a callback for incoming event messages."""
        self._handlers[TOPIC_EVENT].append(fn)
        return fn

    def send_command(self, cmd: dict):
        """Forward a command dict to the robot."""
        self.bus.publish_command(cmd)
        log.debug("Command sent: %s", cmd)

    def _poll_loop(self):
        while True:
            tel = self.bus.poll_telemetry(timeout_ms=5)
            if tel:
                log.debug("Telemetry: %s", tel)
                for fn in self._handlers[TOPIC_TELEMETRY]:
                    fn(tel)

            evt = self.bus.poll_event(timeout_ms=5)
            if evt:
                log.warning("Event: %s", evt)
                for fn in self._handlers[TOPIC_EVENT]:
                    fn(evt)

    def start(self):
        self.bus.start_heartbeat_thread()
        t = threading.Thread(target=self._poll_loop, daemon=True, name="ipc-router")
        t.start()
        log.info("IPCRouter started")