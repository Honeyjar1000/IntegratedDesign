"""
Status management and server communication service.
"""


class StatusService:
    """Handles status polling and management."""
    
    def __init__(self, socket_client, ui_update_callback):
        self.socket_client = socket_client
        self.ui_update_callback = ui_update_callback
        self.servo_angle = 0.0
    
    def poll_status(self):
        """Poll server for status updates."""
        if self.socket_client.connected:
            try:
                self.socket_client.emit("get_status", callback=self._on_status_response)
            except Exception:
                pass
    
    def _on_status_response(self, data):
        """Handle status response from server."""
        self.ui_update_callback(0, lambda d=data: self.apply_status_dict(d))
    
    def apply_status_dict(self, status_dict: dict):
        """Apply status dictionary to update UI and internal state."""
        if not isinstance(status_dict, dict) or not status_dict.get("ok", True):
            return

        # Update motor status display
        left_info = status_dict.get("left", {})
        right_info = status_dict.get("right", {})
        
        def format_value(x):
            return f"{x:.2f}" if isinstance(x, (float, int)) else x
        
        status_text = (
            f"L: dir {left_info.get('dir',0)} duty {format_value(left_info.get('duty',0))} | "
            f"R: dir {right_info.get('dir',0)} duty {format_value(right_info.get('duty',0))}"
        )
        
        try:
            # Update speed limit if present
            speed_updates = {}
            if "speed_limit" in status_dict:
                frac = float(status_dict["speed_limit"])
                pct = int(round(frac * 100))
                speed_updates = {"speed_percent": pct}

            # Update trims if present
            trim_updates = {}
            if "trim" in status_dict and isinstance(status_dict["trim"], dict):
                trim = status_dict["trim"]
                if "L" in trim:
                    trim_updates["left_trim"] = int(round(float(trim["L"]) * 100))
                if "R" in trim:
                    trim_updates["right_trim"] = int(round(float(trim["R"]) * 100))

            # Update servo angle if present
            if isinstance(status_dict.get("servo"), dict) and "angle" in status_dict["servo"]:
                self.servo_angle = float(status_dict["servo"]["angle"])

            # Send all updates to UI
            self.ui_update_callback(0, lambda: self._update_ui_status(
                status_text, speed_updates, trim_updates
            ))
            
        except Exception:
            # If parsing fails, at least update the basic status
            self.ui_update_callback(0, lambda: self._update_ui_status(status_text, {}, {}))
    
    def _update_ui_status(self, status_text, speed_updates, trim_updates):
        """Update UI with status information - to be connected by main app."""
        pass
