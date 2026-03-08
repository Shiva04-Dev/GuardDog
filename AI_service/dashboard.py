from flask import Flask, render_template

app = Flask(__name__)

CAMERA_URLS = [
    {"name":"Front Door", "url":"http://192.168.1.10:5000/video_feed/FrontDoor"},
    {"name":"Back Yard", "url":"http://192.168.1.11:5000/video_feed/BackYard"},
]

@app.route("/")
def index():
    return render_template("index.html", cameras=CAMERA_URLS)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
