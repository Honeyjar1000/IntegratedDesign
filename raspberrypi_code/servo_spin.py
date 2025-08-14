# ~/Documents/raspberrypi_code/spin_servo.py
#!/usr/bin/env python3
import time, argparse, sys
import pigpio

SERVO_PIN = 18  # change if you wired to another GPIO

def to_us(speed):  # speed in [-1.0 .. 1.0]
    us = 1500 + int(speed * 400)  # 1100..1900us typical for FS90R
    return max(1000, min(2000, us))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=0.6, help="-1..1 neg=reverse")
    ap.add_argument("--secs", type=float, default=1.0, help="run time seconds")
    args = ap.parse_args()

    pi = pigpio.pi()
    if not pi.connected:
        print("pigpio not running. Start it with: sudo systemctl start pigpiod", file=sys.stderr)
        sys.exit(1)

    pi.set_mode(SERVO_PIN, pigpio.OUTPUT)
    pi.set_servo_pulsewidth(SERVO_PIN, to_us(args.speed))
    time.sleep(args.secs)
    pi.set_servo_pulsewidth(SERVO_PIN, 1490)  # stop
    pi.stop()

if __name__ == "__main__":
    main()
