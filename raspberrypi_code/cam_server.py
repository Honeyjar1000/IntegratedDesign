#!/usr/bin/env python3
import atexit
from flask import Flask, Response, request, jsonify
import pigpio

# ---- Servo config (your values) ----
PIN = 18                 # BCM pin (physical 12)
NEUTRAL_US = 1490        # your calibrated stop
SCALE = 400              # +/-us range for full speed
def to_us(speed):        # speed in [-1..1]
    return max(1000, min(2000, NEUTRAL_US + int(speed * SCALE)))

# ---- Camera (Picamera2) ----
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from threading import Condition

class StreamingOutput:
    def __init__(self):
        self.frame = None
        self.condition = Condition()
    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

app = Flask(__name__)

# Motor init
pi = pigpio.pi()
pi.set_mode(PIN, pigpio.OUTPUT)
pi.set_servo_pulsewidth(PIN, NEUTRAL_US)  # hold neutral

# Camera init
picam2 = Picamera2()
# Choose resolution + fps that your Zero 2 W can handle easily
video_cfg = picam2.create_video_configuration(main={"size": (1280, 720)}, controls={"FrameRate": 30})
picam2.configure(video_cfg)

# Manual white-balance gains (similar to libcamera --awbgains R,B)
# Tweak these to remove green/magenta cast on the NoIR
R_GAIN, B_GAIN = 1.00, 0.98  # try (0.95,1.00) or (1.05,0.95) to taste
picam2.set_controls({"AwbEnable": False, "ColourGains": (R_GAIN, B_GAIN)})

output = StreamingOutput()
picam2.start_recording(JpegEncoder(85), FileOutput(output))

@atexit.register
def _cleanup():
    try:
        picam2.stop_recording()
    except Exception:
        pass
    try:
        pi.set_servo_pulsewidth(PIN, NEUTRAL_US)
        pi.stop()
    except Exception:
        pass

# ---- Routes ----

@app.route("/")
def index():
    return (
        "<h3>Raspberry Pi Camera + Motor</h3>"
        '<p>Video: <a href="/stream.mjpg">/stream.mjpg</a></p>'
        '<p>Set speed (POST JSON): <code>POST /speed {"speed":0.7}</code></p>'
        '<p>Set WB (GET): <code>/wb?r=1.00&b=0.98</code></p>'
    )

@app.route("/stream.mjpg")
def stream_mjpg():
    def gen():
        while True:
            with output.condition:
                output.condition.wait()
                frame = output.frame
            # multipart/x-mixed-replace frame
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" +
                   frame + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/speed", methods=["POST"])
def set_speed():
    data = request.get_json(force=True, silent=True) or {}
    speed = max(-1.0, min(1.0, float(data.get("speed", 0.0))))
    pi.set_servo_pulsewidth(PIN, to_us(speed))
    return jsonify(ok=True, speed=speed)

@app.route("/wb")
def set_wb():
    # quick way to tune colour without restarting
    try:
        r = float(request.args.get("r", R_GAIN))
        b = float(request.args.get("b", B_GAIN))
        picam2.set_controls({"AwbEnable": False, "ColourGains": (r, b)})
        return jsonify(ok=True, r=r, b=b)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

if __name__ == "__main__":
    # threaded=True so video + API play nicely
    app.run(host="0.0.0.0", port=8080, threaded=True)
