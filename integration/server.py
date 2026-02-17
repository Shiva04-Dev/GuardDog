import zmq
import time
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

context = zmq.Context()

# 1. REP Socket (Bind to Port)
rep = context.socket(zmq.REP)
rep.bind("tcp://*:5555")

# 2. PUB Socket (Bind to Port)
pub = context.socket(zmq.PUB)
pub.bind("tcp://*:5556")

poller = zmq.Poller()
poller.register(rep, zmq.POLLIN)

logger.info("Server started. Waiting for PI...")

last_heartbeat_time = time.time()
HEARTBEAT_TIMEOUT = 3
safe_stop_triggered = False
last_telemetry_time = 0

time.sleep(1) # Allow clients to connect

try:
    while True:
        events = dict(poller.poll(timeout=100))

        # Handle Incoming Messages
        if rep in events:
            message = rep.recv_json()
            logger.debug(f"Received: {message}")

            if message.get("type") == "heartbeat":
                last_heartbeat_time = time.time()
                rep.send_json({"status": "heartbeat_ack"})
            else:
                # Send Movement Command
                command = {
                    "type": "command",
                    "data": {
                        "action": "move",
                        "direction": "forward",
                        "speed": 0.5
                    }
                }
                rep.send_json(command)
                logger.info("Command sent to PI")

        # Heartbeat Safety Check
        if time.time() - last_heartbeat_time > HEARTBEAT_TIMEOUT:
            if not safe_stop_triggered:
                logger.warning(" HEARTBEAT LOST — SAFE STOP TRIGGERED")
                pub.send_json({"type": "emergency", "data": {"action": "stop"}})
                safe_stop_triggered = True
            last_heartbeat_time = time.time()
        else:
            safe_stop_triggered = False

        # Telemetry
        now = time.time()
        if now - last_telemetry_time >= 1:
            pub.send_json({"type": "telemetry", "battery": 11.8})
            last_telemetry_time = now

        time.sleep(0.01)

except KeyboardInterrupt:
    logger.info("Server shutting down...")
finally:
    rep.close()
    pub.close()
    context.term()