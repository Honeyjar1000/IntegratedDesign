"""
Settings and configuration management service.
"""


class SettingsService:
    """Handles application settings and configuration."""
    
    def __init__(self, socket_client, status_callback):
        self.socket_client = socket_client
        self.status_callback = status_callback
        
        # Debounce handles for slider updates
        self._speed_job = None
        self._trim_left_job = None
        self._trim_right_job = None
    
    def set_speed_limit_debounced(self, percent, after_callback, cancel_callback):
        """Set speed limit with debouncing."""
        if self._speed_job:
            cancel_callback(self._speed_job)
        
        def emit_speed():
            self._emit_set_speed_limit(percent / 100.0)
        
        self._speed_job = after_callback(150, emit_speed)
    
    def set_trim_debounced(self, side, percent, after_callback, cancel_callback):
        """Set wheel trim with debouncing."""
        job_attr = f"_trim_{side.lower()}_job"
        current_job = getattr(self, job_attr, None)
        
        if current_job:
            cancel_callback(current_job)
        
        def emit_trim():
            self._emit_set_trim(side, percent / 100.0)
        
        new_job = after_callback(150, emit_trim)
        setattr(self, job_attr, new_job)
    
    def _emit_set_speed_limit(self, fraction):
        """Emit speed limit change to server."""
        try:
            self.socket_client.emit(
                "set_speed_limit",
                {"speed_limit": float(fraction)},
                callback=self._on_status_update
            )
        except Exception:
            pass
    
    def _emit_set_trim(self, side, value):
        """Emit trim change to server."""
        try:
            self.socket_client.emit(
                "set_trim", 
                {side: float(value)}, 
                callback=self._on_status_update
            )
        except Exception:
            pass
    
    def _on_status_update(self, data):
        """Handle status update response."""
        # This will be connected to the status service
        pass
