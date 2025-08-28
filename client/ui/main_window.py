import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image
import cv2
from PIL import ImageTk

from config import (WINDOW_TITLE, SAVE_DIR, STREAM_RETRY_MS, LIVE_MAX_WIDTH, PHOTO_MAX_WIDTH)
from services.api import post_json, get_json
from services.stream import StreamClient
from utils.images import (ts_filename, pil_from_bgr, resize_to_width, banner_image, save_bgr)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.geometry("1360x760")
        self.configure(bg="#111")

        # State
        self.stream  = StreamClient()
        self.connected = False
        self.running = True
        self.last_frame_bgr = None
        self.drive_pressed = set()
        self.save_dir = SAVE_DIR

        # ---- UI: top row ----
        top = tk.Frame(self, bg="#111"); top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        self.live_panel  = self._panel(top, "Live video")
        self.photo_panel = self._panel(top, "Last photo", add_take_button=True)

        self.live_panel["frame"].pack(side=tk.LEFT, padx=6)
        self.photo_panel["frame"].pack(side=tk.LEFT, padx=6)

        # ---- Controls ----
        controls = tk.Frame(self, bg="#111"); controls.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)

        tip = tk.Label(controls, text="Click window to focus. Arrow keys drive. Space saves a photo.",
                       fg="#aaa", bg="#111")
        tip.pack(pady=(0,8))

        btns = tk.Frame(controls, bg="#111"); btns.pack()
        self._btn(btns, "Forward (↑)",    lambda: self.drive(-1, -1)).pack(side=tk.LEFT, padx=4, pady=4)
        self._btn(btns, "Reverse (↓)",    lambda: self.drive( 1,  1)).pack(side=tk.LEFT, padx=4, pady=4)
        self._btn(btns, "Pivot Left (←)", lambda: self.drive(-1,  1)).pack(side=tk.LEFT, padx=4, pady=4)
        self._btn(btns, "Pivot Right (→)",lambda: self.drive( 1, -1)).pack(side=tk.LEFT, padx=4, pady=4)
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
        self.status = tk.Label(controls, text="Waiting for server…", fg="#eee",
                               bg="#161616", bd=1, relief="solid", padx=8, pady=4)
        self.status.pack(pady=(10,0))

        # Keybindings
        self.bind("<KeyPress>",  self.on_key_press)
        self.bind("<KeyRelease>",self.on_key_release)
        self.focus_force()

        # Waiting banner + initial status
        self.waiting_banner = banner_image(
            ["Waiting for server…", "Press Q to quit."], w=LIVE_MAX_WIDTH, h=int(LIVE_MAX_WIDTH*0.75)
        )
        self._show_image(self.live_panel["image"], self.waiting_banner, maxw=LIVE_MAX_WIDTH)
        self.init_from_pi()

        # Loops
        self.after(100, self.video_loop)
        self.after(1000, self.pulse_status)

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

    def _show_image(self, label_widget, bgr, maxw: int):
        # bgr can be a PIL Image (banner) or a NumPy BGR frame
        if isinstance(bgr, Image.Image):
            im = bgr
        else:
            # 🔽 flip here if you want 180° rotation
            bgr = cv2.flip(bgr, -1)   # -1 = flip both axes (same as your Pi side did)
            # if you just want horizontal mirror: cv2.flip(bgr, 1)
            # if just vertical flip: cv2.flip(bgr, 0)

            h, w = bgr.shape[:2]
            if w > maxw:
                scale = maxw / w
                bgr = cv2.resize(bgr, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            im = Image.fromarray(rgb)

        imtk = ImageTk.PhotoImage(im)
        label_widget.imtk = imtk
        label_widget.configure(image=imtk)

    # ---------- Connection / stream loop ----------
    def video_loop(self):
        """Fetch frame with minimal buffering and update the UI.
        Falls back to a waiting banner while the server is down."""
        if not self.running:
            return

        # Ensure stream is open (or keep waiting)
        if not self.stream.is_open() and not self.stream.open():
            self._show_image(self.live_panel["image"], self.waiting_banner, maxw=LIVE_MAX_WIDTH)
            self.status.config(text="Waiting for server…")
            self.after(STREAM_RETRY_MS, self.video_loop)
            return

        # Read one (fresh) frame; if it fails, go back to waiting
        ok, frame = self.stream.read()
        if not ok or frame is None:
            self.stream.close()
            self.status.config(text="Waiting for server…")
            self._show_image(self.live_panel["image"], self.waiting_banner, maxw=LIVE_MAX_WIDTH)
            self.after(STREAM_RETRY_MS, self.video_loop)
            return

        # Success: show newest frame and schedule next iteration
        self.last_frame_bgr = frame
        self._show_image(self.live_panel["image"], frame, maxw=LIVE_MAX_WIDTH)
        self.after(10, self.video_loop)  # request ~100 fps; Tk will cap effectively, keeps latency low

    def pulse_status(self):
        if not self.running:
            return
        j = get_json("/status", timeout=1.0)
        if j and j.get("ok"):
            L, R = j.get("left",{}), j.get("right",{})
            fmt = lambda x: f"{x:.2f}" if isinstance(x,(float,int)) else x
            self.status.config(text=f"L: dir {L.get('dir',0)} duty {fmt(L.get('duty',0))} | "
                                    f"R: dir {R.get('dir',0)} duty {fmt(R.get('duty',0))}")
        else:
            self.status.config(text="Waiting for server…")
        self.after(1000, self.pulse_status)

    # ---------- API / controls ----------
    def drive(self, left, right):
        j = post_json("/drive", {"left": left, "right": right})
        if j.get("ok"):
            self.update_status(j)
        else:
            self.status.config(text="Waiting for server…")

    def stop(self):
        j = post_json("/stop", {})
        if j.get("ok"):
            self.update_status(j)
        else:
            self.status.config(text="Waiting for server…")

    def update_status(self, j):
        if not j: return
        if j.get("ok"):
            L, R = j.get("left",{}), j.get("right",{})
            fmt = lambda x: f"{x:.2f}" if isinstance(x,(float,int)) else x
            self.status.config(text=f"L: dir {L.get('dir',0)} duty {fmt(L.get('duty',0))} | "
                                    f"R: dir {R.get('dir',0)} duty {fmt(R.get('duty',0))}")
        else:
            self.status.config(text="Waiting for server…")

    def init_from_pi(self):
        st = get_json("/status")
        if not st or not st.get("ok"):
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

    # ---------- Sliders ----------
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
        out = self.save_dir / ts_filename("photo", "jpg")
        if save_bgr(self.last_frame_bgr, out):
            self._show_image(self.photo_panel["image"], self.last_frame_bgr, maxw=PHOTO_MAX_WIDTH)
            print(f"Saved: {out}")
        else:
            print("Failed to save image.")

    # ---------- Keyboard ----------
    def on_key_press(self, e):
        code = e.keysym
        if code in self.drive_pressed:  # ignore auto-repeat
            return
        if code in ("Up","Down","Left","Right","space"):
            self.drive_pressed.add(code)
        if code == "Up":    self.drive(-1, -1)
        if code == "Down":  self.drive( 1,  1)
        if code == "Left":  self.drive( 1, -1)
        if code == "Right": self.drive(-1,  1)
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
        self.stream.close()
        self.destroy()
