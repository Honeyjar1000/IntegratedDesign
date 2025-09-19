"""
Drawing and annotation functionality for object detection.
"""
import random
import cv2
import numpy as np


class DetectionAnnotator:
    """Handles drawing bounding boxes and labels on frames."""
    
    def __init__(self):
        self._cls_colors = {}  # color palette per class id
    
    def _get_class_color(self, cls_id: int):
        """Get consistent color for a class ID."""
        if cls_id not in self._cls_colors:
            random.seed(cls_id + 12345)
            self._cls_colors[cls_id] = (
                int(50 + 205 * random.random()),
                int(50 + 205 * random.random()),
                int(50 + 205 * random.random()),
            )
        return self._cls_colors[cls_id]
    
    def draw_detections(self, frame_bgr, results, class_names=None):
        """Draw boxes/labels on a copy of the frame."""
        if not results:
            return frame_bgr.copy()
        
        out = frame_bgr.copy()
        res = results[0]
        names = getattr(res, "names", None) or class_names or {}

        boxes = getattr(res, "boxes", None)
        if boxes is None or boxes.xyxy is None:
            return out

        xyxy = boxes.xyxy.cpu().numpy() if hasattr(boxes.xyxy, "cpu") else np.asarray(boxes.xyxy)
        confs = boxes.conf.cpu().numpy() if hasattr(boxes.conf, "cpu") else np.asarray(boxes.conf)
        clses = boxes.cls.cpu().numpy() if hasattr(boxes.cls, "cpu") else np.asarray(boxes.cls)

        H, W = out.shape[:2]
        t = max(1, int(round(min(H, W) / 320)))  # thickness scales with image size
        tf = max(0.4, min(0.8, t * 0.4))         # font scale

        for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clses):
            cls_id = int(k) if k is not None else -1
            color = self._get_class_color(cls_id)
            x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

            # Draw bounding box
            cv2.rectangle(out, (x1, y1), (x2, y2), color, t, cv2.LINE_AA)

            # Prepare label text
            label = names.get(cls_id, f"id{cls_id}") if isinstance(names, dict) else str(cls_id)
            text = f"{label} {c:.2f}" if c is not None else f"{label}"
            
            # Calculate text size
            (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, tf, max(1, t))
            th = th + bl
            
            # Draw text background
            xt2, yt2 = x1 + tw + 6, y1 + th + 4
            cv2.rectangle(out, (x1, y1), (xt2, yt2), color, -1, cv2.LINE_AA)
            
            # Draw text
            cv2.putText(out, text, (x1 + 3, y1 + th - bl), 
                       cv2.FONT_HERSHEY_SIMPLEX, tf, (0, 0, 0), 1, cv2.LINE_AA)

        return out
    
    def draw_error_message(self, frame_bgr, error_msg):
        """Draw error message on frame."""
        out = frame_bgr.copy()
        cv2.putText(out, f"Detection error: {error_msg}", (10, 24),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        return out
