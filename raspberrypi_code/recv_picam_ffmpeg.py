#!/usr/bin/env python3
import subprocess, sys, numpy as np, cv2

PI_IP = "192.168.0.122"  # <- your Pi's IP
WIDTH, HEIGHT = 1280, 720  # <- must match libcamera-vid settings

cmd = [
    "ffmpeg",
    "-loglevel", "error",
    "-fflags", "nobuffer",
    "-flags", "low_delay",
    "-analyzeduration", "0",
    "-probesize", "32",
    "-i", f"tcp://{PI_IP}:8890",
    # decode and output raw BGR frames to stdout:
    "-f", "rawvideo",
    "-pix_fmt", "bgr24",
    "-"  # write to stdout
]

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=WIDTH*HEIGHT*3)
frame_bytes = WIDTH * HEIGHT * 3

try:
    while True:
        buf = proc.stdout.read(frame_bytes)
        if not buf or len(buf) < frame_bytes:
            break
        frame = np.frombuffer(buf, dtype=np.uint8).reshape((HEIGHT, WIDTH, 3))
        cv2.imshow("PiCam (Esc to quit)", frame)
        if cv2.waitKey(1) == 27:
            break
finally:
    proc.kill()
    cv2.destroyAllWindows()
