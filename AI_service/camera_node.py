import cv2, face_recognition, os, numpy as np, pygame, random, time, json
from flask import Flask, Response
from datetime import datetime

# ===============================
# LOAD CONFIG
# ===============================
with open("config.json") as f:
    config = json.load(f)

CAMERA_ID = config.get("camera_id", "Camera1")
CONFIDENCE_DAY = config.get("confidence_day", 0.45)
CONFIDENCE_NIGHT = config.get("confidence_night", 0.50)
NIGHT_THRESHOLD = config.get("night_threshold", 60)
FRAME_CONFIRMATION = config.get("frame_confirmation",5)
ALARM_COOLDOWN = config.get("alarm_cooldown",15)
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ===============================
# SOUND INIT
# ===============================
pygame.mixer.init()
sound_files = ["sounds/bark1.wav","sounds/bark2.wav","sounds/growl.wav"]

def play_random_sound():
    pygame.mixer.music.load(random.choice(sound_files))
    pygame.mixer.music.play()

# ===============================
# LOAD AUTHORIZED FACES
# ===============================
known_encodings = []
known_names = []

for file in os.listdir("known_faces"):
    if file.endswith((".jpg",".png")):
        img = face_recognition.load_image_file(f"known_faces/{file}")
        enc = face_recognition.face_encodings(img)
        if enc:
            known_encodings.append(enc[0])
            known_names.append(os.path.splitext(file)[0])

# ===============================
# CAMERA INIT
# ===============================
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

unknown_counter = 0
frame_count = 0

def gen_frames():
    global unknown_counter, frame_count
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        frame_count += 1

        brightness = np.mean(frame)
        if brightness < NIGHT_THRESHOLD:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frame = cv2.cvtColor(cv2.GaussianBlur(cv2.equalizeHist(gray),(5,5),0), cv2.COLOR_GRAY2BGR)
            confidence_threshold = CONFIDENCE_NIGHT
        else:
            confidence_threshold = CONFIDENCE_DAY

        if frame_count % 2 == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb, model="hog")
            encodings = face_recognition.face_encodings(rgb, locations)
            unknown_detected = False

            for (top,right,bottom,left),face_enc in zip(locations, encodings):
                name = "Unknown"
                distances = face_recognition.face_distance(known_encodings, face_enc)
                if len(distances)>0:
                    best_match = np.argmin(distances)
                    if distances[best_match] < confidence_threshold:
                        name = known_names[best_match]
                    else:
                        unknown_detected = True
                else:
                    unknown_detected = True

                color = (0,255,0) if name!="Unknown" else (0,0,255)
                cv2.rectangle(frame,(left,top),(right,bottom),color,2)
                cv2.putText(frame,name,(left,top-10),cv2.FONT_HERSHEY_SIMPLEX,0.7,color,2)

            if unknown_detected:
                unknown_counter +=1
            else:
                unknown_counter = 0

            if unknown_counter >= FRAME_CONFIRMATION:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename=f"logs/{CAMERA_ID}_unknown_{ts}.jpg"
                cv2.imwrite(filename, frame)
                play_random_sound()
                unknown_counter=0

        ret, buffer = cv2.imencode(".jpg", frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n'+buffer.tobytes()+b'\r\n')

# ===============================
# FLASK APP
# ===============================
app = Flask(__name__)

@app.route(f'/video_feed/{CAMERA_ID}')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__=="__main__":
    app.run(host='0.0.0.0',port=config.get("port",5000))

