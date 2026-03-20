"""
Central IPC configuration. All ZeroMQ ports, topics, and timing constants.
Import from here — never hardcode ports elsewhere.
"""

# ── Ports ────────────────────────────────────────────────────────────────────
CMD_PORT        = 5555   # Server → Robot  (PUB/SUB)
TELEMETRY_PORT  = 5556   # Robot  → Server (PUSH/PULL)
EVENT_PORT      = 5557   # Robot  → Server (PUSH/PULL)
HEARTBEAT_PORT  = 5558   # Server → Robot  (PUB/SUB)

# ── Topics (PUB/SUB filter strings) ─────────────────────────────────────────
TOPIC_COMMAND   = "command"
TOPIC_TELEMETRY = "telemetry"
TOPIC_EVENT     = "event"
TOPIC_HEARTBEAT = "heartbeat"

# ── Timing ───────────────────────────────────────────────────────────────────
HEARTBEAT_INTERVAL  = 1.0   # seconds between heartbeat publishes
HEARTBEAT_TIMEOUT   = 3.0   # seconds of silence before safe-stop triggers
TELEMETRY_INTERVAL  = 0.05  # seconds between telemetry pushes (~20 Hz)
POLL_TIMEOUT_MS     = 10    # ZMQ poll block duration

# ── Serial ───────────────────────────────────────────────────────────────────
SERIAL_PORT     = "/dev/ttyUSB0"
SERIAL_BAUD     = 115200
SERIAL_TIMEOUT  = 1.0

# ── Command IDs ──────────────────────────────────────────────────────────────
CMD_ID_STOP     = 99
CMD_ID_MOVE     = 1