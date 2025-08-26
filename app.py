#!/usr/bin/env python3
from flask import Flask, render_template, Response, request, jsonify
from picamera2 import Picamera2
import pigpio, cv2, time, os, atexit
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

_last_jpeg = None
_frame_lock = Lock()

def mjpeg_generator():
    global _last_jpeg
    while True:
        frame = picam2.capture_array()
        frame = cv2.flip(frame, -1)  # 180° rotate if camera inverted
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        ok, jpg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        with _frame_lock:
            _last_jpeg = jpg.tobytes()
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _last_jpeg + b"\r\n")

@app.route("/video_feed")
def video_feed():
    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/photo", methods=["GET", "POST"])
def take_photo():
    os.makedirs("imgs", exist_ok=True)
    name = request.args.get("name")
    if request.is_json:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict):
            name = body.get("name", name)

    ts = time.strftime("%Y%m%d-%H%M%S")
    base = ts
    if name:
        safe = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
        if safe:
            base += f"_{safe}"
    path = os.path.join("imgs", base + ".jpg")

    with _frame_lock:
        jpeg_bytes = _last_jpeg

    if jpeg_bytes is None:
        frame = picam2.capture_array()
        frame = cv2.flip(frame, -1)
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        ok, jpg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            return jsonify(ok=False, error="encode failed"), 500
        jpeg_bytes = jpg.tobytes()

    with open(path, "wb") as f:
        f.write(jpeg_bytes)

    return jsonify(ok=True, saved=path, bytes=len(jpeg_bytes))

# ==================== Motors: L298N dual channel ====================
# LEFT motor (Channel A: OUT1/OUT2)
ENA_L, IN1_L, IN2_L = 12, 23, 25     # BCM12(phys32), BCM23(16), BCM24(18)
# RIGHT motor (Channel B: OUT3/OUT4)
ENA_R, IN3_R, IN4_R = 13, 19, 26     # BCM13(33), BCM19(35), BCM26(37)

PWM_FREQ_HZ = 15000       # ultrasonic (quiet)
DUTY_MIN = 0.10            # 80% is your quiet threshold (per your tests)
DUTY_MAX = 1.00
BRAKE_TIME = 0.06          # brief active brake on stop

POLARITY = {"L": -1, "R": +1}

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running. Try: sudo systemctl start pigpiod")

for p in (ENA_L, IN1_L, IN2_L, ENA_R, IN3_R, IN4_R):
    pi.set_mode(p, pigpio.OUTPUT)
    pi.write(p, 0)

_motor_lock = Lock()
# State
_cur = {
    "L": {"dir": 0, "duty": 0.0},
    "R": {"dir": 0, "duty": 0.0},
}

def _duty_to_hw(d):
    d = max(DUTY_MIN, min(DUTY_MAX, float(d)))
    return int(d * 1_000_000)  # hardware_PWM duty units

def _apply_one(side, direction, duty):
    """Immediately apply direction & duty to one motor and HOLD it."""
    if side == "L":
        ena, in1, in2 = ENA_L, IN1_L, IN2_L
    else:
        ena, in1, in2 = ENA_R, IN3_R, IN4_R

    if direction > 0:   # forward
        pi.write(in1, 1); pi.write(in2, 0)
    elif direction < 0: # reverse
        pi.write(in1, 0); pi.write(in2, 1)
    else:               # coast
        pi.write(in1, 0); pi.write(in2, 0)

    pi.hardware_PWM(ena, PWM_FREQ_HZ, _duty_to_hw(duty) if duty > 0 else 0)

def _set_speed_one(side, speed):
    """speed in [-1,1]; maps to duty [DUTY_MIN..DUTY_MAX]; 0 = stop."""
    s = max(-1.0, min(1.0, float(speed)))
    # apply per-motor polarity so 'forward' means both wheels push the robot forward
    s *= POLARITY[side]

    if abs(s) < 1e-3:
        if side == "L":
            pi.hardware_PWM(ENA_L, 0, 0); pi.write(IN1_L, 0); pi.write(IN2_L, 0)
        else:
            pi.hardware_PWM(ENA_R, 0, 0); pi.write(IN3_R, 0); pi.write(IN4_R, 0)
        _cur[side]["dir"], _cur[side]["duty"] = 0, 0.0
        return _cur[side]

    direction = 1 if s > 0 else -1
    duty = DUTY_MIN + (DUTY_MAX - DUTY_MIN) * abs(s)
    _apply_one(side, direction, duty)
    _cur[side]["dir"], _cur[side]["duty"] = direction, duty
    return _cur[side]

def stop_all(brake=True):
    with _motor_lock:
        if brake:
            # active brake both briefly
            pi.write(IN1_L,1); pi.write(IN2_L,1); pi.hardware_PWM(ENA_L,0,0)
            pi.write(IN3_R,1); pi.write(IN4_R,1); pi.hardware_PWM(ENA_R,0,0)
            time.sleep(BRAKE_TIME)
        # coast + PWM off
        for ena, inA, inB in ((ENA_L, IN1_L, IN2_L), (ENA_R, IN3_R, IN4_R)):
            pi.write(inA, 0); pi.write(inB, 0)
            pi.hardware_PWM(ena, 0, 0)
        _cur["L"] = {"dir":0, "duty":0.0}
        _cur["R"] = {"dir":0, "duty":0.0}

# ------------- HTTP endpoints -------------
@app.post("/drive")
def drive():
    """
    Tank drive:
      JSON: {"left": -1..1, "right": -1..1}
      Holds until /stop or next /drive call.
    """
    data = request.get_json(force=True)
    left = float(data.get("left", 0))
    right = float(data.get("right", 0))
    with _motor_lock:
        stL = _set_speed_one("L", left)
        stR = _set_speed_one("R", right)
    return jsonify(ok=True, left=stL, right=stR, pwm_hz=PWM_FREQ_HZ)

@app.post("/stop")
def stop():
    stop_all(brake=True)
    return jsonify(ok=True, left=_cur["L"], right=_cur["R"])

@app.get("/diag")
def diag():
    side = request.args.get("side","L").upper()
    if side not in ("L","R"): return jsonify(ok=False,error="side must be L or R"),400
    if side=="L": ena,in1,in2 = ENA_L,IN1_L,IN2_L
    else:         ena,in1,in2 = ENA_R,IN3_R,IN4_R

    def pulse(tag, a, b):
        pi.hardware_PWM(ena,0,0); pi.write(in1,0); pi.write(in2,0); time.sleep(0.05)
        pi.write(in1,a); pi.write(in2,b)
        pi.hardware_PWM(ena, PWM_FREQ_HZ, _duty_to_hw(0.8)); time.sleep(1.0)
        pi.hardware_PWM(ena,0,0)
        return {"tag":tag,"in1_set":a,"in2_set":b,"in1_read":int(pi.read(in1)),"in2_read":int(pi.read(in2))}
    fwd = pulse("forward",1,0)
    rev = pulse("reverse",0,1)
    pi.write(in1,0); pi.write(in2,0)
    return jsonify(ok=True, side=side, forward=fwd, reverse=rev)


@app.get("/status")
def status():
    return jsonify(ok=True, left=_cur["L"], right=_cur["R"], pwm_hz=PWM_FREQ_HZ,
                   duty_min=DUTY_MIN, duty_max=DUTY_MAX)

@app.route("/")
def index():
    return render_template("index.html")

# ==================== Exit-time cleanup ====================
def _on_exit():
    try:
        stop_all(brake=False)
    except Exception:
        pass
    try:
        pi.stop()
    except Exception:
        pass

atexit.register(_on_exit)

if __name__ == "__main__":
    # Do NOT stop on startup; we want it to keep running after /drive until /stop
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False, threaded=True)
