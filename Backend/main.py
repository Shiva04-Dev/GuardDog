from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
import json

# FastAPI will automatically generates docs 
app = FastAPI(
    title="Guard Dog Robot API",
    description="Backend service for API + WebSocket server",
    version="1.0.0"
)


# REST ENDPOINTS 


@app.get("/")
async def root():
    return {"message": "Gaurd Dog Backend Service is running."}

@app.get("/api/system-status")
async def get_status():
    """Simple REST endpoint to check if the integration layer is alive."""
    # soon this will query the IPC bridge
    return {"status": "online", "layer": "backend_service"}

# WEBSOCKETS For live telemetry and dashboard


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """WebSocket endpoint to stream live robot data to the frontend."""
    await websocket.accept()
    print("Frontend Dashboard connected to telemetry stream.")
    
    try:
        while True:
            #  Simulating data that will eventually 
            # come from the C++ Firmware via the Integration Layer.
            mock_telemetry = {
                "battery_pct": 88,
                "motor_state": "standby",
                "current_gait": "none",
                "cpu_temp": 45.2
            }
            
            # Send the JSON payload to the connected dashboard
            await websocket.send_json(mock_telemetry)
            
            # Async performance: wait 1 second without blocking other requests
            await asyncio.sleep(1) 
            
    except WebSocketDisconnect:
        print("Frontend Dashboard disconnected.")