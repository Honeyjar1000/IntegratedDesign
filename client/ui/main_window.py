"""
Main application window.
"""
import tkinter as tk
from config import WINDOW_TITLE
from app.constants import BG_COLOR
from ui.components.video_panels import VideoPanelSet
from ui.components.control_panel import ControlPanel
from ui.components.status_bar import StatusBar


class MainWindow(tk.Tk):
    """Main application window with all UI components."""
    
    def __init__(self, callbacks):
        super().__init__()
        self.callbacks = callbacks
        
        # Window setup
        self.title(WINDOW_TITLE)
        self.protocol("WM_DELETE_WINDOW", self.callbacks["on_close"])
        self.geometry("1360x760")
        self.configure(bg=BG_COLOR)
        
        # Create UI components
        self._create_video_panels()
        self._create_control_panel()
        self._create_status_bar()
        
        # Setup keyboard bindings
        self.bind("<KeyPress>", self.callbacks["key_press"])
        self.bind("<KeyRelease>", self.callbacks["key_release"])
        self.focus_force()
    
    def _create_video_panels(self):
        """Create video display panels."""
        self.video_panels = VideoPanelSet(self, self.callbacks["take_photo"])
    
    def _create_control_panel(self):
        """Create control panel with buttons and sliders."""
        control_callbacks = {
            "drive": self.callbacks["drive"],
            "stop": self.callbacks["stop"],
            "speed_change": self.callbacks["speed_change"],
            "trim_left_change": self.callbacks["trim_left_change"],
            "trim_right_change": self.callbacks["trim_right_change"],
            "choose_folder": self.callbacks["choose_folder"]
        }
        self.control_panel = ControlPanel(self, control_callbacks)
    
    def _create_status_bar(self):
        """Create status bar."""
        self.status_bar = StatusBar(self)
    
    # Video display methods
    def show_live_frame(self, frame, max_width):
        """Show frame in live video panel."""
        self.video_panels.show_live_frame(frame, max_width)
    
    def show_annotated_frame(self, frame, max_width):
        """Show frame in annotated video panel."""
        self.video_panels.show_annotated_frame(frame, max_width)
    
    def show_photo(self, frame, max_width):
        """Show frame in photo panel."""
        self.video_panels.show_photo(frame, max_width)
    
    def show_waiting_banner(self, banner_image, max_width):
        """Show waiting banner in video panels."""
        self.video_panels.show_waiting_banner(banner_image, max_width)
    
    # Control panel updates
    def update_speed_display(self, percent):
        """Update speed slider display."""
        self.control_panel.update_speed(percent)
    
    def update_trim_display(self, left_percent=None, right_percent=None):
        """Update trim slider displays."""
        if left_percent is not None:
            self.control_panel.update_trim_left(left_percent)
        if right_percent is not None:
            self.control_panel.update_trim_right(right_percent)
    
    def update_save_folder_display(self, text):
        """Update save folder display text."""
        self.control_panel.update_save_folder_text(text)
    
    # Status bar updates
    def update_status(self, text):
        """Update status bar text."""
        self.status_bar.update_status(text)
    
    def set_connecting_status(self):
        """Set status to connecting."""
        self.status_bar.set_connecting()
    
    def set_connected_status(self, host):
        """Set status to connected."""
        self.status_bar.set_connected(host)
    
    def set_disconnected_status(self):
        """Set status to disconnected."""
        self.status_bar.set_disconnected()
    
    def set_error_status(self, error_msg):
        """Set status to error."""
        self.status_bar.set_error(error_msg)
