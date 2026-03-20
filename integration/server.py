"""
server.py — command source / AI brain.

Publishes commands to connected robot clients, receives telemetry and events.
Replace the example loop with your real AI / operator interface.

Usage
─────
    python server.py
    python server.py --verbose
"""

import argparse
import logging
import signal
import sys
import time

from ipc.router import IPCRouter
from ipc.config import TOPIC_TELEMETRY, TOPIC_EVENT

log = logging.getLogger("server")


def main():
    parser = argparse.ArgumentParser(description="Robot Dog server")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(name)-20s %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    router = IPCRouter()

    @router.on_telemetry
    def handle_tel(msg):
        log.debug("TEL  battery=%(battery)s  status=%(status)s", msg)

    @router.on_event
    def handle_evt(msg):
        log.warning("EVT  event=%(event)s  severity=%(severity)s", msg)

    router.start()
    log.info("Server ready. Sending example commands…")

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    # ── Example: send a move command every 5 s ────────────────────────────────
    cmd_id = 0
    try:
        while True:
            cmd_id += 1
            router.send_command({
                "type":      "command",
                "cmd_id":    cmd_id,
                "timestamp": time.time(),
                "data": {
                    "action":    "move",
                    "direction": "forward",
                    "speed":     0.5,
                },
            })
            log.info("Sent move command #%d", cmd_id)
            time.sleep(5)

    except KeyboardInterrupt:
        log.info("Server stopped")


if __name__ == "__main__":
    main()