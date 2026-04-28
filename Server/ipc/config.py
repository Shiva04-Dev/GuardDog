"""Server-side IPC and service configuration."""
import os

# ZMQ ports
CMD_PORT       = 5555
TELEMETRY_PORT = 5556
EVENT_PORT     = 5557
HEARTBEAT_PORT = 5558

HEARTBEAT_INTERVAL = 1.0

# Paths
KNOWN_FACES_DIR = "server/known_faces"
LOGS_DIR        = "server/logs"

# Auth
API_KEY = os.getenv("API_KEY", "guarddog-secret-key-123")

# Downstream services
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Face model: "hog" (CPU) or "cnn" (GPU)
FACE_MODEL = os.getenv("FACE_MODEL", "hog")