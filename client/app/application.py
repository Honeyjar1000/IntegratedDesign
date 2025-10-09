"""
Main application class that coordinates all components.
"""
from config import PI_HOST
from app.constants import LIVE_MAX_WIDTH, PHOTO_MAX_WIDTH
from ui.main_window import MainWindow
from communication.socket_client import SocketClientManager
from control.drive_controller import DriveController
from control.servo_controller import ServoController
from control.input_handler import InputHandler
from vision.detector import ObjectDetector
from vision.annotator import DetectionAnnotator
from vision.frame_processor import FrameProcessor
from services.photo_service import PhotoService
from services.status_service import StatusService
from services.settings_service import SettingsService
from utils.images import banner_image


class RobotControlApp:
    """Main application class that coordinates all components."""
    
    def __init__(self):
        # Application state
        self.running = True
        
        # Create waiting banner
        self.waiting_banner = banner_image(
            ["Waiting for server…", "Press Q to quit."], 
            w=LIVE_MAX_WIDTH, 
            h=int(LIVE_MAX_WIDTH * 0.75)
        )
        
        # Initialize UI FIRST (like original code)
        self._init_ui()
        
        # Initialize other components
        self._init_vision()
        self._init_services()
        self._init_controllers()
        
        # Initialize communication AFTER UI is ready (like original code)
        self._init_communication()
        
        # Setup initial UI state
        self._setup_initial_ui()
        
        # Start status polling
        self.window.after(1000, self._poll_status)
    
    def _init_ui(self):
        """Initialize the main window and UI components."""
        callbacks = {
            "on_close": self.on_close,
            "key_press": self._on_key_press,
            "key_release": self._on_key_release,
            "take_photo": self._take_photo,
            "drive": self._drive,
            "stop": self._stop,
            "speed_change": self._on_speed_change,
            "trim_left_change": self._on_trim_left_change,
            "trim_right_change": self._on_trim_right_change,
            "choose_folder": self._choose_folder
        }
        self.window = MainWindow(callbacks)
    
    def _init_vision(self):
        """Initialize vision components."""
        self.detector = ObjectDetector(self._ui_status)
        self.annotator = DetectionAnnotator()
        self.frame_processor = FrameProcessor(
            self.detector, 
            self.annotator, 
            self.window.after
        )
        
        # Connect frame processor callbacks to UI
        self.frame_processor._show_live_frame = lambda frame: self.window.show_live_frame(frame, LIVE_MAX_WIDTH)
        self.frame_processor._show_annotated_frame = lambda frame: self.window.show_annotated_frame(frame, LIVE_MAX_WIDTH)
    
    def _init_services(self):
        """Initialize service components."""
        self.photo_service = PhotoService(
            lambda: self.frame_processor.last_frame_bgr,
            lambda frame: self.window.show_photo(frame, PHOTO_MAX_WIDTH)
        )
        
        # Status service will be initialized after socket client
        self.status_service = None
        self.settings_service = None
    
    def _init_controllers(self):
        """Initialize control components."""
        # Controllers will be initialized after socket client
        self.drive_controller = None
        self.servo_controller = None
        self.input_handler = None
    
    def _init_communication(self):
        """Initialize communication components."""
        # Create socket client manager exactly like original code
        self.socket_client = SocketClientManager(self)
        
        # Now initialize components that depend on socket client
        self.status_service = StatusService(self.socket_client, self.window.after)
        self.status_service._update_ui_status = self._apply_status_updates
        
        self.settings_service = SettingsService(self.socket_client, self._ui_status)
        self.settings_service._on_status_update = self.status_service._on_status_response
        
        self.drive_controller = DriveController(self.socket_client, self._ui_status)
        self.drive_controller._on_ack_update_status = self.status_service._on_status_response
        
        self.servo_controller = ServoController(self.socket_client)
        self.servo_controller._on_ack_update_status = self.status_service._on_status_response
        
        self.input_handler = InputHandler(
            self.drive_controller,
            self.servo_controller,
            self.photo_service,
            self.on_close
        )
        
        # Socket client connects automatically in constructor (like original)
    
    def _setup_initial_ui(self):
        """Setup initial UI state."""
        self.window.show_waiting_banner(self.waiting_banner, LIVE_MAX_WIDTH)
        self.window.update_save_folder_display(self.photo_service.get_save_directory_text())
    
    # Socket.IO event handlers
    def _on_connect(self):
        """Handle socket connection."""
        self.window.set_connected_status(PI_HOST)
        try:
            self.socket_client.emit("get_status", callback=self.status_service._on_status_response)
        except Exception:
            pass
    
    def _on_disconnect(self):
        """Handle socket disconnection."""
        self.window.set_disconnected_status()
        self.window.after(0, lambda: self.window.show_waiting_banner(self.waiting_banner, LIVE_MAX_WIDTH))
    
    def _on_connect_error(self, err):
        """Handle socket connection error."""
        self.window.set_error_status(f"Connect error: {err}")
    
    def _on_status(self, data):
        """Handle status update from server."""
        self.window.after(0, lambda d=data: self.status_service.apply_status_dict(d))
    
    def _on_video_frame(self, jpg_bytes):
        """Handle video frame from server."""
        self.frame_processor.process_video_frame(jpg_bytes)
    
    # UI event handlers
    def _on_key_press(self, event):
        """Handle key press events."""
        self.input_handler.on_key_press(event)
    
    def _on_key_release(self, event):
        """Handle key release events."""
        self.input_handler.on_key_release(event)
    
    def _take_photo(self):
        """Handle photo capture."""
        self.photo_service.take_photo()
    
    def _drive(self, left, right):
        """Handle drive command."""
        self.drive_controller.drive(left, right)
    
    def _stop(self):
        """Handle stop command."""
        self.drive_controller.stop()
    
    def _on_speed_change(self, percent):
        """Handle speed change."""
        self.settings_service.set_speed_limit_debounced(
            percent, 
            self.window.after, 
            self.window.after_cancel
        )
    
    def _on_trim_left_change(self, percent):
        """Handle left trim change."""
        self.settings_service.set_trim_debounced(
            "L", 
            percent, 
            self.window.after, 
            self.window.after_cancel
        )
    
    def _on_trim_right_change(self, percent):
        """Handle right trim change."""
        self.settings_service.set_trim_debounced(
            "R", 
            percent, 
            self.window.after, 
            self.window.after_cancel
        )
    
    def _choose_folder(self):
        """Handle folder selection."""
        new_folder = self.photo_service.choose_folder()
        if new_folder:
            self.window.update_save_folder_display(
                self.photo_service.get_save_directory_text()
            )
    
    # Status and UI updates
    def _ui_status(self, text):
        """Update UI status."""
        self.window.after(0, lambda t=text: self.window.update_status(t))
    
    def _apply_status_updates(self, status_text, speed_updates, trim_updates):
        """Apply status updates to UI."""
        self.window.update_status(status_text)
        
        if "speed_percent" in speed_updates:
            self.window.update_speed_display(speed_updates["speed_percent"])
        
        if "left_trim" in trim_updates:
            self.window.update_trim_display(left_percent=trim_updates["left_trim"])
        
        if "right_trim" in trim_updates:
            self.window.update_trim_display(right_percent=trim_updates["right_trim"])
    
    def _poll_status(self):
        """Poll server for status updates."""
        if self.running:
            self.status_service.poll_status()
            self.window.after(1000, self._poll_status)
    
    # Application lifecycle
    def on_close(self):
        """Handle application close."""
        self.running = False
        try:
            self.drive_controller.stop()
        except:
            pass
        try:
            self.socket_client.disconnect()
        except:
            pass
        self.window.destroy()
    
    def mainloop(self):
        """Start the application main loop."""
        self.window.mainloop()
