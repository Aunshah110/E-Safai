import os
import json
import time
import cv2
import numpy as np

EVIDENCE_DIR = "evidence"
INDEX_PATH = os.path.join(EVIDENCE_DIR, "index.json")


class EvidenceManager:
    def __init__(self):
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        self.index = self._load_index()

    def _load_index(self):
        if os.path.exists(INDEX_PATH):
            try:
                with open(INDEX_PATH, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_index(self):
        with open(INDEX_PATH, "w") as f:
            json.dump(self.index, f, indent=2, default=str)   # default=str as last resort

    def save(self, frame_bgr, cam_id, detections, location=None):
        now = time.time()
        ts_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))

        # Sanitize location: must be dict with lat/lon or None
        loc = None
        if isinstance(location, dict) and "lat" in location and "lon" in location:
            try:
                loc = {"lat": float(location["lat"]), "lon": float(location["lon"])}
            except (TypeError, ValueError):
                loc = None

        loc_suffix = f"_{loc['lat']:.4f}_{loc['lon']:.4f}" if loc else ""
        filename = f"{ts_str}_cam{cam_id}{loc_suffix}.jpg"
        filepath = os.path.join(EVIDENCE_DIR, filename)

        try:
            cv2.imwrite(filepath, frame_bgr)
        except Exception as e:
            print(f"[evidence] imwrite failed: {e}")
            return None

        # Normalize detections into a list of dicts
        det_list = []
        if isinstance(detections, (list, tuple, set)):
            for d in detections:
                if isinstance(d, dict):
                    det_list.append(d)
                elif isinstance(d, str):
                    det_list.append({"cls": d, "conf": 0.0})
        elif isinstance(detections, dict):
            det_list.append(detections)

        # Build classes dict safely
        classes = {}
        for d in det_list:
            name = str(d.get("cls", "Unknown"))
            classes[name] = classes.get(name, 0) + 1

        max_conf = 0.0
        for d in det_list:
            try:
                max_conf = max(max_conf, float(d.get("conf", 0.0)))
            except (TypeError, ValueError):
                pass

        record = {
            "timestamp": now,
            "timestamp_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "cam_id": int(cam_id),
            "filename": filename,
            "num_objects": len(det_list),
            "classes": classes,          # always a dict of str -> int
            "max_conf": max_conf,
            "location": loc,             # dict or None
            "location_str": (
                f"{loc['lat']:.5f}, {loc['lon']:.5f}" if loc else "Unknown"
            ),
        }
        self.index.append(record)
        self._save_index()
        return record

    def get_history(self, limit=None):
        records = sorted(self.index, key=lambda r: r.get("timestamp", 0), reverse=True)
        return records[:limit] if limit else records

    def get_image_path(self, record):
        return os.path.join(EVIDENCE_DIR, record["filename"])

    def clear(self):
        for r in self.index:
            p = self.get_image_path(r)
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        self.index = []
        self._save_index()