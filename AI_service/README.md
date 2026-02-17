# AI Service

Provides:
- Camera capture
- YOLO human detection
- Object tracking
- Threat scoring
- Decision logic

---

## Pipeline

Camera → Detection → Tracking → Scoring → Command

---

## Features

- Person detection
- Zone violation detection
- Threat scoring (0–100)
- State machine logic

---

## Configuration

config/zones.json → Restricted areas  
config/ai_config.yaml → Model parameters  

---

## Run

python main.py
