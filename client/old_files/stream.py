import cv2
from config import STREAM_URL

class StreamClient:
    """Tiny wrapper over cv2.VideoCapture that knows how to (re)open."""
    def __init__(self):
        self.cap = None

    def open(self) -> bool:
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(STREAM_URL)
        return self.cap.isOpened()

    def read(self):
        if self.cap is None:
            return False, None
        return self.cap.read()

    def is_open(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def close(self):
        if self.cap is not None:
            try:
                self.cap.release()
            finally:
                self.cap = None
