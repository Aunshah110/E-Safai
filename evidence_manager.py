import os
import json
import time
import cv2, datetime
import numpy as np
from collections import Counter, defaultdict

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

    def compute_stats(self, days=None, cam_id=None):
        """
        Returns a dict of pre-aggregated stats.
        days: None = all time, or an int (last N days)
        cam_id: None = all cameras, or int
        """
        records = self.index
    
        if days is not None:
            cutoff = time.time() - days * 86400
            records = [r for r in records if r.get("timestamp", 0) >= cutoff]
    
        if cam_id is not None:
            records = [r for r in records if r.get("cam_id") == cam_id]
    
        total = len(records)
    
        # Today's count
        today_start = datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp()
        today_count = sum(1 for r in records if r.get("timestamp", 0) >= today_start)
    
        # Per-camera counts
        per_cam = Counter(r.get("cam_id", -1) for r in records)
    
        # Class distribution (aggregate the "classes" dict of each record)
        class_counter = Counter()
        for r in records:
            cls_val = r.get("classes", {})
            if isinstance(cls_val, dict):
                for k, v in cls_val.items():
                    class_counter[k] += v
            elif isinstance(cls_val, (list, tuple, set)):
                for k in cls_val:
                    class_counter[k] += 1
    
        # Per-day counts (last 7 days by default for the timeline)
        per_day = defaultdict(int)
        for r in records:
            ts = r.get("timestamp", 0)
            day = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            per_day[day] += 1
    
        # Most common class
        top_class = class_counter.most_common(1)[0][0] if class_counter else "—"
    
        # Busiest camera
        busiest_cam = per_cam.most_common(1)[0][0] if per_cam else "—"
    
        return {
            "total": total,
            "today": today_count,
            "per_cam": dict(per_cam),
            "class_dist": dict(class_counter),
            "per_day": dict(sorted(per_day.items())),
            "top_class": top_class,
            "busiest_cam": busiest_cam,
            "num_records": len(records),
        }