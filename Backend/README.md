# Backend Service

Provides:
- REST API
- WebSocket telemetry
- Alert storage
- Dashboard data

---

## Endpoints

GET /status
GET /telemetry
POST /command
GET /alerts

---

## WebSocket

/ws → Real-time robot updates

---

## Run

uvicorn main:app --reload
