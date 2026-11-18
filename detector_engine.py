from ultralytics import YOLO
import numpy as np

# Merge easily confused classes; UI only displays "Garbage"
CLASS_MERGE = {
    "BIODEGRADABLE": "Garbage",
    "CARDBOARD": "Garbage",
    "GLASS": "Garbage",
    "METAL": "Garbage",
    "PAPER": "Garbage",
    "PLASTIC": "Garbage",
}

class GarbageDetector:
    def __init__(self, model_path="models/best.pt", conf=0.3):
        self.model = YOLO(model_path)
        self.conf = conf

    def detect(self, frame: np.ndarray):
        results = self.model(frame, conf=self.conf, imgsz=416, verbose=False)
        boxes = results[0].boxes
        detections = []
        for box in boxes:
            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            raw_name = self.model.names[cls_id]
            display_name = CLASS_MERGE.get(raw_name, raw_name)
            detections.append({
                "box": xyxy,
                "conf": conf,
                "cls": display_name,
                "raw_cls": raw_name,   # Preserve original class for debugging
            })
        return detections
    