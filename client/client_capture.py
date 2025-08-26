#!/usr/bin/env python3
import os, io, time
from pathlib import Path
from datetime import datetime

import cv2
import requests
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont

# ===================== CONFIG =====================
PI_HOST    = "172.20.10.4"               # Pi IP/hostname
PORT       = 5000
API_BASE   = f"http://{PI_HOST}:{PORT}"
STREAM_URL = f"{API_BASE}/video_feed"
SAVE_DIR   = Path("D:/uni/ECE4179/project/client/imgs")  # default local save folder
WINDOW_TITLE = "Robot Control (Laptop UI)"
STREAM_RETRY_MS = 1500                   # retry interval while waiting
# ==================================================

SAVE_DIR.mkdir(parents=True, exist_ok=True)

def ts_filename(prefix="photo", ext="jpg"):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d-%H%M%S_%f')[:-3]}.{ext}"

def post_json(path, payload, timeout=2.0):
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_json(path, timeout=2.0):
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=timeout)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def banner_image(text_lines, w=640, h=480):
    """Create a dark placeholder image with centered lines of text."""
    img = Image.new("RGB", (w, h), (17, 17, 17))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    total_h = sum(draw.textbbox((0,0), t, font=font)[3] for t in text_lines) + 10*(len(text_lines)-1)
    y = (h - total_h) // 2
    for t in text_lines:
        tw = draw.textbbox((0,0), t, font=font)[2]
        x = (w - tw)//2
        draw.text((x, y), t, fill=(200,200,200), font=font)
        y += draw.textbbox((0,0), t, font=font)[3] + 10
    return img

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.geometry("1360x760")
        self.configure(bg="#111")

        # State
        self.cap = None
        self.connected = False
        self.running = True
        self.last_frame_bgr = None
        self.drive_pressed = set()
        self.save_dir = SAVE_DIR

        # ---- UI layout (top: live + last photo) ----
        top = tk.Frame(self, bg="#111")
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        self.live_panel = self._panel(top, "Live video")
        self.photo_panel = self._panel(top, "Last photo", add_take_button=True)

        # side-by-side
        self.live_panel["frame"].pack(side=tk.LEFT, padx=6)
        self.photo_panel["frame"].pack(side=tk.LEFT, padx=6)

        # ---- Controls (bottom) ----
        controls = tk.Frame(self, bg="#111")
        controls.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)

        tip = tk.Label(
            controls,
            text="Click window to focus. Arrow keys drive. Space saves a photo.",
            fg="#aaa", bg="#111"
        )
        tip.pack(pady=(0,8))

        btns = tk.Frame(controls, bg="#111"); btns.pack()
        self.btnFwd = self._btn(btns, "Forward (↑)",  lambda: self.drive(-1, -1)); self.btnFwd.pack(side=tk.LEFT, padx=4, pady=4)
        self.btnRev = self._btn(btns, "Reverse (↓)",  lambda: self.drive( 1,  1)); self.btnRev.pack(side=tk.LEFT, padx=4, pady=4)
        self.btnL   = self._btn(btns, "Pivot Left (←)",  lambda: self.drive(-1,  1)); self.btnL.pack(side=tk.LEFT, padx=4, pady=4)
        self.btnR   = self._btn(btns, "Pivot Right (→)", lambda: self.drive( 1, -1)); self.btnR.pack(side=tk.LEFT, padx=4, pady=4)
        self.btnStop= self._btn(btns, "Stop", self.stop); self.btnStop.pack(side=tk.LEFT, padx=4, pady=4)

        # Speed slider
        spd = tk.Frame(controls, bg="#111"); spd.pack(pady=(10,2))
        tk.Label(spd, text="Speed limit", fg="#eee", bg="#111").pack(side=tk.LEFT, padx=(0,8))
        self.spd_val = tk.StringVar(value="50%")
        tk.Label(spd, textvariable=self.spd_val, fg="#eee", bg="#111").pack(side=tk.LEFT, padx=8)
        self.spd = tk.Scale(spd, from_=0, to=100, orient="horizontal", length=260,
                            showvalue=False, command=self.on_speed_input, bg="#111",
                            troughcolor="#222", highlightthickness=0)
        self.spd.set(50); self.spd.pack(side=tk.LEFT)

        # Trim sliders
        trim = tk.Frame(controls, bg="#111"); trim.pack(pady=(10,2))
        tk.Label(trim, text="Wheel trim", fg="#eee", bg="#111").grid(row=0, column=0, columnspan=3, sticky="w")

        tk.Label(trim, text="Left", fg="#eee", bg="#111", width=6).grid(row=1, column=0, sticky="e", padx=4)
        self.trimL_val = tk.StringVar(value="1.00×")
        self.trimL = tk.Scale(trim, from_=50, to=120, orient="horizontal", length=260,
                              showvalue=False, command=self.on_trimL_input, bg="#111",
                              troughcolor="#222", highlightthickness=0)
        self.trimL.set(100); self.trimL.grid(row=1, column=1, padx=4)
        tk.Label(trim, textvariable=self.trimL_val, fg="#eee", bg="#111", width=6).grid(row=1, column=2, sticky="w")

        tk.Label(trim, text="Right", fg="#eee", bg="#111", width=6).grid(row=2, column=0, sticky="e", padx=4)
        self.trimR_val = tk.StringVar(value="1.00×")
        self.trimR = tk.Scale(trim, from_=50, to=120, orient="horizontal", length=260,
                              showvalue=False, command=self.on_trimR_input, bg="#111",
                              troughcolor="#222", highlightthickness=0)
        self.trimR.set(100); self.trimR.grid(row=2, column=1, padx=4)
        tk.Label(trim, textvariable=self.trimR_val, fg="#eee", bg="#111", width=6).grid(row=2, column=2, sticky="w")

        # Save location
        save = tk.Frame(controls, bg="#111"); save.pack(pady=(10,2))
        self._btn(save, "Choose folder…", self.choose_folder).pack(side=tk.LEFT, padx=4)
        self.save_label = tk.Label(save, text=f"Saving to: {self.save_dir}", fg="#aaa", bg="#111")
        self.save_label.pack(side=tk.LEFT, padx=8)

        # Status line
        self.status = tk.Label(controls, text="Waiting for server…", fg="#eee",
                               bg="#161616", bd=1, relief="solid", padx=8, pady=4)
        self.status.pack(pady=(10,0))

        # Key bindings
        self.bind("<KeyPress>",  self.on_key_press)
        self.bind("<KeyRelease>",self.on_key_release)
        self.focus_force()

        # Start with a waiting banner
        self.waiting_banner = banner_image(
            [ "Waiting for server…",
              f"URL: {STREAM_URL}",
              "Press Q to quit." ],
            640, 480
        )
        self.show_image(self.live_panel["image"], self.waiting_banner)

        # Pull initial status from Pi (won’t crash if down)
        self.init_from_pi()

        # Kick off loops
        self.after(100, self.video_loop)
        self.after(1000, self.pulse_status)

    # ---------- UI helpers ----------
    def _panel(self, parent, title, add_take_button=False):
        outer = tk.Frame(parent, bg="#111")
        frame = tk.Frame(outer, bg="#1a1a1a", highlightthickness=1)
        frame.config(highlightbackground="#333")
        header = tk.Frame(frame, bg="#1a1a1a")
        header.pack(fill=tk.X, padx=6, pady=(6,0))
        tk.Label(header, text=title, bg="#1a1a1a", fg="#ccc").pack(side=tk.LEFT)
        if add_take_button:
            self._btn(header, "Take Photo (Space)", self.take_photo).pack(side=tk.RIGHT)
        img_label = tk.Label(frame, bg="#1a1a1a")
        img_label.pack(padx=6, pady=6)
        frame.pack(padx=6, pady=6)
        return {"frame": outer, "image": img_label}

    def _btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg="#2b2b2b", fg="#eee",
                         activebackground="#373737", relief="raised", bd=1, padx=12, pady=6)

    # ---------- Image display ----------
    def show_image(self, label_widget, pil_image_or_bgr):
        if isinstance(pil_image_or_bgr, Image.Image):
            im = pil_image_or_bgr
        else:
            # BGR -> RGB
            rgb = cv2.cvtColor(pil_image_or_bgr, cv2.COLOR_BGR2RGB)
            im = Image.fromarray(rgb)
        # scale if wider than 640
        if im.width > 640:
            ratio = 640 / im.width
            im = im.resize((640, int(im.height * ratio)), Image.LANCZOS)
        imtk = ImageTk.PhotoImage(im)
        label_widget.imtk = imtk
        label_widget.configure(image=imtk)

    # ---------- Connection / video loop ----------
    def ensure_cap(self):
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(STREAM_URL)
            self.connected = self.cap.isOpened()

    def video_loop(self):
        if not self.running: return

        self.ensure_cap()
        if not self.connected:
            # still waiting
            self.show_image(self.live_panel["image"], self.waiting_banner)
            self.after(STREAM_RETRY_MS, self.video_loop)
            return

        ok, frame = self.cap.read()
        if not ok or frame is None:
            # lost stream -> back to waiting
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            self.connected = False
            self.status.config(text="Waiting for server…")
            self.show_image(self.live_panel["image"], self.waiting_banner)
            self.after(STREAM_RETRY_MS, self.video_loop)
            return

        self.last_frame_bgr = frame
        self.show_image(self.live_panel["image"], frame)
        self.after(10, self.video_loop)

    # Periodically poll /status (if reachable) to keep status line fresh
    def pulse_status(self):
        if not self.running: return
        j = get_json("/status", timeout=1.0)
        if j and j.get("ok"):
            L, R = j.get("left",{}), j.get("right",{})
            fmt = lambda x: f"{x:.2f}" if isinstance(x,(float,int)) else x
            self.status.config(text=f"L: dir {L.get('dir',0)} duty {fmt(L.get('duty',0))} | "
                                    f"R: dir {R.get('dir',0)} duty {fmt(R.get('duty',0))}")
        else:
            self.status.config(text="Waiting for server…")
        self.after(1000, self.pulse_status)

    # ---------- Controls / API ----------
    def drive(self, left, right):
        j = post_json("/drive", {"left": left, "right": right})
        if not j.get("ok"):
            self.status.config(text="Waiting for server…")
        else:
            self.update_status(j)

    def stop(self):
        j = post_json("/stop", {})
        if not j.get("ok"):
            self.status.config(text="Waiting for server…")
        else:
            self.update_status(j)

    def update_status(self, j):
        if not j: return
        if j.get("ok"):
            L, R = j.get("left",{}), j.get("right",{})
            fmt = lambda x: f"{x:.2f}" if isinstance(x,(float,int)) else x
            self.status.config(text=f"L: dir {L.get('dir',0)} duty {fmt(L.get('duty',0))} | "
                                    f"R: dir {R.get('dir',0)} duty {fmt(R.get('duty',0))}")
        else:
            self.status.config(text=f"Waiting for server…")

    def init_from_pi(self):
        st = get_json("/status")
        if not st or not st.get("ok"):
            # initialize UI defaults; actual values will sync once server is up
            self.spd.set(50); self.spd_val.set("50%")
            self.trimL.set(100); self.trimR.set(100)
            self.trimL_val.set("1.00×"); self.trimR_val.set("1.00×")
            return
        try:
            frac = float(st.get("speed_limit", 0.5))
            self.spd.set(int(round(frac*100)))
            self.spd_val.set(f"{int(round(frac*100))}%")
            trim = st.get("trim", {"L":1.0,"R":1.0})
            self.trimL.set(int(round(float(trim.get("L",1.0))*100)))
            self.trimR.set(int(round(float(trim.get("R",1.0))*100)))
            self.trimL_val.set(f"{self.trimL.get()/100:.2f}×")
            self.trimR_val.set(f"{self.trimR.get()/100:.2f}×")
        except Exception:
            pass

    # ---------- Sliders (debounced) ----------
    def on_speed_input(self, _):
        val = self.spd.get()
        self.spd_val.set(f"{val}%")
        if hasattr(self, "_spd_job"):
            self.after_cancel(self._spd_job)
        self._spd_job = self.after(200, lambda: post_json("/config/speed_limit",
                                                          {"speed_limit": val/100.0}))

    def on_trimL_input(self, _):
        self.trimL_val.set(f"{self.trimL.get()/100:.2f}×")
        if hasattr(self, "_trimL_job"):
            self.after_cancel(self._trimL_job)
        self._trimL_job = self.after(200, lambda: post_json("/config/trim",
                                                            {"L": self.trimL.get()/100.0}))
    def on_trimR_input(self, _):
        self.trimR_val.set(f"{self.trimR.get()/100:.2f}×")
        if hasattr(self, "_trimR_job"):
            self.after_cancel(self._trimR_job)
        self._trimR_job = self.after(200, lambda: post_json("/config/trim",
                                                            {"R": self.trimR.get()/100.0}))

    # ---------- Photos ----------
    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=str(self.save_dir), title="Choose save folder")
        if d:
            self.save_dir = Path(d)
            self.save_label.config(text=f"Saving to: {self.save_dir}")

    def take_photo(self):
        if self.last_frame_bgr is None:
            messagebox.showwarning("No frame", "No video frame available yet.")
            return
        self.save_dir.mkdir(parents=True, exist_ok=True)
        out = self.save_dir / ts_filename("photo", "jpg")
        ok = cv2.imwrite(str(out), self.last_frame_bgr)
        if ok:
            self.show_image(self.photo_panel["image"], self.last_frame_bgr)
            print(f"Saved: {out}")
        else:
            print("Failed to save image.")

    # ---------- Keyboard driving ----------
    def on_key_press(self, e):
        code = e.keysym
        if code in self.drive_pressed:  # ignore auto-repeat
            return
        if code in ("Up","Down","Left","Right","space"):
            self.drive_pressed.add(code)
        if code == "Up":    self.drive(-1, -1)
        if code == "Down":  self.drive( 1,  1)
        if code == "Left":  self.drive(1,  -1)
        if code == "Right": self.drive(-1, 1)
        if code == "space": self.take_photo()

    def on_key_release(self, e):
        code = e.keysym
        if code in self.drive_pressed:
            self.drive_pressed.discard(code)
        if not any(k in self.drive_pressed for k in ("Up","Down","Left","Right")):
            self.stop()

    # ---------- Cleanup ----------
    def on_close(self):
        self.running = False
        try: self.stop()
        except: pass
        try:
            if self.cap is not None:
                self.cap.release()
        except: pass
        self.destroy()

if __name__ == "__main__":
    App().mainloop()
