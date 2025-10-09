"""
Video stream client for receiving video frames.
"""
import cv2
from config import STREAM_URL


class StreamClient:
    """Wrapper over cv2.VideoCapture for video streaming."""
    
    def __init__(self):
        self.cap = None

    def open(self) -> bool:
        """Open video stream connection."""
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(STREAM_URL)
        return self.cap.isOpened()

    def read(self):
        """Read frame from video stream."""
        if self.cap is None:
            return False, None
        return self.cap.read()

    def is_open(self) -> bool:
        """Check if stream is open."""
        return self.cap is not None and self.cap.isOpened()

    def close(self):
        """Close video stream connection."""
        if self.cap is not None:
            try:
                self.cap.release()
            finally:
                self.cap = None
