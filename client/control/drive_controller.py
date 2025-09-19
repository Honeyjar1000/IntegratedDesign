"""
Drive and movement control.
"""
import time


class DriveController:
    """Handles robot drive commands."""
    
    def __init__(self, socket_client, status_callback):
        self.socket_client = socket_client
        self.status_callback = status_callback
    
    def drive(self, left, right):
        """Send drive command to robot."""
        try:
            payload = {
                "left": float(left),
                "right": float(right),
                "client_ts": time.time()
            }

            def on_callback(data):
                """Handler for the app server callback."""
                client_ts = data.get("client_ts")
                if client_ts is not None:
                    curr_ts = time.time()
                    latency = (curr_ts - client_ts) * 500  # * 1000 for ms, /2 for round trip
                    self.status_callback(f"Last motor latency: {latency:.1f} ms")

            # Emit data and wait for latency callback from the app server
            self.socket_client.emit("drive", payload, callback=on_callback)
        except Exception:
            self.status_callback("drive error")

    def stop(self):
        """Stop robot movement."""
        try:
            self.socket_client.emit("stop", callback=self._on_ack_update_status)
        except Exception:
            self.status_callback("stop error")
    
    def _on_ack_update_status(self, data):
        """Handle status update from server."""
        # This will be connected to the main app's status handler
        pass
