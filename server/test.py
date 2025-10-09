#!/usr/bin/env python3
import time
import pigpio

# --- Pin configuration (BCM numbers) ---
ENA_A, IN1_A, IN2_A = 12, 23, 24  # Left motor (Channel A)
ENA_B, IN3_B, IN4_B = 13, 19, 26  # Right motor (Channel B)
PWM_FREQ_HZ = 20000

# --- Setup ---
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpiod not running. Try: sudo systemctl start pigpiod")

for p in (ENA_A, IN1_A, IN2_A, ENA_B, IN3_B, IN4_B):
    pi.set_mode(p, pigpio.OUTPUT)
    pi.write(p, 0)

def motor_test(ena, in1, in2, name):
    print(f"\n--- Testing {name} ---")

    # Forward
    print("Forward...")
    pi.write(in1, 1)
    pi.write(in2, 0)
    pi.hardware_PWM(ena, PWM_FREQ_HZ, int(0.7 * 1_000_000))
    time.sleep(2)

    # Reverse
    print("Reverse...")
    pi.write(in1, 0)
    pi.write(in2, 1)
    pi.hardware_PWM(ena, PWM_FREQ_HZ, int(0.7 * 1_000_000))
    time.sleep(2)

    # Stop
    print("Stop.")
    pi.hardware_PWM(ena, 0, 0)
    pi.write(in1, 0)
    pi.write(in2, 0)
    time.sleep(1)

try:
    motor_test(ENA_A, IN1_A, IN2_A, "Motor A (Left)")
    motor_test(ENA_B, IN3_B, IN4_B, "Motor B (Right)")
finally:
    pi.hardware_PWM(ENA_A, 0, 0)
    pi.hardware_PWM(ENA_B, 0, 0)
    pi.write(IN1_A, 0); pi.write(IN2_A, 0)
    pi.write(IN3_B, 0); pi.write(IN4_B, 0)
    pi.stop()
    print("Test complete, GPIO released.")
