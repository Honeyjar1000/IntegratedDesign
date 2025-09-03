#!/usr/bin/env python3
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk
import cv2
import numpy as np
import socketio
import threading

from config import WINDOW_TITLE, SAVE_DIR, LIVE_MAX_WIDTH, PHOTO_MAX_WIDTH, PI_HOST, API_BASE
from utils.images import ts_filename, banner_image, save_bgr



class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.geometry("1360x760")
        self.configure(bg="#111")

        # State
        self.connected = False
        self.running = True
        self.last_frame_bgr = None
        self.save_dir = SAVE_DIR
        self.servo_angle = 0.0
        self.drive_pressed = set()

        # debounce handles
        self._spd_job = None
        self._trimL_job = None
        self._trimR_job = None
        self._spd_job = None
        self._trimL_job = None

        # suppress programmatic slider->callback loops
        self._suppress_spd_cb = False

        # drop-frame render control
        self._render_busy = False
        self._latest_jpg = None

        # ---- UI: top row ----
        top = tk.Frame(self, bg="#111"); top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        self.live_panel      = self._panel(top, "Live video")
        self.annotated_panel = self._panel(top, "Annotated video")
        self.photo_panel     = self._panel(top, "Last photo", add_take_button=True)
        self.live_panel["frame"].pack(side=tk.LEFT, padx=6)
        self.annotated_panel["frame"].pack(side=tk.LEFT, padx=6)
        self.photo_panel["frame"].pack(side=tk.LEFT, padx=6)

        # ---- Controls ----
        controls = tk.Frame(self, bg="#111"); controls.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)

        tip = tk.Label(controls, text="Click window to focus. Arrow keys drive. Space saves a photo.",
                       fg="#aaa", bg="#111")
        tip.pack(pady=(0,8))

        btns = tk.Frame(controls, bg="#111"); btns.pack()
        self._btn(btns, "Forward (↑)",     lambda: self.drive(-1, -1)).pack(side=tk.LEFT, padx=4, pady=4)
        self._btn(btns, "Reverse (↓)",     lambda: self.drive( 1,  1)).pack(side=tk.LEFT, padx=4, pady=4)
        self._btn(btns, "Pivot Left (←)",  lambda: self.drive( 1, -1)).pack(side=tk.LEFT, padx=4, pady=4)
        self._btn(btns, "Pivot Right (→)", lambda: self.drive(-1,  1)).pack(side=tk.LEFT, padx=4, pady=4)
        self._btn(btns, "Stop", self.stop).pack(side=tk.LEFT, padx=4, pady=4)

        # Speed
        spd = tk.Frame(controls, bg="#111"); spd.pack(pady=(10,2))
        tk.Label(spd, text="Speed limit", fg="#eee", bg="#111").pack(side=tk.LEFT, padx=(0,8))
        self.spd_val = tk.StringVar(value="50%")
        tk.Label(spd, textvariable=self.spd_val, fg="#eee", bg="#111").pack(side=tk.LEFT, padx=8)
        self.spd = tk.Scale(spd, from_=0, to=100, orient="horizontal", length=260,
                            showvalue=False, command=self.on_speed_input, bg="#111",
                            troughcolor="#222", highlightthickness=0)
        self.spd.set(50); self.spd.pack(side=tk.LEFT)

        # Trim
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

        # Save folder
        save = tk.Frame(controls, bg="#111"); save.pack(pady=(10,2))
        self._btn(save, "Choose folder…", self.choose_folder).pack(side=tk.LEFT, padx=4)
        self.save_label = tk.Label(save, text=f"Saving to: {self.save_dir}", fg="#aaa", bg="#111")
        self.save_label.pack(side=tk.LEFT, padx=8)

        # Status
        self.status = tk.Label(controls, text="Connecting…", fg="#eee",
                               bg="#161616", bd=1, relief="solid", padx=8, pady=4)
        self.status.pack(pady=(10,0))

        # Keybindings
        self.bind("<KeyPress>",  self.on_key_press)
        self.bind("<KeyRelease>",self.on_key_release)
        self.focus_force()

        # Waiting banner
        self.waiting_banner = banner_image(
            ["Waiting for server…", "Press Q to quit."], w=LIVE_MAX_WIDTH, h=int(LIVE_MAX_WIDTH*0.75)
        )
        self._show_image(self.live_panel["image"], self.waiting_banner, maxw=LIVE_MAX_WIDTH)

        # ---- Socket.IO client ----
        self.sio = socketio.Client(reconnection=True, logger=False, engineio_logger=False)

        @self.sio.event
        def connect():
            self.connected = True
            self._ui_status(f"Connected to {PI_HOST}")
            try:
                self.sio.emit("get_status", callback=self._on_ack_update_status)
            except Exception:
                pass

        @self.sio.event
        def disconnect():
            self.connected = False
            self._ui_status("Disconnected — retrying…")
            self.after(0, lambda: self._show_image(self.live_panel["image"], self.waiting_banner, maxw=LIVE_MAX_WIDTH))

        @self.sio.event
        def connect_error(err):
            self._ui_status(f"Connect error: {err}")

        @self.sio.on("status")
        def on_status(data):
            self.after(0, lambda d=data: self._apply_status_dict(d))

        @self.sio.on("video_frame")
        def on_video_frame(jpg_bytes):
            # drop old frames, render most recent
            self._latest_jpg = jpg_bytes
            if not self._render_busy:
                self._render_busy = True
                self.after(0, self._drain_and_render)

        # Connect in background so Tk never blocks
        threading.Thread(
            target=lambda: self.sio.connect(API_BASE, namespaces=['/'], transports=['websocket'], wait_timeout=10),
            daemon=True
        ).start()

        # Poll status every second (server also broadcasts)
        self.after(1000, self.poll_status)

    # ---------- UI basics ----------
    def _panel(self, parent, title, add_take_button=False):
        outer = tk.Frame(parent, bg="#111")
        frame = tk.Frame(outer, bg="#1a1a1a", highlightthickness=1)
        frame.config(highlightbackground="#333")
        header = tk.Frame(frame, bg="#1a1a1a"); header.pack(fill=tk.X, padx=6, pady=(6,0))
        tk.Label(header, text=title, bg="#1a1a1a", fg="#ccc").pack(side=tk.LEFT)
        if add_take_button:
            self._btn(header, "Take Photo (Space)", self.take_photo).pack(side=tk.RIGHT)
        img_label = tk.Label(frame, bg="#1a1a1a"); img_label.pack(padx=6, pady=6)
        frame.pack(padx=6, pady=6)
        return {"frame": outer, "image": img_label}

    def _btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg="#2b2b2b", fg="#eee",
                         activebackground="#373737", relief="raised", bd=1, padx=12, pady=6)

    def _show_image(self, label_widget, bgr_or_pil, maxw: int):
        if isinstance(bgr_or_pil, Image.Image):
            im = bgr_or_pil
        else:
            bgr = bgr_or_pil
            #bgr = cv2.flip(bgr, -1)
            h, w = bgr.shape[:2]
            if w > maxw:
                scale = maxw / w
                bgr = cv2.resize(bgr, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            im = Image.fromarray(rgb)
        imtk = ImageTk.PhotoImage(im)
        label_widget.imtk = imtk
        label_widget.configure(image=imtk)

    def _ui_status(self, text):
        self.after(0, lambda t=text: self.status.config(text=t))

    # ---------- drop-frame render ----------
    def _drain_and_render(self):
        data = self._latest_jpg
        self._latest_jpg = None
        if data is not None:
            np_arr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is not None:
                self.last_frame_bgr = frame
                self._show_image(self.live_panel["image"], frame, maxw=LIVE_MAX_WIDTH)
        if self._latest_jpg is not None:
            self.after(0, self._drain_and_render)
        else:
            self._render_busy = False

    # ---------- Status ----------
    def poll_status(self):
        if self.running and self.connected:
            try:
                self.sio.emit("get_status", callback=self._on_ack_update_status)
            except Exception:
                pass
        if self.running:
            self.after(1000, self.poll_status)

    def _on_ack_update_status(self, data):
        self.after(0, lambda d=data: self._apply_status_dict(d))

    def _apply_status_dict(self, st: dict):
        if not isinstance(st, dict) or not st.get("ok", True):
            return

        # status text (safe)
        L, R = st.get("left", {}), st.get("right", {})
        fmt = lambda x: f"{x:.2f}" if isinstance(x, (float, int)) else x
        self.status.config(
            text=f"L: dir {L.get('dir',0)} duty {fmt(L.get('duty',0))} | "
                f"R: dir {R.get('dir',0)} duty {fmt(R.get('duty',0))}"
        )

        try:
            # --- speed limit: only if server sent it ---
            if "speed_limit" in st:
                frac = float(st["speed_limit"])
                pct = int(round(frac * 100))
                self._suppress_spd_cb = True
                try:
                    self.spd.set(pct)
                finally:
                    self._suppress_spd_cb = False
                self.spd_val.set(f"{pct}%")

            # --- trims: only if present ---
            if "trim" in st and isinstance(st["trim"], dict):
                trim = st["trim"]
                if "L" in trim:
                    v = int(round(float(trim["L"]) * 100))
                    self.trimL.set(v); self.trimL_val.set(f"{v/100:.2f}×")
                if "R" in trim:
                    v = int(round(float(trim["R"]) * 100))
                    self.trimR.set(v); self.trimR_val.set(f"{v/100:.2f}×")

            # --- servo: only if present ---
            if isinstance(st.get("servo"), dict) and "angle" in st["servo"]:
                self.servo_angle = float(st["servo"]["angle"])

        except Exception:
            pass
        
    # ---------- Sliders (DEBOUNCED HANDLERS) ----------
    def on_speed_input(self, _):
        if getattr(self, "_suppress_spd_cb", False):
            return  # ignore updates caused by programmatic .set()
        val = self.spd.get()
        self.spd_val.set(f"{val}%")
        if self._spd_job:
            self.after_cancel(self._spd_job)
        self._spd_job = self.after(150, lambda: self._emit_set_speed_limit(val/100.0))

    def _emit_set_speed_limit(self, frac):
        try:
            self.sio.emit("set_speed_limit",
                        {"speed_limit": float(frac)},
                        callback=self._on_ack_update_status)
        except Exception:
            pass

    def on_trimL_input(self, _):
        self.trimL_val.set(f"{self.trimL.get()/100:.2f}×")
        if self._trimL_job:
            self.after_cancel(self._trimL_job)
        self._trimL_job = self.after(
            150,
            lambda: self._emit_set_trim("L", self.trimL.get()/100.0)
        )

    def on_trimR_input(self, _):
        self.trimR_val.set(f"{self.trimR.get()/100:.2f}×")
        if self._trimR_job:
            self.after_cancel(self._trimR_job)
        self._trimR_job = self.after(
            150,
            lambda: self._emit_set_trim("R", self.trimR.get()/100.0)
        )

    def _emit_set_trim(self, side, val):
        try:
            self.sio.emit("set_trim", {side: float(val)}, callback=self._on_ack_update_status)
        except Exception:
            pass

    # ---------- Controls ----------
    def drive(self, left, right):
        try:
            self.sio.emit("drive", {"left": float(left), "right": float(right)})
        except Exception:
            self._ui_status("drive error")

    def stop(self):
        try:
            self.sio.emit("stop", callback=self._on_ack_update_status)
        except Exception:
            self._ui_status("stop error")

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
        out = self.save_dir / ts_filename("photo", "jpg")
        if save_bgr(self.last_frame_bgr, out):
            self._show_image(self.photo_panel["image"], self.last_frame_bgr, maxw=PHOTO_MAX_WIDTH)
            print(f"Saved: {out}")
        else:
            print("Failed to save image.")

    # ---------- Keyboard ----------
    def on_key_press(self, e):
        code = e.keysym
        if code in ("Up","Down","Left","Right"):
            if code in self.drive_pressed:
                return
            self.drive_pressed.add(code)
            if code == "Up":    self.drive(1, 1)
            if code == "Down":  self.drive( -1,  -1)
            if code == "Left":  self.drive( -1, 1)
            if code == "Right": self.drive(1,  -1)
            return
        if code == "space":
            self.take_photo(); return
        STEP_DEG = 3.0
        if code in ("w","W"):
            self.servo_nudge_angle(-STEP_DEG)
        elif code in ("s","S"):
            self.servo_nudge_angle(+STEP_DEG)
        elif code in ("q","Q"):
            self.on_close()

    def on_key_release(self, e):
        code = e.keysym
        if code in self.drive_pressed:
            self.drive_pressed.discard(code)
        if not any(k in self.drive_pressed for k in ("Up","Down","Left","Right")):
            self.stop()

    # ---------- Servo ----------
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

    # ---------- Cleanup ----------
    def on_close(self):
        self.running = False
        try: self.stop()
        except: pass
        try: self.sio.disconnect()
        except: pass
        self.destroy()