# Integration Layer

This module connects Python AI and C++ firmware safely.

It provides:
- Command validation
- ZeroMQ communication
- Telemetry publishing
- Heartbeat monitoring
- Watchdog fail-safe

---

## Architecture

Python (REQ) → C++ (REP)
C++ (PUB) → Python (SUB)

Ports:
5555 → Commands
5556 → Telemetry

---

## Responsibilities

- Define IPC schema
- Validate all incoming commands
- Enforce timeout-based STOP
- Synchronize system state

---

## Safety Rules

If no heartbeat > 500ms → STOP
If malformed message → Reject
If unsafe parameter → Clamp or Reject

---

## Testing

Simulate:
- Network drop
- Invalid command
- AI crash
