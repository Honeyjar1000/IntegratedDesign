"""
YOLO object detection functionality.
"""
from pathlib import Path
from app.constants import MODEL

# Optional: Ultralytics YOLO for detection
try:
    from ultralytics import YOLO
except Exception as _e:
    YOLO = None
    _YOLO_IMPORT_ERR = _e


class ObjectDetector:
    """Handles YOLO model loading and inference."""
    
    def __init__(self, status_callback):
        self.status_callback = status_callback
        self.enabled = False
        self.model = None
        self.names = {}
        self.conf_threshold = 0.7
        
        self._init_model()
    
    def _init_model(self):
        """Load YOLO model from models/{MODEL}.pt; if it fails, keep UI usable."""
        model_path = Path(f"models/{MODEL}.pt")
        
        if YOLO is None:
            self.enabled = False
            self.status_callback(f"YOLO import failed: {getattr(globals(),'_YOLO_IMPORT_ERR', 'unknown')}")
            return
            
        if not model_path.exists():
            self.enabled = False
            self.status_callback(f"Model not found: {model_path} (showing raw video)")
            return
            
        try:
            self.model = YOLO(str(model_path))
            # class names
            self.names = getattr(self.model, "names", {}) or {}
            self.enabled = True
            self.status_callback(f"Loaded detector {model_path}")
        except Exception as e:
            self.enabled = False
            self.status_callback(f"Detector load error: {e}")
    
    def predict(self, frame_bgr):
        """Run inference on frame and return results."""
        if not (self.enabled and self.model):
            return None
            
        try:
            # Ultralytics works with BGR numpy arrays directly
            results = self.model.predict(
                source=frame_bgr, 
                conf=self.conf_threshold, 
                verbose=False, 
                imgsz=640, 
                device=None
            )
            return results
        except Exception as e:
            self.status_callback(f"Detection error: {e}")
            return None
    
    def set_confidence_threshold(self, conf: float):
        """Set confidence threshold for detections."""
        self.conf_threshold = max(0.0, min(1.0, conf))
