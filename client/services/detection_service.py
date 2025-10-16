"""
Detection service for manual object detection.
"""
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime


class DetectionService:
    """Handles manual detection triggering and saving annotated images."""
    
    def __init__(self, detector, annotator, photo_service, ui_update_callback):
        self.detector = detector
        self.annotator = annotator
        self.photo_service = photo_service
        self.ui_update_callback = ui_update_callback
        
        # Disable automatic detection
        self.detector.enabled = False
        
        # Current frame for detection
        self.current_frame = None
    
    def update_frame(self, frame_bgr):
        """Update the current frame for detection."""
        self.current_frame = frame_bgr
    
    def trigger_detection(self):
        """Manually trigger detection on current frame."""
        if self.current_frame is None:
            print("❌ Detection triggered but no frame available!")
            return
        
        print(f"✓ Detection triggered on frame {self.current_frame.shape}")
        
        # Run detection
        try:
            results = self.detector.predict(self.current_frame)
            print(f"✓ Detection results: {results}")
            if results is not None:
                annotated = self.annotator.draw_detections(self.current_frame, results, self.detector.names)
                print(f"✓ Annotated frame created: {annotated.shape}")
            else:
                annotated = self.current_frame.copy()
                print("⚠ No detection results, showing copy of frame")
        except Exception as e:
            print(f"❌ Detection error: {e}")
            annotated = self.annotator.draw_error_message(self.current_frame, str(e))
        
        # Show annotated frame in second window
        print("✓ Calling show_annotated_frame")
        self.ui_update_callback(0, lambda: self._show_annotated_frame(annotated))
        
        # Save the annotated image
        self._save_detection_image(annotated)
    
    def _show_annotated_frame(self, frame):
        """Show annotated frame - to be connected by main app."""
        pass
    
    def _save_detection_image(self, annotated_frame):
        """Save the annotated detection image."""
        try:
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"detection_{timestamp}.jpg"
            
            # Get save directory from photo service
            save_dir = self.photo_service.save_directory
            filepath = save_dir / filename
            
            # Save the image
            cv2.imwrite(str(filepath), annotated_frame)
            
            # Update UI status
            self.ui_update_callback(0, lambda: self._update_status(f"Detection saved: {filename}"))
            
        except Exception as e:
            error_msg = f"Save error: {e}"
            self.ui_update_callback(0, lambda: self._update_status(error_msg))
    
    def _update_status(self, message):
        """Update status - to be connected by main app."""
        pass
