import cv2
import time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from detector_engine import GarbageDetector

class CameraWorker(QThread):
    # Signal: (camera_id, frame_with_boxes, status_text)
    frame_ready = pyqtSignal(int, np.ndarray, str)

    def __init__(self, cam_id: int, ip: str, port: str, detector: GarbageDetector):
        super().__init__()
        self.cam_id = cam_id
        self.url = f"http://{ip}:{port}/video"
        self.detector = detector
        self.running = True
        self.infer_interval = 2.5   # Infer once every 2.5 seconds
        self.last_infer_time = 0

    def run(self):
        cap = cv2.VideoCapture(self.url)
        if not cap.isOpened():
            self.frame_ready.emit(self.cam_id, None, "Connection failed")
            return

        while self.running:
            ret, frame = cap.read()
            if not ret:
                self.frame_ready.emit(self.cam_id, None, "Disconnected, reconnecting...")
                cap.release()
                time.sleep(3)
                cap = cv2.VideoCapture(self.url)
                continue

            now = time.time()
            status = "Clean"

            # Run inference only at intervals to avoid CPU overload
            if now - self.last_infer_time >= self.infer_interval:
                self.last_infer_time = now
                dets = self.detector.detect(frame)
                if len(dets) > 0:
                    status = f"Garbage detected ({len(dets)})"
                    for d in dets:
                        x1, y1, x2, y2 = d["box"]
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv2.putText(frame, f"{d['cls']} {d['conf']:.2f}",
                                    (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5, (0, 0, 255), 1)
                else:
                    status = "Clean"

            # Convert BGR to RGB for Qt display
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.frame_ready.emit(self.cam_id, rgb, status)

        cap.release()

    def stop(self):
        self.running = False
        self.wait()