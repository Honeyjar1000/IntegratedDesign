from flask import Flask, render_template, Response
from picamera2 import Picamera2
import cv2
import time

app = Flask(__name__)

# --- Camera init ---
picam2 = Picamera2()
# modest resolution keeps CPU low on Zero 2 W; tweak as needed
video_config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "XRGB8888"},
    controls={"FrameRate": 24}
)
picam2.configure(video_config)
picam2.start()
time.sleep(0.2)  # small warm-up

def mjpeg_generator():
    """
    Grabs frames from Picamera2, JPEG-encodes them, and yields as multipart MJPEG.
    """
    while True:
        frame = picam2.capture_array()              # numpy array, shape (H, W, 4)
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        ok, jpg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        chunk = jpg.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n"
               b"Content-Length: " + str(len(chunk)).encode() + b"\r\n\r\n" +
               chunk + b"\r\n")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    # multipart/x-mixed-replace streaming (MJPEG)
    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    # change port=80 to 5000 if you don’t want sudo
    app.run(host="0.0.0.0", port=80, debug=True, threaded=True)
