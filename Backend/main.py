"""
backend/main.py — GuardDog Backend Service.

Responsibilities:
  - WebSocket hub: broadcast telemetry + alerts to connected dashboards
  - REST API: receive commands from dashboard, forward to Server Brain
  - Internal ingest: receive telemetry/events from Server Brain
  - Auth-gated endpoints

Run with:
    uvicorn backend.main:app --port 8000 --reload
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

import aiohttp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

log = logging.getLogger(__name__)

API_KEY    = os.getenv("API_KEY", "guarddog-secret-key-123")
BRAIN_URL  = os.getenv("BRAIN_URL", "http://localhost:8001")
PI_STREAM  = os.getenv("PI_STREAM_URL", "http://raspberrypi.local:5000")


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)
        log.info("Dashboard connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket):
        self._clients.remove(ws)
        log.info("Dashboard disconnected (%d total)", len(self._clients))

    async def broadcast(self, data: dict):
        dead = []
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.remove(ws)


manager = ConnectionManager()

# ── Latest state (for new dashboard connections) ──────────────────────────────

latest_telemetry: dict = {}
latest_alert: dict = {}


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="GuardDog Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket endpoints ───────────────────────────────────────────────────────

@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    """Streams telemetry + alerts to the dashboard."""
    await manager.connect(ws)
    # Send latest state immediately on connect
    if latest_telemetry:
        await ws.send_json({"type": "telemetry", **latest_telemetry})
    if latest_alert:
        await ws.send_json({"type": "alert", **latest_alert})
    try:
        while True:
            # Keep alive; actual data is pushed via broadcast()
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        manager.disconnect(ws)


@app.websocket("/ws/commands")
async def ws_commands(ws: WebSocket):
    """Receives commands from the dashboard, forwards to Server Brain."""
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            await _forward_command(data)
            await ws.send_json({"status": "sent", "cmd": data})
    except WebSocketDisconnect:
        pass


# ── REST endpoints ────────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    type: str = "command"
    data: dict


@app.post("/api/command")
async def post_command(req: CommandRequest, x_api_key: str = Header(None)):
    """REST command endpoint (alternative to WebSocket)."""
    _auth(x_api_key)
    await _forward_command(req.dict())
    return {"status": "sent"}


@app.get("/api/status")
async def api_status():
    return {
        "status": "online",
        "connected_dashboards": len(manager._clients),
        "pi_stream": PI_STREAM,
        "brain_url": BRAIN_URL,
    }


@app.get("/api/stream-url")
async def stream_url():
    """Returns the Pi stream URL for the dashboard to embed directly."""
    return {"url": f"{PI_STREAM}/stream"}


# ── Internal ingest (called by Server Brain) ──────────────────────────────────

@app.post("/internal/ingest")
async def ingest(payload: dict):
    """Receives telemetry/events from Server Brain and broadcasts to dashboards."""
    global latest_telemetry
    if payload.get("type") == "telemetry":
        latest_telemetry = payload
    await manager.broadcast({"type": payload.get("type", "data"), **payload})
    return {"ok": True}


@app.post("/internal/alert")
async def alert(payload: dict):
    """Receives intruder alerts from Server Brain and broadcasts to dashboards."""
    global latest_alert
    latest_alert = {**payload, "received_at": datetime.now().isoformat()}
    await manager.broadcast({"type": "alert", **latest_alert})
    log.warning("ALERT broadcast to %d dashboard(s)", len(manager._clients))
    return {"ok": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth(key: str | None):
    if key != API_KEY:
        raise HTTPException(403, "Invalid API key")


async def _forward_command(cmd: dict):
    """POST command to Server Brain which publishes it over ZMQ to the Pi."""
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{BRAIN_URL}/command",
                json=cmd,
                headers={"x-api-key": API_KEY},
                timeout=aiohttp.ClientTimeout(total=3),
            )
    except Exception as e:
        log.error("Failed to forward command to brain: %s", e)


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)-20s %(levelname)-8s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))