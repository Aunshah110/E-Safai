from ultralytics import YOLO
import numpy as np


class GarbageDetector:
    def __init__(self, model_path="models/best.pt", conf=0.3, iou=0.25):
        self.model = YOLO(model_path)
        self.conf = conf
        self.iou = iou

    def detect(self, frame: np.ndarray):
        results = self.model(
            frame,
            conf=self.conf,
            iou=self.iou,
            imgsz=416,
            agnostic_nms=True,
            verbose=False,
        )
        boxes = results[0].boxes
        detections = []
        for box in boxes:
            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = self.model.names[cls_id]
            detections.append({
                "box": xyxy,
                "conf": conf,
                "cls": cls_name,      # Original category name, e.g., PLASTIC, GLASS
                "cls_id": cls_id,
            })
        return detections