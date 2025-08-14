#!/usr/bin/env python3
from pynput import keyboard
import requests

PI = "http://192.168.0.122:8080"   # or "http://192.168.0.122:8080"
SPEED = 0.4                    # tweak to taste

pressed = set()

def send(speed):
    try:
        requests.post(f"{PI}/speed", json={"speed": speed}, timeout=0.25)
    except Exception:
        pass  # ignore quick hiccups

def on_press(key):
    if key == keyboard.Key.up and keyboard.Key.up not in pressed:
        pressed.add(keyboard.Key.up)
        send(SPEED)
    elif key == keyboard.Key.down and keyboard.Key.down not in pressed:
        pressed.add(keyboard.Key.down)
        send(-SPEED)
    elif key == keyboard.Key.esc:
        send(0.0)
        return False

def on_release(key):
    # If neither up nor down is held, stop (neutral)
    if key in (keyboard.Key.up, keyboard.Key.down) and key in pressed:
        pressed.remove(key)
        if not pressed:
            send(0.0)

print("Hold ↑ = forward, hold ↓ = reverse, release = stop.  Esc to quit.")
with keyboard.Listener(on_press=on_press, on_release=on_release) as L:
    L.join()
