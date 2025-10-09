"""
Status bar component for displaying connection and robot status.
"""
from ui.styles import create_status_label


class StatusBar:
    """Status bar for displaying connection and robot status."""
    
    def __init__(self, parent):
        self.status_label = create_status_label(parent, text="Connecting…")
        self.status_label.pack(pady=(10, 0))
    
    def update_status(self, text):
        """Update status text."""
        self.status_label.config(text=text)
    
    def set_connecting(self):
        """Set status to connecting."""
        self.update_status("Connecting…")
    
    def set_connected(self, host):
        """Set status to connected."""
        self.update_status(f"Connected to {host}")
    
    def set_disconnected(self):
        """Set status to disconnected."""
        self.update_status("Disconnected — retrying…")
    
    def set_error(self, error_msg):
        """Set status to error."""
        self.update_status(f"Error: {error_msg}")
