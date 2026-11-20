from PyQt6.QtWidgets import (QMainWindow, QWidget, QGridLayout, QLabel,
                             QPushButton, QInputDialog, QVBoxLayout, QSizePolicy)
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt
from camera_worker import CameraWorker
from detector_engine import GarbageDetector
import json, os


CONFIG_PATH = "configs/cameras.json"


class CameraScreen(QLabel):
    """A QLabel that always scales its pixmap to fit, keeping aspect ratio."""
    def __init__(self):
        super().__init__("+")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background: #222; color: #888; font-size: 36px; "
            "border: 2px dashed #555;"
        )
        # Key: allow the widget to shrink below its sizeHint
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(80, 60)   # Small floor, not a hard 600x350
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
        self._apply_pixmap()   # Re-scale existing frame on window resize


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E-Safai - Garbage Detection System")
        self.resize(1200, 800)

        self.detector = GarbageDetector("models/best.pt", conf=0.15)
        self.workers = {}
        self.screens = {}
        self.status_labels = {}
        self.last_frames = {}    # cam_id -> QPixmap (for resize re-scaling)
        self.config = self.load_config()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        title = QLabel("E-Safai")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 4px;")
        root.addWidget(title, 0)   # 0 stretch: title keeps its natural height

        grid = QGridLayout()
        grid.setSpacing(8)
        root.addLayout(grid, 1)    # 1 stretch: grid takes all remaining space

        # Make the 2x2 grid share space equally
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        for i in range(4):
            container = QWidget()
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(2)

            screen = CameraScreen()
            screen.mousePressEvent = lambda e, cid=i: self.on_screen_clicked(cid)

            status = QLabel("Not connected")
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status.setStyleSheet("color: #aaa; font-size: 12px;")

            vbox.addWidget(screen, 1)   # screen takes all vertical space
            vbox.addWidget(status, 0)   # status keeps natural height

            grid.addWidget(container, i // 2, i % 2)

            self.screens[i] = screen
            self.status_labels[i] = status

        # Auto-reconnect saved cameras
        for cid_str, cfg in self.config.items():
            cid = int(cid_str)
            if cfg.get("ip") and cfg.get("port"):
                self.start_camera(cid, cfg["ip"], cfg["port"])

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

        # Stop an existing worker cleanly before starting a new one
        if cam_id in self.workers:
            try:
                self.workers[cam_id].stop()
            except Exception:
                pass
            del self.workers[cam_id]

        worker = CameraWorker(cam_id, ip, port, self.detector)
        worker.frame_ready.connect(self.update_screen)
        worker.reset_screen.connect(self.on_reset_screen)   # NEW
        worker.start()
        self.workers[cam_id] = worker
        self.screens[cam_id].setText("Connecting...")
        self.status_labels[cam_id].setText("Connecting...")

    def on_reset_screen(self, cam_id, reason):
        """Called when worker gives up after 10s. Free the slot."""
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

        # Re-allow click
        screen.mousePressEvent = lambda e, cid=cam_id: self.on_screen_clicked(cid)
    
    def update_screen(self, cam_id, frame, status):
        self.status_labels[cam_id].setText(status)
        if frame is None:
            self.screens[cam_id].setText("No signal")
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