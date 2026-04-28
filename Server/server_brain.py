"""
server_brain.py — Face recognition server.

Pulls frames from the Pi's MJPEG stream at regular intervals,
runs face_recognition on them, and:
  - Pushes intruder alerts to the Backend via HTTP
  - Publishes ZMQ commands to the Pi when needed
  - Forwards telemetry/events received from the Pi to the Backend

Run with:
    uvicorn server.server_brain:app --port 8001
"""

import asyncio
import io
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
import cv2
import face_recognition
import numpy as np
import zmq
from fastapi import FastAPI, Header, HTTPException, Query, UploadFile, File
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from server.ipc.config import (
    CMD_PORT, TELEMETRY_PORT, EVENT_PORT, HEARTBEAT_PORT,
    HEARTBEAT_INTERVAL, KNOWN_FACES_DIR, LOGS_DIR,
    BACKEND_URL, API_KEY, FACE_MODEL,
)

log = logging.getLogger(__name__)
Path(KNOWN_FACES_DIR).mkdir(exist_ok=True)
Path(LOGS_DIR).mkdir(exist_ok=True)


# ── Face store ────────────────────────────────────────────────────────────────

class FaceStore:
    def __init__(self):
        self.encodings = []
        self.names = []
        self.last_loaded = None
        self._lock = threading.Lock()

    def load(self):
        with self._lock:
            self.encodings, self.names = [], []
            count = 0
            for f in Path(KNOWN_FACES_DIR).iterdir():
                if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    try:
                        img = face_recognition.load_image_file(str(f))
                        encs = face_recognition.face_encodings(img)
                        if encs:
                            self.encodings.append(encs[0])
                            self.names.append(f.stem)
                            count += 1
                    except Exception as e:
                        log.warning("Could not load %s: %s", f.name, e)
            self.last_loaded = datetime.now()
            log.info("Loaded %d known faces", count)
            return count

    def get(self):
        with self._lock:
            return list(self.encodings), list(self.names)


face_store = FaceStore()

THRESHOLDS = {"strict": 0.35, "normal": 0.45, "loose": 0.55}


# ── Face recognition ──────────────────────────────────────────────────────────

def recognize(frame_rgb: np.ndarray, mode="normal") -> dict:
    threshold = THRESHOLDS.get(mode, 0.45)
    locations = face_recognition.face_locations(frame_rgb, model=FACE_MODEL)

    if not locations:
        return {"is_intruder": False, "faces_detected": 0, "matches": [],
                "unknown_faces": 0, "status": "no_faces"}

    encodings = face_recognition.face_encodings(frame_rgb, locations)
    known_encs, known_names = face_store.get()
    results, unknown = [], 0
    intruder = False

    for enc in encodings:
        if not known_encs:
            results.append({"name": "Unknown", "confidence": 1.0, "is_known": False})
            unknown += 1
            intruder = True
            continue
        dists = face_recognition.face_distance(known_encs, enc)
        idx = int(np.argmin(dists))
        dist = float(dists[idx])
        if dist <= threshold:
            results.append({"name": known_names[idx],
                             "confidence": round(1 - dist, 3), "is_known": True})
        else:
            results.append({"name": "Unknown",
                             "confidence": round(1 - dist, 3), "is_known": False})
            unknown += 1
            intruder = True

    return {
        "is_intruder": intruder,
        "faces_detected": len(locations),
        "unknown_faces": unknown,
        "matches": results,
        "status": "intruder" if intruder else "all_known",
    }


# ── ZMQ server-side sockets ───────────────────────────────────────────────────

class ZMQBroker:
    """Binds ZMQ sockets. Forwards telemetry/events to backend. Publishes commands to Pi."""

    def __init__(self):
        self._ctx      = zmq.Context.instance()
        self._cmd_pub  = self._ctx.socket(zmq.PUB)
        self._tel_pull = self._ctx.socket(zmq.PULL)
        self._evt_pull = self._ctx.socket(zmq.PULL)
        self._hb_pub   = self._ctx.socket(zmq.PUB)

        self._cmd_pub.bind(f"tcp://*:{CMD_PORT}")
        self._tel_pull.bind(f"tcp://*:{TELEMETRY_PORT}")
        self._evt_pull.bind(f"tcp://*:{EVENT_PORT}")
        self._hb_pub.bind(f"tcp://*:{HEARTBEAT_PORT}")

        self._running = False
        log.info("ZMQ broker bound on ports %s/%s/%s/%s",
                 CMD_PORT, TELEMETRY_PORT, EVENT_PORT, HEARTBEAT_PORT)

    def publish_command(self, cmd: dict):
        self._cmd_pub.send_json(cmd)

    def start(self):
        self._running = True
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        threading.Thread(target=self._forward_loop,   daemon=True).start()

    def _heartbeat_loop(self):
        while self._running:
            self._hb_pub.send_json({"type": "heartbeat", "timestamp": time.time()})
            time.sleep(HEARTBEAT_INTERVAL)

    def _forward_loop(self):
        """Forward Pi telemetry/events to the Backend service."""
        poller = zmq.Poller()
        poller.register(self._tel_pull, zmq.POLLIN)
        poller.register(self._evt_pull, zmq.POLLIN)

        while self._running:
            socks = dict(poller.poll(100))
            for sock in (self._tel_pull, self._evt_pull):
                if socks.get(sock) == zmq.POLLIN:
                    msg = sock.recv_json()
                    asyncio.run(self._post_to_backend(msg))

    @staticmethod
    async def _post_to_backend(payload: dict):
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(f"{BACKEND_URL}/internal/ingest",
                              json=payload, timeout=aiohttp.ClientTimeout(total=2))
        except Exception as e:
            log.debug("Backend forward failed: %s", e)

    def close(self):
        self._running = False
        for sock in (self._cmd_pub, self._tel_pull, self._evt_pull, self._hb_pub):
            sock.close(linger=0)


broker = ZMQBroker()


# ── Periodic frame-pull from Pi stream ───────────────────────────────────────

async def _frame_check_loop(pi_stream_url: str, interval: float = 2.0):
    """Pull a snapshot from the Pi every `interval` seconds and run recognition."""
    log.info("Frame check loop started → %s", pi_stream_url)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(pi_stream_url.rstrip("/") + "/snapshot",
                                       timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        nparr = np.frombuffer(data, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            result = recognize(rgb)
                            if result["is_intruder"]:
                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                path = f"{LOGS_DIR}/intruder_{ts}.jpg"
                                cv2.imwrite(path, frame)
                                log.warning("INTRUDER detected — saved %s", path)
                                # alert backend
                                asyncio.create_task(_alert_backend(result, path))
            except Exception as e:
                log.debug("Frame check error: %s", e)
            await asyncio.sleep(interval)


async def _alert_backend(result: dict, image_path: str):
    payload = {**result, "image_path": image_path, "timestamp": datetime.now().isoformat()}
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"{BACKEND_URL}/internal/alert", json=payload,
                         timeout=aiohttp.ClientTimeout(total=3))
    except Exception as e:
        log.warning("Alert delivery failed: %s", e)


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    face_store.load()

    # File watcher for hot-reload of known_faces/
    observer = Observer()
    class _Watcher(FileSystemEventHandler):
        def on_any_event(self, _): face_store.load()
    observer.schedule(_Watcher(), KNOWN_FACES_DIR, recursive=False)
    observer.start()

    broker.start()

    pi_url = os.getenv("PI_STREAM_URL", "http://raspberrypi.local:5000")
    task = asyncio.create_task(_frame_check_loop(pi_url))

    yield

    task.cancel()
    observer.stop()
    broker.close()


app = FastAPI(title="GuardDog Brain", lifespan=lifespan)


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _auth(key: Optional[str]):
    if key != API_KEY:
        raise HTTPException(403, "Invalid API key")


@app.get("/health")
async def health():
    encs, names = face_store.get()
    return {"status": "ok", "faces_loaded": len(encs),
            "last_reload": face_store.last_loaded.isoformat() if face_store.last_loaded else None}


@app.post("/check_face")
async def check_face(
    file: UploadFile = File(...),
    camera_id: str = Query("default"),
    mode: str = Query("normal"),
    x_api_key: str = Header(None),
):
    """Manual face check endpoint (also called by dashboard upload)."""
    _auth(x_api_key)
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Could not decode image")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return recognize(rgb, mode)


@app.post("/command")
async def send_command(cmd: dict, x_api_key: str = Header(None)):
    """Forward a command from Backend/Dashboard to the Pi via ZMQ."""
    _auth(x_api_key)
    broker.publish_command(cmd)
    return {"status": "sent"}


@app.post("/reload_faces")
async def reload_faces(x_api_key: str = Header(None)):
    _auth(x_api_key)
    count = face_store.load()
    return {"status": "reloaded", "faces_loaded": count}


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8001)))