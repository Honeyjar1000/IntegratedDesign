# ------------- Servo -------------
def servo_set_angle(self, angle_deg: float):
    try:
        self.sio.emit("servo_set", {"angle": float(angle_deg)}, callback=self._on_ack_update_status)
    except Exception:
        pass

def servo_nudge_angle(self, delta_deg: float):
    try:
        self.sio.emit("servo_set", {"delta": float(delta_deg)}, callback=self._on_ack_update_status)
    except Exception:
        pass

def servo2_set_angle(self, angle_deg: float):
    try:
        self.sio.emit("servo2_set", {"angle": float(angle_deg)}, callback=self._on_ack_update_status)
    except Exception:
        pass

def servo2_nudge_angle(self, delta_deg: float):
    try:
        self.sio.emit("servo2_set", {"delta": float(delta_deg)}, callback=self._on_ack_update_status)
    except Exception:
        pass