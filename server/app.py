#!/usr/bin/env python3
from flask import Flask, Response, request, jsonify
from picamera2 import Picamera2
import pigpio, cv2, time, atexit
from threading import Lock

app = Flask(__name__)

# ==================== Camera ====================
picam2 = Picamera2()
video_config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "XRGB8888"},
    controls={"FrameRate": 24}
)
picam2.configure(video_config)
picam2.start()
time.sleep(0.2)

_frame_lock = Lock()

def mjpeg_generator():
    """Continuous MJPEG stream for /video_feed."""
    while True:
        frame = picam2.capture_array()
        # keep flip if your camera is upside-down; change to flipCode=0/1/ -1 or remove as needed
        frame = cv2.flip(frame, -1)
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        ok, jpg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        with _frame_lock:
            jpeg = jpg.tobytes()
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")

@app.get("/video_feed")
def video_feed():
    return Response(mjpeg_generator(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.get("/health")
def health():
    return jsonify(ok=True, service="robot", camera=True)

# ==================== Motors: L298N dual channel ====================
# Physical channel A (OUT1/OUT2) pins:
ENA_A, IN1_A, IN2_A = 12, 23, 25     # BCM12, BCM23, BCM25
# Physical channel B (OUT3/OUT4) pins:
ENA_B, IN3_B, IN4_B = 13, 19, 26     # BCM13, BCM19, BCM26

PWM_FREQ_HZ = 15000       # ultrasonic (quiet)
DUTY_MIN    = 0.10        # minimum duty when moving
DUTY_MAX    = 1.00
BRAKE_TIME  = 0.06        # brief active brake on stop

SPEED_LIMIT = 0.50        # global speed cap 0..1

# Swap logical sides to match wiring: L -> B, R -> A
LOGICAL2PHYS = {"L": "B", "R": "A"}

# Polarity so "forward" (positive) drives robot forward
POLARITY = {"L": -1, "R": +1}

# Per-wheel trim for straightness
TRIM = {"L": 1.00, "R": 1.00}

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running. Try: sudo systemctl start pigpiod")

for p in (ENA_A, IN1_A, IN2_A, ENA_B, IN3_B, IN4_B):
    pi.set_mode(p, pigpio.OUTPUT)
    pi.write(p, 0)

_motor_lock = Lock()
_cur = {"L": {"dir": 0, "duty": 0.0}, "R": {"dir": 0, "duty": 0.0}}

def _duty_to_hw(d):
    d = max(DUTY_MIN, min(DUTY_MAX, float(d)))
    return int(d * 1_000_000)  # hardware_PWM duty units

def _pins_for(side):  # side is logical "L"/"R"
    phys = LOGICAL2PHYS[side]
    if phys == "A":
        return ENA_A, IN1_A, IN2_A
    else:
        return ENA_B, IN3_B, IN4_B

def _apply_one(side, direction, duty):
    ena, in1, in2 = _pins_for(side)
    if direction > 0:   # forward
        pi.write(in1, 1); pi.write(in2, 0)
    elif direction < 0: # reverse
        pi.write(in1, 0); pi.write(in2, 1)
    else:               # coast
        pi.write(in1, 0); pi.write(in2, 0)
    pi.hardware_PWM(ena, PWM_FREQ_HZ, _duty_to_hw(duty) if duty > 0 else 0)

def _set_speed_one(side, speed):
    global SPEED_LIMIT
    s = max(-1.0, min(1.0, float(speed)))
    s *= POLARITY[side]
    mag = abs(s) * max(0.0, min(1.0, float(SPEED_LIMIT))) * max(0.0, min(2.0, float(TRIM[side])))
    if mag < 1e-3:
        ena, in1, in2 = _pins_for(side)
        pi.hardware_PWM(ena, 0, 0); pi.write(in1, 0); pi.write(in2, 0)
        _cur[side]["dir"], _cur[side]["duty"] = 0, 0.0
        return _cur[side]
    direction = 1 if s > 0 else -1
    duty = DUTY_MIN + (DUTY_MAX - DUTY_MIN) * min(1.0, mag)
    _apply_one(side, direction, duty)
    _cur[side]["dir"], _cur[side]["duty"] = direction, duty
    return _cur[side]

def stop_all(brake=True):
    with _motor_lock:
        if brake:
            pi.write(IN1_A,1); pi.write(IN2_A,1); pi.hardware_PWM(ENA_A,0,0)
            pi.write(IN3_B,1); pi.write(IN4_B,1); pi.hardware_PWM(ENA_B,0,0)
            time.sleep(BRAKE_TIME)
        for ena, inA, inB in ((ENA_A, IN1_A, IN2_A), (ENA_B, IN3_B, IN4_B)):
            pi.write(inA, 0); pi.write(inB, 0)
            pi.hardware_PWM(ena, 0, 0)
        _cur["L"] = {"dir":0, "duty":0.0}
        _cur["R"] = {"dir":0, "duty":0.0}

# ------------- HTTP endpoints -------------
@app.post("/drive")
def drive():
    data = request.get_json(force=True)
    left  = float(data.get("left", 0))
    right = float(data.get("right", 0))
    with _motor_lock:
        stL = _set_speed_one("L", left)
        stR = _set_speed_one("R", right)
    return jsonify(ok=True, left=stL, right=stR, pwm_hz=PWM_FREQ_HZ)

@app.post("/stop")
def stop():
    stop_all(brake=True)
    return jsonify(ok=True, left=_cur["L"], right=_cur["R"])

@app.route("/config/speed_limit", methods=["GET", "POST"])
def config_speed_limit():
    global SPEED_LIMIT
    if request.method == "GET":
        return jsonify(ok=True, speed_limit=SPEED_LIMIT)
    data = request.get_json(silent=True) or {}
    try:
        v = float(data.get("speed_limit"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="speed_limit must be a number 0..1"), 400
    SPEED_LIMIT = max(0.0, min(1.0, v))
    return jsonify(ok=True, speed_limit=SPEED_LIMIT)

@app.route("/config/trim", methods=["GET", "POST"])
def config_trim():
    if request.method == "GET":
        return jsonify(ok=True, trim=TRIM)
    data = request.get_json(silent=True) or {}
    changed = {}
    for k in ("L","R"):
        if k in data:
            try:
                val = float(data[k])
            except (TypeError, ValueError):
                return jsonify(ok=False, error=f"{k} must be a number"), 400
            TRIM[k] = max(0.0, min(2.0, val))
            changed[k] = TRIM[k]
    return jsonify(ok=True, trim=TRIM, changed=changed)

@app.get("/status")
def status():
    return jsonify(
        ok=True,
        left=_cur["L"], right=_cur["R"],
        pwm_hz=PWM_FREQ_HZ,
        duty_min=DUTY_MIN, duty_max=DUTY_MAX,
        speed_limit=SPEED_LIMIT,
        trim=TRIM,
        map=LOGICAL2PHYS, polarity=POLARITY
    )

# ==================== Exit-time cleanup ====================
def _on_exit():
    try: stop_all(brake=False)
    except Exception: pass
    try: pi.stop()
    except Exception: pass

atexit.register(_on_exit)

if __name__ == "__main__":
    # Laptop app connects to http://<pi>:5000
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False, threaded=True)
