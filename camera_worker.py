import cv2
import time
import urllib.request
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from detector_engine import GarbageDetector


class CameraWorker(QThread):
    frame_ready = pyqtSignal(int, object, str)
    reset_screen = pyqtSignal(int, str)
    evidence_saved = pyqtSignal(int, dict)
    location_ready = pyqtSignal(int, float, float)   # NEW

    def __init__(self, cam_id, ip, port, detector: GarbageDetector,
                 evidence_manager, location_manager=None):
        super().__init__()
        self.cam_id = cam_id
        self.snapshot_url = f"http://{ip}:{port}/shot.jpg"
        self.detector = detector
        self.evidence_manager = evidence_manager
        self.running = True
        self.infer_interval = 2.0
        self.last_infer_time = 0
        self.RECONNECT_TIMEOUT = 10
        self.FETCH_INTERVAL = 0.1
        self.last_fetch = 0
        self.location_manager = location_manager
        self.last_location = None

        self.current_dets = []
        self.miss_count = {}
        self.MAX_MISSES = 3

        self.last_state = "Clean"
        self.last_save_time = 0.0
        self.MIN_SAVE_INTERVAL = 10.0

    def _fetch_snapshot(self):
        try:
            with urllib.request.urlopen(self.snapshot_url, timeout=5) as resp:
                data = resp.read()
            if not data:
                return None
            arr = np.frombuffer(data, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def _sleep_interruptible(self, seconds):
        end = time.time() + seconds
        while self.running and time.time() < end:
            time.sleep(0.1)

    @staticmethod
    def _iou(a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        return inter / (area_a + area_b - inter + 1e-6)

    def _merge_detections(self, new_dets):
        updated = []
        used_old = set()

        for nd in new_dets:
            best_iou, best_idx = 0.0, -1
            for i, od in enumerate(self.current_dets):
                if i in used_old:
                    continue
                iou = self._iou(nd["box"], od["box"])
                if iou > best_iou:
                    best_iou, best_idx = iou, i

            if best_iou > 0.3:
                old = self.current_dets[best_idx]
                sm_box = (0.5 * np.array(nd["box"]) + 0.5 * np.array(old["box"])).astype(int)
                sm_conf = 0.6 * nd["conf"] + 0.4 * old["conf"]
                updated.append({"box": sm_box, "conf": sm_conf, "cls": nd["cls"]})
                used_old.add(best_idx)
            else:
                updated.append(dict(nd))
                self.miss_count[id(nd)] = 0

        for i, od in enumerate(self.current_dets):
            if i in used_old:
                continue
            key = id(od)
            self.miss_count[key] = self.miss_count.get(key, 0) + 1
            if self.miss_count[key] <= self.MAX_MISSES:
                updated.append(od)

        self.current_dets = updated

    def _emit_location_if_available(self):
        if not self.location_manager:
            return
        loc = self.location_manager.get_location()
        if loc and loc.get("lat") is not None and loc.get("lon") is not None:
            self.last_location = loc
            self.location_ready.emit(self.cam_id, float(loc["lat"]), float(loc["lon"]))

    def run(self):
        self.frame_ready.emit(self.cam_id, None, "Connecting...")
        deadline = time.time() + self.RECONNECT_TIMEOUT
        frame = None
        while self.running and time.time() < deadline:
            frame = self._fetch_snapshot()
            if frame is not None:
                break
            self._sleep_interruptible(1.0)

        if frame is None:
            self.reset_screen.emit(self.cam_id, "Connection failed")
            return

        self.frame_ready.emit(self.cam_id, None, "Connected")

        # NEW: fetch GPS once on connect
        self._emit_location_if_available()

        fail_since = None

        while self.running:
            now = time.time()
            if now - self.last_fetch < self.FETCH_INTERVAL:
                time.sleep(0.02)
                continue
            self.last_fetch = now

            frame = self._fetch_snapshot()
            if frame is None:
                if fail_since is None:
                    fail_since = time.time()
                    self.frame_ready.emit(self.cam_id, None, "Reconnecting...")
                if time.time() - fail_since >= self.RECONNECT_TIMEOUT:
                    self.reset_screen.emit(self.cam_id, "Disconnected")
                    return
                self._sleep_interruptible(1.0)
                continue

            fail_since = None
            status = "Clean"

            if time.time() - self.last_infer_time >= self.infer_interval:
                self.last_infer_time = time.time()

                h, w = frame.shape[:2]
                s = min(h, w)
                y0, x0 = (h - s) // 2, (w - s) // 2
                crop = frame[y0:y0 + s, x0:x0 + s]

                new_dets = self.detector.detect(crop)
                for d in new_dets:
                    d["box"] = (d["box"] + np.array([x0, y0, x0, y0])).astype(int)

                self._merge_detections(new_dets)

            if self.current_dets:
                status = f"Garbage detected ({len(self.current_dets)})"
                for d in self.current_dets:
                    x1, y1, x2, y2 = d["box"]
                    cv2.rectangle(frame, (int(x1), int(y1)),
                                  (int(x2), int(y2)), (0, 0, 255), 2)
                    cv2.putText(frame, f"{d['cls']} {d['conf']:.2f}",
                                (int(x1), max(int(y1) - 8, 18)),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 2)
            else:
                status = "Clean"

            # ---- Evidence saving (debounced) ----
            current_state = "Garbage" if self.current_dets else "Clean"
            now_save = time.time()
            if (
                current_state == "Garbage"
                and self.last_state == "Clean"
                and now_save - self.last_save_time >= self.MIN_SAVE_INTERVAL
            ):
                try:
                    # NEW: refresh GPS before saving
                    self._emit_location_if_available()
                    loc = self.last_location
                    record = self.evidence_manager.save(
                        frame, self.cam_id, self.current_dets, location=loc
                    )
                    self.last_save_time = now_save
                    self.evidence_saved.emit(self.cam_id, record)
                except Exception as e:
                    print(f"[cam{self.cam_id}] evidence save failed: {e}")

            self.last_state = current_state

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.frame_ready.emit(self.cam_id, rgb, status)

    def stop(self):
        self.running = False
        self.wait(2000)