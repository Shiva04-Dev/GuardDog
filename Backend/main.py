from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
import json

app = FastAPI(
    title="GuardDog Backend API",
    description="Backend service for API + WebSocket telemetry",
    version="1.0.0"
)

# REST ENDPOINTS

@app.get("/")
async def root():
    return {"message": "GuardDog Backend Service is running."}

@app.get("/api/system-status")
async def get_status():
    """Checks if the integration layer is alive."""
    return {"status": "online", "layer": "backend_service"}

#  WEBSOCKETS

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """Streams live mock robot data to the frontend."""
    await websocket.accept()
    print("Frontend connected to telemetry stream.")
    
    try:
        while True:
            # Simulating data that will eventually come from the C++ Firmware
            mock_telemetry = {
                "battery_pct": 88,
                "motor_state": "standby",
                "current_gait": "none",
                "cpu_temp": 45.2
            }
            
            # Send the JSON payload
            await websocket.send_json(mock_telemetry)
            
            # Async wait so we don't block the rest of the app
            await asyncio.sleep(1) 
            
    except WebSocketDisconnect:
        print("Frontend disconnected.")