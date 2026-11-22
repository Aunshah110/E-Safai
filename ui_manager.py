from collections import Counter
import webbrowser
import time

from stats_page import StatsPage

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QLabel, QPushButton, QInputDialog,
    QVBoxLayout, QHBoxLayout, QSizePolicy, QStackedWidget, QScrollArea,
    QFrame
)
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt
from camera_worker import CameraWorker
from detector_engine import GarbageDetector
from evidence_manager import EvidenceManager
from location_manager import LocationManager
import json, os


CONFIG_PATH = "configs/cameras.json"


class CameraScreen(QLabel):
    def __init__(self):
        super().__init__("+")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background: #222; color: #888; font-size: 36px; "
            "border: 2px dashed #555;"
        )
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(80, 60)
        self._pixmap = None

    def set_frame(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._apply_pixmap()

    def _apply_pixmap(self):
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        super().setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_pixmap()


class HistoryCard(QFrame):
    def __init__(self, record, image_path):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #2a2a2a; border: 1px solid #444; border-radius: 6px; }"
        )
        self.setFixedHeight(160)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        thumb = QLabel()
        thumb.setFixedSize(200, 140)
        thumb.setStyleSheet("background: #111; border: 1px solid #333;")
        pix = QPixmap(image_path)
        if not pix.isNull():
            thumb.setPixmap(pix.scaled(
                200, 140,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(thumb)

        info = QVBoxLayout()
        info.setSpacing(4)

        ts_lbl = QLabel(record.get("timestamp_str", "Unknown time"))
        ts_lbl.setStyleSheet("color: #4fc3f7; font-size: 14px; font-weight: bold;")
        info.addWidget(ts_lbl)

        cam_lbl = QLabel(f"Camera {int(record.get('cam_id', 0)) + 1}")
        cam_lbl.setStyleSheet("color: #bbb; font-size: 12px;")
        info.addWidget(cam_lbl)

        classes_val = record.get("classes", {})
        if isinstance(classes_val, dict):
            classes_str = ", ".join(f"{k} ×{v}" for k, v in classes_val.items())
        elif isinstance(classes_val, (list, tuple, set)):
            counts = Counter(classes_val)
            classes_str = ", ".join(f"{k} ×{v}" for k, v in counts.items())
        else:
            classes_str = "Unknown"

        cls_lbl = QLabel(f"Detected: {classes_str}")
        cls_lbl.setStyleSheet("color: #ddd; font-size: 12px;")
        cls_lbl.setWordWrap(True)
        info.addWidget(cls_lbl)

        try:
            num_obj = int(record.get("num_objects", 0))
        except (TypeError, ValueError):
            num_obj = 0
        try:
            max_conf = float(record.get("max_conf", 0.0))
        except (TypeError, ValueError):
            max_conf = 0.0

        conf_lbl = QLabel(f"Objects: {num_obj}  |  Max conf: {max_conf:.2f}")
        conf_lbl.setStyleSheet("color: #999; font-size: 11px;")
        info.addWidget(conf_lbl)

        location_str = record.get("location_str", "Unknown")
        location = record.get("location")

        has_coords = (
            isinstance(location, dict)
            and location.get("lat") is not None
            and location.get("lon") is not None
            and location_str not in (None, "", "Unknown")
        )

        if has_coords:
            loc_lbl = QLabel(f"Location: {location_str}")
            loc_lbl.setStyleSheet("color: #81c784; font-size: 11px;")
            info.addWidget(loc_lbl)

            btn = QPushButton("View on Map")
            btn.setFixedHeight(24)
            try:
                lat = float(location["lat"])
                lon = float(location["lon"])
                btn.clicked.connect(
                    lambda _, a=lat, b=lon: webbrowser.open(
                        f"https://www.google.com/maps?q={a},{b}"
                    )
                )
            except (TypeError, ValueError):
                btn.setEnabled(False)
            info.addWidget(btn)
        else:
            loc_lbl = QLabel(f"Location: {location_str if location_str else 'Unknown'}")
            loc_lbl.setStyleSheet("color: #777; font-size: 11px;")
            info.addWidget(loc_lbl)

        info.addStretch()
        layout.addLayout(info, 1)


class HistoryPage(QWidget):
    def __init__(self, evidence_manager: EvidenceManager):
        super().__init__()
        self.evidence_manager = evidence_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QHBoxLayout()
        title = QLabel("Detection History")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #fff;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.reload)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: #1e1e1e; }")
        self.container = QWidget()
        self.container.setStyleSheet("background: #1e1e1e;")
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setSpacing(8)
        self.vbox.setContentsMargins(4, 4, 4, 4)
        self.vbox.addStretch()
        self.scroll.setWidget(self.container)

        layout.addWidget(self.scroll, 1)
        self.reload()

    def reload(self):
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        records = self.evidence_manager.get_history()
        if not records:
            empty = QLabel("No detection records yet.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
            self.vbox.insertWidget(0, empty)
            return

        for rec in records:
            path = self.evidence_manager.get_image_path(rec)
            if os.path.exists(path):
                card = HistoryCard(rec, path)
                self.vbox.insertWidget(self.vbox.count() - 1, card)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E-Safai - Garbage Detection System")
        self.resize(1300, 820)

        self.evidence_manager = EvidenceManager()
        self.detector = GarbageDetector("models/best.pt", conf=0.15)
        self.workers = {}
        self.screens = {}
        self.status_labels = {}
        self.last_frames = {}
        self.config = self.load_config()

        # Live location state
        self.location_labels = {}
        self.map_buttons = {}
        self.camera_locations = {}

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar ----
        sidebar = QFrame()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet(
            "QFrame { background: #1a1a1a; border-right: 1px solid #333; }"
        )
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 16, 12, 16)
        side_layout.setSpacing(8)

        logo = QLabel("E-Safai")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("color: #fff; font-size: 20px; font-weight: bold; padding: 8px;")
        side_layout.addWidget(logo)

        self.btn_live = QPushButton("Live Cameras")
        self.btn_history = QPushButton("History")
        self.btn_stats = QPushButton("Statistics")
        for b in (self.btn_live, self.btn_history, self.btn_stats):
            b.setCheckable(True)
            b.setStyleSheet("""
                QPushButton {
                    text-align: left; padding: 10px 14px; color: #ccc;
                    background: transparent; border: none; border-radius: 6px;
                    font-size: 14px;
                }
                QPushButton:hover { background: #2a2a2a; }
                QPushButton:checked { background: #0d47a1; color: #fff; }
            """)
        self.btn_live.setChecked(True)
        self.btn_live.clicked.connect(lambda: self.switch_page(0))
        self.btn_history.clicked.connect(lambda: self.switch_page(1))
        self.btn_stats.clicked.connect(lambda: self.switch_page(2))
        side_layout.addWidget(self.btn_live)
        side_layout.addWidget(self.btn_history)
        side_layout.addWidget(self.btn_stats)
        side_layout.addStretch()
        root.addWidget(sidebar)

        # ---- Stacked pages ----
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.live_page = self._build_live_page()
        self.stack.addWidget(self.live_page)

        self.history_page = HistoryPage(self.evidence_manager)
        self.stack.addWidget(self.history_page)

        self.stats_page = StatsPage(self.evidence_manager)
        self.stack.addWidget(self.stats_page)

        # Auto-reconnect saved cameras
        for cid_str, cfg in self.config.items():
            cid = int(cid_str)
            if cfg.get("ip") and cfg.get("port"):
                self.start_camera(cid, cfg["ip"], cfg["port"])

    def _build_live_page(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        title = QLabel("Live Garbage Detection")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 4px;")
        root.addWidget(title, 0)

        grid = QGridLayout()
        grid.setSpacing(8)
        root.addLayout(grid, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        for i in range(4):
            container = QWidget()
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(2)

            loc_row = QWidget()
            loc_row.setStyleSheet("background: #1a1a1a; border-radius: 3px;")
            lr = QHBoxLayout(loc_row)
            lr.setContentsMargins(4, 2, 4, 2)
            lr.setSpacing(4)

            loc_label = QLabel("📍 Location: Unknown")
            loc_label.setStyleSheet("color: #4fc3f7; font-size: 11px;")
            lr.addWidget(loc_label, 1)

            map_btn = QPushButton("View on Map")
            map_btn.setFixedHeight(20)
            map_btn.setStyleSheet(
                "QPushButton { background: #0d47a1; color: #fff; border: none; "
                "border-radius: 3px; padding: 1px 6px; font-size: 10px; }"
                "QPushButton:hover { background: #1565c0; }"
            )
            map_btn.setVisible(False)
            map_btn.clicked.connect(lambda _, cid=i: self.open_map(cid))
            lr.addWidget(map_btn, 0)

            screen = CameraScreen()
            screen.mousePressEvent = lambda e, cid=i: self.on_screen_clicked(cid)

            status = QLabel("Not connected")
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status.setStyleSheet("color: #aaa; font-size: 12px;")

            vbox.addWidget(loc_row, 0)
            vbox.addWidget(screen, 1)
            vbox.addWidget(status, 0)
            grid.addWidget(container, i // 2, i % 2)

            self.screens[i] = screen
            self.status_labels[i] = status
            self.location_labels[i] = loc_label
            self.map_buttons[i] = map_btn

        return page

    def switch_page(self, idx):
        self.stack.setCurrentIndex(idx)
        self.btn_live.setChecked(idx == 0)
        self.btn_history.setChecked(idx == 1)
        self.btn_stats.setChecked(idx == 2)
        if idx == 1:
            self.history_page.reload()
        elif idx == 2:
            self.stats_page.refresh()

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        return {}

    def save_config(self):
        os.makedirs("configs", exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config, f, indent=2)

    def on_screen_clicked(self, cam_id):
        if cam_id in self.workers:
            return
        text, ok = QInputDialog.getText(
            self, f"Camera {cam_id + 1}",
            "Enter IP and Port (e.g., 192.168.1.5:8080):")
        if not ok or ":" not in text:
            return
        ip, port = text.split(":", 1)
        self.start_camera(cam_id, ip.strip(), port.strip())

    def start_camera(self, cam_id, ip, port):
        self.config[str(cam_id)] = {"ip": ip, "port": port}
        self.save_config()

        if cam_id in self.workers:
            try:
                self.workers[cam_id].stop()
            except Exception:
                pass
            del self.workers[cam_id]

        loc_mgr = LocationManager(ip, port)

        worker = CameraWorker(cam_id, ip, port, self.detector,
                              self.evidence_manager, loc_mgr)
        worker.frame_ready.connect(self.update_screen)
        worker.reset_screen.connect(self.on_reset_screen)
        worker.evidence_saved.connect(self.on_evidence_saved)
        worker.location_ready.connect(self.on_location_ready)
        worker.start()
        self.workers[cam_id] = worker
        self.screens[cam_id].setText("Connecting...")
        self.status_labels[cam_id].setText("Connecting...")
        self.location_labels[cam_id].setText("📍 Location: Locating...")
        self.map_buttons[cam_id].setVisible(False)

    def on_location_ready(self, cam_id, lat, lon):
        self.camera_locations[cam_id] = (lat, lon)
        if cam_id in self.location_labels:
            self.location_labels[cam_id].setText(f"📍 {lat:.5f}, {lon:.5f}")
        if cam_id in self.map_buttons:
            btn = self.map_buttons[cam_id]
            btn.setVisible(True)
            btn.setToolTip(f"{lat:.5f}, {lon:.5f}")

    def open_map(self, cam_id):
        loc = self.camera_locations.get(cam_id)
        if not loc:
            return
        lat, lon = loc
        webbrowser.open(f"https://www.google.com/maps?q={lat},{lon}")

    def on_evidence_saved(self, cam_id, record):
        if self.stack.currentIndex() == 1:
            self.history_page.reload()
        elif self.stack.currentIndex() == 2:
            self.stats_page.refresh()

    def on_reset_screen(self, cam_id, reason):
        if cam_id in self.workers:
            try:
                self.workers[cam_id].stop()
            except Exception:
                pass
            del self.workers[cam_id]

        self.last_frames.pop(cam_id, None)
        screen = self.screens[cam_id]
        screen._pixmap = None
        screen.setText("+")
        screen.setStyleSheet(
            "background: #222; color: #888; font-size: 36px; "
            "border: 2px dashed #555;")
        self.status_labels[cam_id].setText(f"Not connected ({reason})")
        screen.mousePressEvent = lambda e, cid=cam_id: self.on_screen_clicked(cid)

        if cam_id in self.location_labels:
            self.location_labels[cam_id].setText("📍 Location: Unknown")
        if cam_id in self.map_buttons:
            self.map_buttons[cam_id].setVisible(False)
        self.camera_locations.pop(cam_id, None)

    def update_screen(self, cam_id, frame, status):
        if cam_id not in self.workers:
            return
        self.status_labels[cam_id].setText(status)
        if frame is None:
            return
        h, w, ch = frame.shape
        qimg = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.last_frames[cam_id] = pix
        self.screens[cam_id].set_frame(pix)

    def closeEvent(self, event):
        for w in self.workers.values():
            w.stop()
        event.accept()