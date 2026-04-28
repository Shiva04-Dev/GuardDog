"""
Shared IPC constants for the Pi side.
Keep in sync with server/ipc/config.py.
"""

# ZMQ ports (server binds, Pi connects)
CMD_PORT       = 5555   # Server → Pi  (PUB/SUB)
TELEMETRY_PORT = 5556   # Pi → Server  (PUSH/PULL)
EVENT_PORT     = 5557   # Pi → Server  (PUSH/PULL)
HEARTBEAT_PORT = 5558   # Server → Pi  (PUB/SUB)

# Topics
TOPIC_COMMAND   = "command"
TOPIC_TELEMETRY = "telemetry"
TOPIC_EVENT     = "event"

# Timing
HEARTBEAT_TIMEOUT  = 3.0   # seconds before safe-stop
TELEMETRY_INTERVAL = 0.5   # seconds between telemetry pushes
POLL_TIMEOUT_MS    = 10

# Camera
CAMERA_INDEX   = 0
FRAME_WIDTH    = 640
FRAME_HEIGHT   = 480
STREAM_PORT    = 5000      # Flask MJPEG stream port
JPEG_QUALITY   = 70

# Serial
SERIAL_PORT    = "/dev/ttyUSB0"
SERIAL_BAUD    = 115200