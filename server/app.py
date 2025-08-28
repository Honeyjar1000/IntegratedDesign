#!/usr/bin/env python3
from flask import Flask, Response, request, jsonify
from picamera2 import Picamera2
import pigpio, cv2, time, atexit
from threading import Lock

app = Flask(__name__)

# ==================== Camera ====================
# XRGB8888 or BGR888
picam2 = Picamera2()
video_config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "XRGB8888"},
    controls={"FrameRate": 24} # can lower this 15-18? to decrease latency?
)
picam2.configure(video_config)
picam2.start()
time.sleep(0.2)

_frame_lock = Lock()

def mjpeg_generator():
    global _last_jpeg
    while True:
        frame_bgr = picam2.capture_array()  # already BGR888
        # remove if you don’t need it:
        # frame_bgr = cv2.flip(frame_bgr, -1)

        # Lower bitrate -> lower live latency
        ok, jpg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if not ok:
            continue
        with _frame_lock:
            _last_jpeg = jpg.tobytes()
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _last_jpeg + b"\r\n")

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

PWM_FREQ_HZ = 22000       # ultrasonic (quiet)
DUTY_MIN    = 0.12        # minimum duty when moving
DUTY_MAX    = 1.00
BRAKE_TIME  = 0.06        # brief active brake on stop

GAMMA         = 0.7        # nonlinear boost: duty ~ mag**GAMMA (0.5–0.8 good)
START_KICK_DUTY = 0.6     # brief “kick” duty to overcome static friction
START_KICK_MS   = 70      # kick duration in ms
SPEED_LIMIT = 0.30        # global speed cap 0..1

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
    """
    speed in [-1,1]; applies polarity, speed limit, trim.
    Ultrasonic PWM (quiet) + short soft-start kick + non-linear low-end mapping.
    """
    global SPEED_LIMIT
    s = max(-1.0, min(1.0, float(speed)))
    s *= POLARITY[side]

    # Compose magnitude with caps
    mag = abs(s)
    mag *= max(0.0, min(1.0, float(SPEED_LIMIT)))
    mag *= max(0.0, min(2.0, float(TRIM[side])))

    # Stop if effectively zero
    if mag < 1e-3:
        ena, in1, in2 = _pins_for(side)
        pi.hardware_PWM(ena, 0, 0); pi.write(in1, 0); pi.write(in2, 0)
        _cur[side]["dir"], _cur[side]["duty"] = 0, 0.0
        return _cur[side]

    direction = 1 if s > 0 else -1

    # Nonlinear boost: keeps tiny inputs usable while preserving range
    mag_boosted = pow(mag, GAMMA)  # e.g., 0.25 -> ~0.36 with GAMMA=0.7

    # Map to duty with a minimum floor
    target_duty = DUTY_MIN + (DUTY_MAX - DUTY_MIN) * min(1.0, mag_boosted)

    ena, in1, in2 = _pins_for(side)
    if direction > 0:
        pi.write(in1, 1); pi.write(in2, 0)
    else:
        pi.write(in1, 0); pi.write(in2, 1)

    # If previously stopped, give a very short ultrasonic kick
    was_stopped = (_cur[side]["duty"] <= 1e-6)
    if was_stopped:
        kick = max(target_duty, START_KICK_DUTY)
        pi.hardware_PWM(ena, PWM_FREQ_HZ, _duty_to_hw(kick))
        time.sleep(START_KICK_MS / 1000.0)

    # Hold at the quiet target duty
    pi.hardware_PWM(ena, PWM_FREQ_HZ, _duty_to_hw(target_duty))
    _cur[side]["dir"], _cur[side]["duty"] = direction, target_duty
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
