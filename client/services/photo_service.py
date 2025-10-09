"""
Photo capture and management service.
"""
from pathlib import Path
from tkinter import filedialog, messagebox
from config import SAVE_DIR
from utils.images import ts_filename, save_bgr


class PhotoService:
    """Handles photo capture and saving functionality."""
    
    def __init__(self, get_current_frame_callback, update_photo_display_callback):
        self.save_dir = SAVE_DIR
        self.get_current_frame = get_current_frame_callback
        self.update_photo_display = update_photo_display_callback
    
    def choose_folder(self):
        """Open folder selection dialog."""
        d = filedialog.askdirectory(
            initialdir=str(self.save_dir), 
            title="Choose save folder"
        )
        if d:
            self.save_dir = Path(d)
            return self.save_dir
        return None
    
    def take_photo(self):
        """Capture and save current frame as photo."""
        current_frame = self.get_current_frame()
        if current_frame is None:
            messagebox.showwarning("No frame", "No video frame available yet.")
            return False
        
        out_path = self.save_dir / ts_filename("photo", "jpg")
        if save_bgr(current_frame, out_path):
            self.update_photo_display(current_frame)
            print(f"Saved: {out_path}")
            return True
        else:
            print("Failed to save image.")
            return False
    
    def get_save_directory_text(self):
        """Get formatted save directory text for display."""
        return f"Saving to: {self.save_dir}"
