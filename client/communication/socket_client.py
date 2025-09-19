"""
Socket.IO client setup using the original working approach.
"""
import socketio
import threading
from config import API_BASE


class SocketClientManager:
    """Manages Socket.IO client exactly like the original working code."""
    
    def __init__(self, app_instance):
        self.app = app_instance
        self.connected = False
        
        # Create client exactly like original code - AFTER Tkinter is initialized
        self.sio = socketio.Client(reconnection=True, logger=False, engineio_logger=False)
        
        # Setup event handlers exactly like original
        self._setup_events()
        
        # Connect in background exactly like original
        self._connect_async()
    
    def _setup_events(self):
        """Setup Socket.IO event handlers exactly like original code."""
        
        @self.sio.event
        def connect():
            self.connected = True
            self.app._on_connect()
        
        @self.sio.event
        def disconnect():
            self.connected = False
            self.app._on_disconnect()
        
        @self.sio.event
        def connect_error(err):
            self.app._on_connect_error(err)
        
        @self.sio.on("status")
        def on_status(data):
            self.app._on_status(data)
        
        @self.sio.on("video_frame")
        def on_video_frame(jpg_bytes):
            self.app._on_video_frame(jpg_bytes)
    
    def _connect_async(self):
        """Connect in background thread exactly like original."""
        threading.Thread(
            target=lambda: self.sio.connect(
                API_BASE, 
                namespaces=['/'], 
                transports=['websocket'], 
                wait_timeout=10
            ),
            daemon=True
        ).start()
    
    def emit(self, event, data=None, callback=None):
        """Emit event to server."""
        if self.connected:
            self.sio.emit(event, data, callback=callback)
    
    def disconnect(self):
        """Disconnect from server."""
        try:
            self.sio.disconnect()
        except Exception:
            pass
