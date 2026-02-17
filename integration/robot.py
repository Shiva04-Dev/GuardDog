import zmq
import serial
import time
import logging

# 1. Setup Logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# 2. Setup ZeroMQ (Network)

context = zmq.Context()
req = context.socket(zmq.REQ)
req.connect("tcp://192.168.1.100:5555")  # Replace with your Server PC IP

sub = context.socket(zmq.SUB)
sub.connect("tcp://192.168.1.100:5556")
sub.setsockopt_string(zmq.SUBSCRIBE, "")

# 3. Setup Serial (Hardware)

try:
    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    logger.info("Serial connected to motor driver")
except serial.SerialException:
    logger.error("Serial port not found! Check /dev/ttyUSB0")
    ser = None

# 4. Helper Functions

def send_to_motor(cmd_type, msg_id, payload):
    if ser and ser.is_open:
        packet = f"<{cmd_type}|{msg_id}|{payload}|00>"
        ser.write(packet.encode())
        logger.debug(f"Serial Sent: {packet}")
    else:
        logger.warning("Serial not available, skipping motor command")

def emergency_stop():
    logger.critical(" EMERGENCY STOP EXECUTED")
    send_to_motor("CMD", 0, "STOP")
    # TODO: Add GPIO pin to cut power relay for hardware safety


# 5. Main Loop

logger.info("PI Client Started...")
last_heartbeat = 0
HEARTBEAT_INTERVAL = 1

try:
    while True:
        now = time.time()

        # --- A. Send Heartbeat to Server ---
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            req.send_json({"type": "heartbeat", "timestamp": now})
            try:
                ack = req.recv_json()
                logger.debug("Heartbeat ACK received")
            except:
                logger.warning("Server heartbeat failed")
            last_heartbeat = now

        # --- B. Listen for Emergency Stops (Non-blocking) ---
        sub.setsockopt(zmq.RCVTIMEO, 100)
        try:
            msg = sub.recv_json()
            if msg.get("type") == "emergency":
                emergency_stop()
        except:
            pass

        # --- C. Listen for Movement Commands (Non-blocking) ---
        req.setsockopt(zmq.RCVTIMEO, 100)
        try:
            # Request command
            req.send_json({"type": "request_command"})
            cmd = req.recv_json()
            
            if cmd.get("type") == "command":
                action = cmd["data"]["action"]
                speed = int(cmd["data"]["speed"] * 100)
                
                logger.info(f"Executing: {action} at {speed}")
                
                # Translate ZeroMQ command to Serial command
                if action == "move":
                    send_to_motor("CMD", 1, f"Move:Forward:{speed}")
                elif action == "stop":
                    send_to_motor("CMD", 1, "STOP")
        except:
            pass

        time.sleep(0.1)

except KeyboardInterrupt:
    logger.info("Shutting down...")
    emergency_stop()

finally:
    if ser: ser.close()
    req.close()
    sub.close()
    context.term()