#!/usr/bin/env python3
"""
Quiet DC motor driver for L298N Channel A using hardware PWM.
- ENA on BCM12 (phys 32), IN1=BCM23 (phys 16), IN2=BCM24 (phys 18)
- 25 kHz hardware PWM, duty clamped to >= 80% to avoid audible noise
- Slew-rate limited ramps and brief braking on direction changes
"""

import time
import pigpio

# ---- Pins (BCM numbers) ----
ENA = 12   # phys 32 (hardware PWM capable)
IN1 = 23   # phys 16
IN2 = 24   # phys 18

# ---- PWM config ----
PWM_FREQ_HZ = 25_000          # ultrasonic & quiet for you
DUTY_MIN = 0.80               # 80% = your quiet threshold
DUTY_MAX = 1.00
# hardware_PWM uses duty in millionths (0..1_000_000)
def duty_to_u16(d):  # helper
    d = max(DUTY_MIN, min(DUTY_MAX, d))
    return int(d * 1_000_000)

# ---- Motion profile ----
SLEW_STEP = 0.04              # duty step per tick (4%/tick)
SLEW_DT   = 0.02              # seconds between steps
BRAKE_TIME = 0.06             # brief active brake on reversals

class MotorA:
    """
    Speed command in [-1.0, 1.0].
    |speed| maps to duty in [DUTY_MIN, DUTY_MAX]; 0 = stop (coast).
    """
    def __init__(self, pi, ena, in1, in2):
        self.pi = pi
        self.ena, self.in1, self.in2 = ena, in1, in2
        for p in (ena, in1, in2):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.write(p, 0)
        self._dir = 0          # -1, 0, +1
        self._duty = 0.0       # 0..1

    def _apply(self, direction, duty):
        if direction > 0:
            self.pi.write(self.in1, 1); self.pi.write(self.in2, 0)
        elif direction < 0:
            self.pi.write(self.in1, 0); self.pi.write(self.in2, 1)
        else:
            self.pi.write(self.in1, 0); self.pi.write(self.in2, 0)  # coast
        self.pi.hardware_PWM(self.ena, PWM_FREQ_HZ, duty_to_u16(duty) if duty > 0 else 0)

    def set_speed(self, speed):
        # clamp & pick direction
        speed = max(-1.0, min(1.0, speed))
        target_dir = 0 if abs(speed) < 1e-3 else (1 if speed > 0 else -1)

        if target_dir == 0:
            # stop/coast
            self._apply(0, 0.0)
            self._dir, self._duty = 0, 0.0
            return

        # map |speed| -> duty in [DUTY_MIN, DUTY_MAX]
        target_duty = DUTY_MIN + (DUTY_MAX - DUTY_MIN) * abs(speed)

        # direction change? brief active brake for clean reversal
        if self._dir != 0 and target_dir != self._dir:
            # brake: both highs, PWM off
            self.pi.write(self.in1, 1); self.pi.write(self.in2, 1)
            self.pi.hardware_PWM(self.ena, 0, 0)
            time.sleep(BRAKE_TIME)

        # if currently stopped, jump straight to the minimum quiet duty in new dir
        if self._dir == 0 and self._duty == 0.0:
            self._dir = target_dir
            self._duty = DUTY_MIN
            self._apply(self._dir, self._duty)
            time.sleep(SLEW_DT)

        # slew duty toward target
        self._dir = target_dir
        duty = self._duty
        while abs(duty - target_duty) > 1e-6:
            if duty < target_duty:
                duty = min(duty + SLEW_STEP, target_duty)
            else:
                duty = max(duty - SLEW_STEP, target_duty)
            self._apply(self._dir, duty)
            time.sleep(SLEW_DT)
        self._duty = duty

    def stop(self, brake=False):
        if brake:
            self.pi.write(self.in1, 1); self.pi.write(self.in2, 1)
            self.pi.hardware_PWM(self.ena, 0, 0)
            time.sleep(BRAKE_TIME)
        # coast + PWM off
        self.pi.write(self.in1, 0); self.pi.write(self.in2, 0)
        self.pi.hardware_PWM(self.ena, 0, 0)
        self._dir, self._duty = 0, 0.0

if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpio daemon not running. Start it with: sudo pigpiod")

    m = MotorA(pi, ENA, IN1, IN2)
    try:
        # Demo: forward cruise, reverse cruise, then ramp
        print("Forward at quiet minimum (80%) for 2s...")
        m.set_speed(+1.0 * 0.0 + 1.0)   # command 1.0 (maps to >=80%)
        time.sleep(2)

        print("Reverse at quiet minimum (80%) for 2s...")
        m.set_speed(-1.0)               # reverse at >=80%
        time.sleep(2)

        print("Ramp up to full forward, then back to stop...")
        for s in [i/10 for i in range(8, 11)]:  # 0.8->1.0
            m.set_speed(+s)
            time.sleep(0.4)
        for s in [i/10 for i in range(10, 7, -1)]:  # 1.0->0.8
            m.set_speed(+s)
            time.sleep(0.4)
        m.stop(brake=True)
        print("Done.")

    except KeyboardInterrupt:
        print("Interrupted.")
    finally:
        m.stop()
        pi.stop()
