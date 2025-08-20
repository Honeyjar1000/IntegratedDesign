from flask import Flask, render_template, Response, request, jsonify
from picamera2 import Picamera2
import pigpio
import cv2
import time

app = Flask(__name__)

# ---------------- Camera (your original) ----------------
picam2 = Picamera2()
video_config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "XRGB8888"},
    controls={"FrameRate": 24}
)
picam2.configure(video_config)
picam2.start()
time.sleep(0.2)  # warm-up

def mjpeg_generator():
    while True:
        frame = picam2.capture_array()                      # XRGB8888: 4 channels
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR) # drop X, RGB->BGR
        ok, jpg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")

@app.route("/")
def index():
    # Keyboard teleop UI with video stream
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# ---------------- Servo control (pigpio) ----------------
# Physical pins: 10 -> BCM 15, 12 -> BCM 18
SERVO_GPIO = {1: 15, 2: 18}  # channel -> BCM
MIN_US, MAX_US = 500, 2500
STOP_US = 1500  # neutral for continuous rotation
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running. sudo systemctl start pigpiod")

for gpio in SERVO_GPIO.values():
    pi.set_mode(gpio, pigpio.OUTPUT)
    pi.set_servo_pulsewidth(gpio, STOP_US)

def clamp_us(us: int) -> int:
    return max(MIN_US, min(MAX_US, int(us)))

def speed_to_us(speed_pct: float) -> int:
    """Continuous rotation: -100..100 -> 1000..2000us around 1500 neutral."""
    s = max(-100.0, min(100.0, float(speed_pct)))
    return int(STOP_US + s * 5)  # 100% -> +/-500us

@app.post("/servo")
def servo_set():
    """
    Set a single servo.
    JSON: {"ch":1, "speed":30}  # -100..100 (continuous rotation)
          {"ch":2, "us":1500}   # raw pulse
    """
    data = request.get_json(force=True)
    ch = int(data.get("ch", 1))
    if ch not in SERVO_GPIO:
        return jsonify(ok=False, error="ch must be 1 or 2"), 400
    gpio = SERVO_GPIO[ch]
    if "us" in data:
        us = clamp_us(int(data["us"]))
    elif "speed" in data:
        us = clamp_us(speed_to_us(data["speed"]))
    else:
        return jsonify(ok=False, error="provide 'speed' or 'us'"), 400
    pi.set_servo_pulsewidth(gpio, us)
    return jsonify(ok=True, ch=ch, gpio=gpio, pulse_us=us)

@app.post("/drive")
def drive():
    """
    Set both wheels at once for teleop.
    JSON: {"left": -100..100, "right": -100..100}
    """
    data = request.get_json(force=True)
    left = float(data.get("left", 0))
    right = float(data.get("right", 0))
    pi.set_servo_pulsewidth(SERVO_GPIO[1], clamp_us(speed_to_us(left)))
    pi.set_servo_pulsewidth(SERVO_GPIO[2], clamp_us(speed_to_us(right)))
    return jsonify(ok=True, left=left, right=right)

@app.post("/stop")
def stop():
    for gpio in SERVO_GPIO.values():
        pi.set_servo_pulsewidth(gpio, STOP_US)
    return jsonify(ok=True, pulse_us=STOP_US)

@app.get("/servo/status")
def servo_status():
    state = {ch: int(pi.get_servo_pulsewidth(gpio)) for ch, gpio in SERVO_GPIO.items()}
    return jsonify(ok=True, pulse_us=state)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False, threaded=True)
