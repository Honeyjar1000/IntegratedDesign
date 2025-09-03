#!/usr/bin/env python3
# Socket.IO robot server for Raspberry Pi (no watchdog).
# Motors keep last setpoint until /stop or client disconnect.

import atexit, time, cv2, pigpio
from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from picamera2 import Picamera2
from threading import Lock

# ===== Tunables =====
VIDEO_FPS      = 12
JPEG_QUALITY   = 40
DOWNSCALE_TO   = (480, 360)   # None => keep native 640x480
APPLY_HZ       = 120          # motor apply loop

# ================= Server =================
app = Flask(__name__)
try:
    import eventlet  # preferred if installed
    ASYNC_MODE = "eventlet"
except Exception:
    ASYNC_MODE = "threading"

sio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=ASYNC_MODE,
    ping_interval=10, ping_timeout=30,
    async_handlers=True,
    logger=False, engineio_logger=False,
    max_http_buffer_size=20_000_000,
    engineio_options={"websocket_compression": False},  # JPEG won't compress further
)
print("async_mode =", sio.async_mode)

# ================= Camera =================
picam2 = None
_cam_lock = Lock()
_clients = set()

def ensure_camera(tries=10, delay=0.4):
    """Open Picamera2 lazily, retry if busy."""
    global picam2
    with _cam_lock:
        if picam2 is not None:
            return picam2
        last_err = None
        for _ in range(tries):
            try:
                cam = Picamera2()
                cfg = cam.create_video_configuration(
                    main={"size": (640, 480), "format": "XRGB8888"},
                    controls={"FrameRate": VIDEO_FPS},
                )
                cam.configure(cfg)
                cam.start()
                picam2 = cam
                return cam
            except Exception as e:
                last_err = e
                time.sleep(delay)
        raise RuntimeError(f"Could not acquire camera: {last_err}")

def stream_camera():
    """Capture -> (optional) resize -> JPEG -> emit newest only."""
    min_dt = 1.0 / max(1, VIDEO_FPS)
    while True:
        t0 = time.time()
        try:
            if _clients:
                cam = ensure_camera()
                frame = cam.capture_array()  # BGR888
                if DOWNSCALE_TO:
                    frame = cv2.resize(frame, DOWNSCALE_TO, interpolation=cv2.INTER_AREA)
                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                if ok:
                    sio.emit("video_frame", jpg.tobytes(), broadcast=True)
        except Exception:
            pass
        # pace to VIDEO_FPS without busy looping
        elapsed = time.time() - t0
        sio.sleep(max(0, min_dt - elapsed))

# ================= Motors (L298N) =================
# Channel A (OUT1/OUT2)
ENA_A, IN1_A, IN2_A = 12, 23, 25    # BCM12, BCM23, BCM25
# Channel B (OUT3/OUT4)
ENA_B, IN3_B, IN4_B = 13, 19, 26    # BCM13, BCM19, BCM26

PWM_FREQ_HZ = 22000
DUTY_MIN    = 0.12
DUTY_MAX    = 1.00
BRAKE_TIME  = 0.06

GAMMA           = 0.7
START_KICK_DUTY = 0.6
START_KICK_MS   = 70
SPEED_LIMIT     = 0.30

LOGICAL2PHYS = {"L": "B", "R": "A"}    # swap to match wiring
POLARITY     = {"L": -1, "R": +1}      # forward polarity
TRIM         = {"L": 1.00, "R": 1.00}

# Servo (MG90S) on BCM18
SERVO_PIN         = 24
SERVO_MIN_DEG     = 0
SERVO_MAX_DEG     = 90
SERVO_MIN_US      = 500
SERVO_MAX_US      = 2400
SERVO_DEFAULT_DEG = 90
SERVO_TRIM_US     = 0

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running. Try: sudo systemctl start pigpiod")

for p in (ENA_A, IN1_A, IN2_A, ENA_B, IN3_B, IN4_B):
    pi.set_mode(p, pigpio.OUTPUT)
    pi.write(p, 0)

_motor_lock = Lock()
_cur = {"L": {"dir": 0, "duty": 0.0}, "R": {"dir": 0, "duty": 0.0}}

pi.set_mode(SERVO_PIN, pigpio.OUTPUT)

def _clamp_deg(deg: float) -> float:
    return max(SERVO_MIN_DEG, min(SERVO_MAX_DEG, float(deg)))

def _deg_to_us(deg: float) -> int:
    deg = _clamp_deg(deg)
    us = SERVO_MIN_US + (SERVO_MAX_US - SERVO_MIN_US) * (deg / 180.0)
    return int(us + SERVO_TRIM_US)

SERVO_ANGLE_DEG = _clamp_deg(SERVO_DEFAULT_DEG)
pi.set_servo_pulsewidth(SERVO_PIN, _deg_to_us(SERVO_ANGLE_DEG))

def _duty_to_hw(d):  # 0..1 -> pigpio duty units
    d = max(DUTY_MIN, min(DUTY_MAX, float(d)))
    return int(d * 1_000_000)

def _pins_for(side):
    return (ENA_A, IN1_A, IN2_A) if LOGICAL2PHYS[side] == "A" else (ENA_B, IN3_B, IN4_B)

def _set_speed_one(side, speed):
    global SPEED_LIMIT
    s = max(-1.0, min(1.0, float(speed))) * POLARITY[side]
    mag = abs(s) * max(0.0, min(1.0, float(SPEED_LIMIT))) * max(0.0, min(2.0, float(TRIM[side])))

    if mag < 1e-3:
        ena, in1, in2 = _pins_for(side)
        pi.hardware_PWM(ena, 0, 0); pi.write(in1, 0); pi.write(in2, 0)
        _cur[side]["dir"], _cur[side]["duty"] = 0, 0.0
        return _cur[side]

    direction = 1 if s > 0 else -1
    mag_boosted = pow(mag, GAMMA)
    target_duty = DUTY_MIN + (DUTY_MAX - DUTY_MIN) * min(1.0, mag_boosted)

    ena, in1, in2 = _pins_for(side)
    if direction > 0: pi.write(in1, 1); pi.write(in2, 0)
    else:             pi.write(in1, 0); pi.write(in2, 1)

    was_stopped = (_cur[side]["duty"] <= 1e-6)
    if was_stopped:
        kick = max(target_duty, START_KICK_DUTY)
        pi.hardware_PWM(ena, PWM_FREQ_HZ, _duty_to_hw(kick))
        time.sleep(START_KICK_MS / 1000.0)

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

# ====== Socket.IO controls (NO WATCHDOG) ======
_drive_lock = Lock()
_last_drive = {"left": 0.0, "right": 0.0}  # no ts

@sio.on("connect")
def on_connect():
    _clients.add(request.sid)
    print("Client connected:", request.sid, "total:", len(_clients))
    if not hasattr(sio, "camera_task"):
        sio.camera_task = sio.start_background_task(stream_camera)
    if not hasattr(sio, "drive_task"):
        sio.drive_task = sio.start_background_task(_drive_apply_loop)
    #if not hasattr(sio, "status_task"):
    #    sio.status_task = sio.start_background_task(_status_broadcast_loop)

@sio.on("disconnect")
def on_disconnect():
    _clients.discard(request.sid)
    print("Client disconnected:", request.sid, "total:", len(_clients))
    # Safety: stop motors when a controlling client drops
    with _drive_lock:
        _last_drive.update(left=0.0, right=0.0)
    stop_all(brake=True)

@sio.on("drive")
def on_drive(data):
    try:
        L = float(data.get("left", 0.0))
        R = float(data.get("right", 0.0))
    except Exception as e:
        return {"ok": False, "error": f"bad payload: {e}"}
    with _drive_lock:
        _last_drive["left"], _last_drive["right"] = L, R
    return {"ok": True}

@sio.on("stop")
def on_stop():
    with _drive_lock:
        _last_drive["left"] = 0.0
        _last_drive["right"] = 0.0
    stop_all(brake=True)
    return {"ok": True, "left": _cur["L"], "right": _cur["R"]}

def _drive_apply_loop():
    """Continuously apply the latest setpoints (no watchdog)."""
    while True:
        with _drive_lock:
            L = _last_drive["left"]
            R = _last_drive["right"]
        with _motor_lock:
            _set_speed_one("L", L)
            _set_speed_one("R", R)
        sio.sleep(1 / APPLY_HZ)

# ----- status + config -----
@sio.on("get_status")
def on_get_status():
    try:
        return {
            "ok": True,
            "left": _cur["L"], "right": _cur["R"],
            "pwm_hz": PWM_FREQ_HZ,
            "duty_min": DUTY_MIN, "duty_max": DUTY_MAX,
            "speed_limit": SPEED_LIMIT,
            "trim": TRIM,
            "map": LOGICAL2PHYS, "polarity": POLARITY,
            "servo": {
                "pin": SERVO_PIN,
                "angle": SERVO_ANGLE_DEG,
                "us": _deg_to_us(SERVO_ANGLE_DEG),
                "min_deg": SERVO_MIN_DEG, "max_deg": SERVO_MAX_DEG,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@sio.on("set_speed_limit")
def on_set_speed_limit(data):
    try:
        v = float(data.get("speed_limit"))
        globals()["SPEED_LIMIT"] = max(0.0, min(1.0, v))
        return {"ok": True, "speed_limit": SPEED_LIMIT}
    except Exception as e:
        return {"ok": False, "error": "speed_limit must be 0..1: " + str(e)}

@sio.on("set_trim")
def on_set_trim(data):
    try:
        changed = {}
        for k in ("L", "R"):
            if k in data:
                val = float(data[k])
                TRIM[k] = max(0.0, min(2.0, val))
                changed[k] = TRIM[k]
        return {"ok": True, "trim": TRIM, "changed": changed}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@sio.on("servo_set")
def on_servo_set(data):
    try:
        global SERVO_ANGLE_DEG, SERVO_TRIM_US
        if "trim_us" in data:
            SERVO_TRIM_US = int(data["trim_us"])
        if "angle" in data:
            SERVO_ANGLE_DEG = _clamp_deg(float(data["angle"]))
        elif "delta" in data:
            SERVO_ANGLE_DEG = _clamp_deg(SERVO_ANGLE_DEG + float(data["delta"]))
        us = _deg_to_us(SERVO_ANGLE_DEG)
        pi.set_servo_pulsewidth(SERVO_PIN, us)
        return {"ok": True, "angle": SERVO_ANGLE_DEG, "us": us, "trim_us": SERVO_TRIM_US}
    except Exception as e:
        return {"ok": False, "error": str(e)}
'''
def _status_broadcast_loop():
    while True:
        try:
            if _clients:
                sio.emit("status", {
                    "left": _cur["L"], "right": _cur["R"],
                    "speed_limit": SPEED_LIMIT, "trim": TRIM,
                    "servo": {"angle": SERVO_ANGLE_DEG, "us": _deg_to_us(SERVO_ANGLE_DEG)},
                }, broadcast=True)
        except Exception:
            pass
        sio.sleep(0.3)
'''
# ================= Cleanup =================
def _on_exit():
    try:
        if picam2:
            picam2.stop()
    except Exception:
        pass
    try:
        pi.set_servo_pulsewidth(SERVO_PIN, _deg_to_us(SERVO_ANGLE_DEG))
    except Exception:
        pass
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
    sio.run(app, host="0.0.0.0", port=5000, debug=False)