"""
Servo control functionality.
"""


class ServoController:
    """Handles servo control commands."""
    
    def __init__(self, socket_client):
        self.socket_client = socket_client
    
    def set_angle(self, angle_deg: float):
        """Set servo to specific angle."""
        try:
            self.socket_client.emit("servo_set", {"angle": float(angle_deg)}, 
                                   callback=self._on_ack_update_status)
        except Exception:
            pass

    def nudge_angle(self, delta_deg: float):
        """Nudge servo by delta angle."""
        try:
            self.socket_client.emit("servo_set", {"delta": float(delta_deg)}, 
                                   callback=self._on_ack_update_status)
        except Exception:
            pass
    
    def _on_ack_update_status(self, data):
        """Handle status update from server."""
        # This will be connected to the main app's status handler
        pass
