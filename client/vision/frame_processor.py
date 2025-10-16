"""
Frame processing pipeline for video and detection.
"""
import threading
import numpy as np
import cv2


class FrameProcessor:
    """Handles frame processing pipeline with drop-frame rendering and inference."""
    
    def __init__(self, detector, annotator, ui_update_callback, detection_service=None):
        self.detector = detector
        self.annotator = annotator
        self.ui_update_callback = ui_update_callback
        self.detection_service = detection_service
        
        # Frame processing state
        self._render_busy = False
        self._latest_jpg = None
        self.last_frame_bgr = None
        
        # Disable automatic inference
        self._infer_busy = False
        self._infer_seq = 0
        self._latest_for_infer = None  # (frame_bgr, seq)
    
    def process_video_frame(self, jpg_bytes):
        """Process incoming video frame (JPEG bytes)."""
        # Drop old frames, render most recent
        self._latest_jpg = jpg_bytes
        if not self._render_busy:
            self._render_busy = True
            # Schedule rendering on UI thread
            self.ui_update_callback(0, self._drain_and_render)
    
    def _drain_and_render(self):
        """Decode and render the latest frame."""
        data = self._latest_jpg
        self._latest_jpg = None
        
        if data is not None:
            np_arr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Keep last raw frame
                self.last_frame_bgr = frame
                
                # Update detection service with current frame
                if self.detection_service:
                    self.detection_service.update_frame(frame)
                
                # Show raw frame in live panel
                self.ui_update_callback(0, lambda: self._show_live_frame(frame))
                
                # NO automatic inference - only manual detection via 'd' key

        # Continue draining if more frames arrived
        if self._latest_jpg is not None:
            self.ui_update_callback(0, self._drain_and_render)
        else:
            self._render_busy = False
    
    def _start_infer(self):
        """Spawn an inference worker if not already busy."""
        if not self.detector.enabled:
            return
        if self._infer_busy or self._latest_for_infer is None:
            return
            
        frame, seq = self._latest_for_infer
        self._infer_busy = True
        threading.Thread(target=self._infer_worker, args=(frame, seq), daemon=True).start()
    
    def _infer_worker(self, frame_bgr, seq):
        """Run model inference and schedule annotated rendering."""
        try:
            results = self.detector.predict(frame_bgr)
            if results is not None:
                annotated = self.annotator.draw_detections(frame_bgr, results, self.detector.names)
            else:
                annotated = frame_bgr.copy()
        except Exception as e:
            annotated = self.annotator.draw_error_message(frame_bgr, str(e))

        # Push to UI thread
        self.ui_update_callback(0, lambda img=annotated: self._show_annotated_frame(img))

        # Allow next infer; if a newer frame arrived while we were busy, kick again
        self._infer_busy = False
        latest = self._latest_for_infer
        if latest is not None and latest[1] > seq:
            self._start_infer()
    
    def _show_live_frame(self, frame):
        """Show live frame - to be implemented by UI."""
        pass
    
    def _show_annotated_frame(self, frame):
        """Show annotated frame - to be implemented by UI."""
        pass
