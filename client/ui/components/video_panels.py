"""
Video display panel components.
"""
import tkinter as tk
from PIL import Image, ImageTk
import cv2
from ui.styles import create_frame, create_panel_frame, create_label, create_button
from app.constants import BG_COLOR, FRAME_COLOR


class VideoPanel:
    """A video display panel with title and optional controls."""
    
    def __init__(self, parent, title, add_button=False, button_text="", button_command=None):
        self.outer_frame = create_frame(parent)
        self.frame = create_panel_frame(self.outer_frame)
        
        # Header with title and optional button
        header = create_frame(self.frame, bg=FRAME_COLOR)
        header.pack(fill=tk.X, padx=6, pady=(6, 0))
        
        create_label(header, text=title, bg=FRAME_COLOR, fg="#ccc").pack(side=tk.LEFT)
        
        if add_button and button_command:
            create_button(header, button_text, button_command).pack(side=tk.RIGHT)
        
        # Image display label
        self.image_label = tk.Label(self.frame, bg=FRAME_COLOR)
        self.image_label.pack(padx=6, pady=6)
        
        self.frame.pack(padx=6, pady=6)
    
    def show_image(self, image_data, max_width):
        """Display image in the panel."""
        if isinstance(image_data, Image.Image):
            im = image_data
        else:
            # Assume BGR numpy array
            bgr = image_data
            h, w = bgr.shape[:2]
            if w > max_width:
                scale = max_width / w
                bgr = cv2.resize(bgr, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            im = Image.fromarray(rgb)
        
        imtk = ImageTk.PhotoImage(im)
        self.image_label.imtk = imtk  # Keep reference to prevent garbage collection
        self.image_label.configure(image=imtk)
    
    def pack(self, **kwargs):
        """Pack the outer frame."""
        self.outer_frame.pack(**kwargs)


class VideoPanelSet:
    """Set of video panels for live, annotated, and photo display."""
    
    def __init__(self, parent, photo_button_command=None):
        self.container = create_frame(parent)
        self.container.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        # Create three panels
        self.live_panel = VideoPanel(self.container, "Live video")
        self.annotated_panel = VideoPanel(self.container, "Annotated video")
        self.photo_panel = VideoPanel(
            self.container, 
            "Last photo", 
            add_button=True, 
            button_text="Take Photo (Space)",
            button_command=photo_button_command
        )
        
        # Pack panels side by side
        self.live_panel.pack(side=tk.LEFT, padx=6)
        self.annotated_panel.pack(side=tk.LEFT, padx=6)
        self.photo_panel.pack(side=tk.LEFT, padx=6)
    
    def show_live_frame(self, frame, max_width):
        """Show frame in live panel."""
        cv2.flip(frame, 0, frame)
        self.live_panel.show_image(frame, max_width)
    
    def show_annotated_frame(self, frame, max_width):
        """Show frame in annotated panel."""
        self.annotated_panel.show_image(frame, max_width)
    
    def show_photo(self, frame, max_width):
        """Show frame in photo panel."""
        self.photo_panel.show_image(frame, max_width)
    
    def show_waiting_banner(self, banner_image, max_width):
        """Show waiting banner in both live and annotated panels."""
        self.live_panel.show_image(banner_image, max_width)
        self.annotated_panel.show_image(banner_image, max_width)
