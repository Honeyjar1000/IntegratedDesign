from flask import Flask, render_template, Response, request, jsonify
from picamera2 import Picamera2
import pigpio
import cv2, time

app = Flask(__name__)

# ---------------- Camera (unchanged) ----------------
picam2 = Picamera2()
video_config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "XRGB8888"},
    controls={"FrameRate": 24}
)
picam2.configure(video_config)
picam2.start()
time.sleep(0.2)

def mjpeg_generator():
    while True:
        frame = picam2.capture_array()                      # XRGB8888
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR) # drop X
        ok, jpg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# ---------------- Servo control w/ anti-jitter ----------------
# Physical pins: 10 -> BCM15, 12 -> BCM18
SERVOS = {
    1: {"gpio": 15, "stop": 1500},   # per-servo neutral; trim via /servo/trim
    2: {"gpio": 18, "stop": 1500},
}

MIN_US, MAX_US = 500, 2500
DEADBAND_PCT = 12            # ignore |speed| below this (%), avoids chatter
MIN_START_US  = 40           # minimum offset to "break away" from neutral
STEP_US       = 30           # max change per command (slew/ramp)
FWD_SCALE     = 5.0          # µs per % forward
REV_SCALE     = 5.5          # µs per % reverse (often needs a little more)

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio not running. Try: sudo systemctl start pigpiod")

for ch, cfg in SERVOS.items():
    pi.set_mode(cfg["gpio"], pigpio.OUTPUT)
    pi.set_servo_pulsewidth(cfg["gpio"], cfg["stop"])

_last_us = {ch: SERVOS[ch]["stop"] for ch in SERVOS}   # for slew limiting

def clamp_us(us: int) -> int:
    return max(MIN_US, min(MAX_US, int(us)))

def speed_to_us(ch: int, speed_pct: float) -> int:
    """Continuous rotation mapping with deadband + reverse bias."""
    s = max(-100.0, min(100.0, float(speed_pct)))
    stop = SERVOS[ch]["stop"]

    # Deadband around stop to avoid jitter
    if abs(s) < DEADBAND_PCT:
        return stop

    if s > 0:
        delta = max(MIN_START_US, int(s * FWD_SCALE))
        return clamp_us(stop + delta)
    else:
        delta = max(MIN_START_US, int((-s) * REV_SCALE))
        return clamp_us(stop - delta)

def apply_with_slew(ch: int, target_us: int):
    """Limit step size to reduce twitching."""
    prev = _last_us.get(ch, SERVOS[ch]["stop"])
    if abs(target_us - prev) > STEP_US:
        target_us = prev + STEP_US if target_us > prev else prev - STEP_US
    _last_us[ch] = target_us
    pi.set_servo_pulsewidth(SERVOS[ch]["gpio"], target_us)
    return target_us

@app.post("/drive")
def drive():
    """
    Set both wheels: {"left": -100..100, "right": -100..100} (percent)
    """
    data = request.get_json(force=True)
    left = float(data.get("left", 0))
    right = float(data.get("right", 0))
    l_us = speed_to_us(1, left)
    r_us = speed_to_us(2, right)
    l_us = apply_with_slew(1, l_us)
    r_us = apply_with_slew(2, r_us)
    return jsonify(ok=True, left=left, right=right, l_us=l_us, r_us=r_us)

@app.post("/servo")
def servo_single():
    """
    Direct control: {"ch":1, "speed":-30} OR {"ch":2, "us":1600}
    """
    data = request.get_json(force=True)
    ch = int(data.get("ch", 1))
    if ch not in SERVOS:
        return jsonify(ok=False, error="ch must be 1 or 2"), 400

    if "us" in data:
        us = clamp_us(int(data["us"]))
    elif "speed" in data:
        us = speed_to_us(ch, float(data["speed"]))
    else:
        return jsonify(ok=False, error="provide 'speed' or 'us'"), 400

    us = apply_with_slew(ch, us)
    return jsonify(ok=True, ch=ch, us=us)

@app.post("/stop")
def stop():
    for ch in SERVOS:
        _last_us[ch] = SERVOS[ch]["stop"]
        pi.set_servo_pulsewidth(SERVOS[ch]["gpio"], SERVOS[ch]["stop"])
    return jsonify(ok=True)

@app.post("/servo/trim")
def servo_trim():
    """
    Adjust neutral on the fly: {"ch":1, "delta_us": 2}  (use +/- until wheel truly stops)
    """
    data = request.get_json(force=True)
    ch = int(data.get("ch", 1))
    delta = int(data.get("delta_us", 0))
    if ch not in SERVOS:
        return jsonify(ok=False, error="ch must be 1 or 2"), 400
    SERVOS[ch]["stop"] = clamp_us(SERVOS[ch]["stop"] + delta)
    _last_us[ch] = SERVOS[ch]["stop"]
    pi.set_servo_pulsewidth(SERVOS[ch]["gpio"], SERVOS[ch]["stop"])
    return jsonify(ok=True, ch=ch, new_stop=SERVOS[ch]["stop"])

@app.get("/servo/status")
def servo_status():
    return jsonify(ok=True, config={ch: {"gpio": cfg["gpio"], "stop": cfg["stop"]}
                                    for ch, cfg in SERVOS.items()},
                   last_us=_last_us)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False, threaded=True)
