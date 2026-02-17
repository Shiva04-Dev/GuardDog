# Firmware (C++ Real-Time Control)

This module controls:
- Motor drivers
- Gait generation
- IMU stabilization
- Safety overrides

Runs at high frequency (100–400 Hz).

---

## Responsibilities

- Execute MOVE / TURN / STOP commands
- Maintain robot balance
- Monitor battery and motor temperature
- Enforce emergency stop

---

## Safety Constraints

- Reject invalid speed values
- Stop if heartbeat timeout
- Stop if tilt exceeds threshold
- Stop on low battery

---

## Build

mkdir build
cd build
cmake ..
make

---

## Runtime

./firmware_main
