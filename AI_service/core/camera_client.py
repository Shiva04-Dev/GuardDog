"""
camera_client.py — Raspberry Pi camera process.

Uses picamera2 (libcamera backend) for capture — required on Pi 4/5
running Raspberry Pi OS Bookworm or later.
OpenCV is only used for JPEG encoding and image processing, not capture.

Usage:
    python -m pi.core.camera_client
    python -m pi.core.camera_client --dry-run   # test pattern, no camera needed
    python -m pi.core.camera_client --verbose
"""

import argparse
import logging
import signal
import sys
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response

from pi.ipc.config import (
    FRAME_WIDTH, FRAME_HEIGHT, JPEG_QUALITY,
    STREAM_PORT,
)

log = logging.getLogger("camera_client")
app = Flask(__name__)

# ── Shared frame state ────────────────────────────────────────────────────────

_frame: np.ndarray | None = None
_frame_lock = threading.Lock()
_running = False


def _set_frame(frame: np.ndarray):
    global _frame
    with _frame_lock:
        _frame = frame.copy()


def _get_frame() -> np.ndarray | None:
    with _frame_lock:
        return _frame.copy() if _frame is not None else None


# ── Low-light enhancement ─────────────────────────────────────────────────────

def _enhance(frame: np.ndarray, threshold: int = 60) -> np.ndarray:
    if np.mean(frame) < threshold:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        eq   = cv2.equalizeHist(gray)
        frame = cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR)
        log.debug("Low-light enhancement applied")
    return frame


# ── Picamera2 capture loop ────────────────────────────────────────────────────

def _picamera2_loop():
    global _running
    from picamera2 import Picamera2

    cam = Picamera2()
    cfg = cam.create_preview_configuration(
        main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "BGR888"}
    )
    cam.configure(cfg)
    cam.start()
    # Give the sensor time to settle (auto-exposure stabilises)
    time.sleep(2)
    log.info("Picamera2 capture started (%dx%d)", FRAME_WIDTH, FRAME_HEIGHT)

    try:
        while _running:
            # BGR888 format — no colour conversion needed
            bgr = cam.capture_array()
            
            
            bgr = _enhance(bgr)
            _set_frame(bgr)
            time.sleep(0.033)   # ~30 fps
    finally:
        cam.stop()
        log.info("Picamera2 stopped")


# ── Dry-run test pattern ──────────────────────────────────────────────────────

def _dummy_loop():
    global _running
    log.info("Dry-run: generating test pattern")
    t = 0
    while _running:
        frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        frame[:, :, 1] = int(128 + 100 * np.sin(t))
        cv2.putText(frame, "DRY RUN", (220, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (200, 200, 200), 2)
        cv2.putText(frame, time.strftime("%H:%M:%S"), (220, 290),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 1)
        _set_frame(frame)
        t += 0.05
        time.sleep(0.033)


# ── MJPEG generator ───────────────────────────────────────────────────────────

def _gen_mjpeg():
    while True:
        frame = _get_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + buf.tobytes()
            + b"\r\n"
        )


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/stream")
def stream():
    """MJPEG stream — embed in <img src="..."> on the dashboard."""
    return Response(_gen_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/snapshot")
def snapshot():
    """Single JPEG frame — polled by server_brain for face recognition."""
    frame = _get_frame()
    if frame is None:
        return "No frame available", 503
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return Response(buf.tobytes(), mimetype="image/jpeg")


@app.route("/health")
def health():
    return {"status": "ok", "has_frame": _frame is not None,
            "resolution": f"{FRAME_WIDTH}x{FRAME_HEIGHT}"}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _running

    parser = argparse.ArgumentParser(description="GuardDog camera client (picamera2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use a test pattern instead of the real camera")
    parser.add_argument("--port",    type=int, default=STREAM_PORT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(name)-20s %(levelname)-8s  %(message)s",
    )

    _running = True

    if args.dry_run:
        t = threading.Thread(target=_dummy_loop, daemon=True)
    else:
        try:
            from picamera2 import Picamera2  # noqa: F401 - validate import early
        except ImportError:
            log.error(
                "picamera2 not found.\n"
                "  Fix: sudo apt install python3-picamera2\n"
                "  Then recreate your venv with:\n"
                "    python3 -m venv .venv --system-site-packages\n"
                "  Or test without hardware: --dry-run"
            )
            sys.exit(1)
        t = threading.Thread(target=_picamera2_loop, daemon=True)

    t.start()

    def _shutdown(sig, _frame):
        global _running
        log.info("Shutting down")
        _running = False
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    log.info("Stream   -> http://0.0.0.0:%d/stream",   args.port)
    log.info("Snapshot -> http://0.0.0.0:%d/snapshot", args.port)
    log.info("Health   -> http://0.0.0.0:%d/health",   args.port)
    app.run(host="0.0.0.0", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()