# ------------- Controls -------------
def drive(self, left, right):
    try:
        payload = {
            "left": float(left),
            "right": float(right),
            "client_ts": time.time()
        }

        def on_callback(data):
            ''' Handler for the app server callback 
            '''
            client_ts = data.get("client_ts")
            if client_ts is not None:
                curr_ts = time.time()
                latency = (curr_ts - client_ts) * 500 # * 1000 for ms, /2 for round trip
                self._ui_status(f"Last motor latency: {latency:.1f} ms")

        # Emit data and wait for latency callback from the app server
        self.sio.emit("drive", payload, callback=on_callback)
    except Exception:
        self._ui_status("drive error")

def stop(self):
    try:
        self.sio.emit("stop", callback=self._on_ack_update_status)
    except Exception:
        self._ui_status("stop error")