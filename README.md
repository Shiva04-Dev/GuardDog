# Quadro Security Robot

A quadruped security robot capable of:
- Walking and stabilizing in real-time
- Detecting humans using computer vision
- Making rule-based threat decisions
- Streaming live telemetry
- Triggering alerts

Target: Working prototype by June 10.

---

## 🧠 System Overview

The system is divided into independent layers:

Firmware (C++) → Real-time motor control  
Integration Layer → Safe communication bridge  
AI Service (Python) → Vision + decision logic  
Backend Service (Python) → API + dashboard  
Frontend → Monitoring interface  

All layers communicate through a defined IPC schema.

---

## 🗂 Project Structure

firmware/           → Real-time motor control  
integration/        → IPC + watchdog + validation  
ai_service/         → Vision + threat logic  
backend_service/    → API + WebSocket server  
frontend/           → Dashboard UI  
docs/               → Architecture + specs  
tests/              → Integration + stress tests  

---

## 🔌 How to Run (Prototype)

1. Start firmware
2. Start integration layer
3. Start AI service
4. Start backend service
5. Open dashboard

---

## 🚨 Safety Rules

- Python never sends raw motor angles
- Firmware has final authority
- Loss of heartbeat triggers STOP
- Low battery triggers STOP

---

## 📅 Roadmap

Phase 1: Movement  
Phase 2: Vision  
Phase 3: Streaming  
Phase 4: Integration  
Phase 5: Demo Stabilization  

---

## 👥 Team Roles

Person 1 → Firmware  
Person 2 → Integration  
Person 3 → AI  
Person 4 → Backend  
Person 5 → Mechanical  

---

