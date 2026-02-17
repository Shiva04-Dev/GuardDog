import zmq
import serial
import time

# ZeroMQ for server communication
zmq_context = zmq.Context()
req = zmq_context.socket(zmq.REQ)
req.connect("tcp://localhost:5555")

# Serial for motor control
ser = serial.Serial('/dev/ttyUSB0', 115200)

def send_to_motor(cmd_type, msg_id, payload):
    packet = f"<{cmd_type}|{msg_id}|{payload}|00>"
    ser.write(packet.encode())

while True:
    # Get command from server (ZeroMQ)
    req.send_json({"type": "heartbeat"})
    server_msg = req.recv_json()
    
    if server_msg.get("type") == "command":
        action = server_msg["data"]["action"]
        
        # Convert to serial command for motor
        if action == "move":
            speed = int(server_msg["data"]["speed"] * 100)
            send_to_motor("CMD", 1, f"Move:Forward:{speed}")
    
    time.sleep(0.1)