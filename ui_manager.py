from collections import Counter
import webbrowser
import time

from stats_page import StatsPage

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QLabel, QPushButton, QInputDialog,
    QVBoxLayout, QHBoxLayout, QSizePolicy, QStackedWidget, QScrollArea,
    QFrame, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QImage, QPixmap, QColor
from PyQt6.QtCore import Qt
from camera_worker import CameraWorker
from detector_engine import GarbageDetector
from evidence_manager import EvidenceManager
from location_manager import LocationManager
import json, os


CONFIG_PATH = "configs/cameras.json"

# Shared with Statistics — visual system only
PALETTE = {
    "bg": "#0c1118",
    "surface": "#121925",
    "card": "#161e2b",
    "card_alt": "#1a2433",
    "stroke": "#2a3648",
    "text": "#e8eef7",
    "muted": "#8b9bb0",
    "dim": "#5d6d82",
    "accent": "#3ee0a2",
    "accent_2": "#5eb8ff",
}
CAM_COLORS = ["#5eb8ff", "#3ee0a2", "#f6c177", "#ff8b7b"]
CLASS_COLORS = [
    "#ff8b7b", "#c4a7e7", "#5eb8ff", "#3ee0a2",
    "#f6c177", "#9ccfd8", "#ea9a97", "#7aa2f7", "#d4e157",
]


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgba(c, a):
    r, g, b = (int(round(x * 255)) for x in _hex(c))
    return f"rgba({r}, {g}, {b}, {a})"


def _chip(text, color):
    lab = QLabel(text)
    lab.setStyleSheet(
        f"color: {color}; background: {_rgba(color, 0.14)}; "
        f"border: 1px solid {_rgba(color, 0.35)}; border-radius: 8px; "
        f"padding: 4px 9px; font-size: 11px; font-weight: 600;"
    )
    return lab


class CameraScreen(QLabel):
    def __init__(self):
        super().__init__("+")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 #0d1520, stop:1 #111b28);"
            f"color: {PALETTE['dim']}; font-size: 40px; font-weight: 300;"
            f"border: 2px dashed {PALETTE['stroke']};"
            f"border-radius: 14px;"
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
        self.setObjectName("HistoryCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumHeight(168)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 16, 12)
        layout.setSpacing(16)

        thumb = QLabel()
        thumb.setObjectName("HistThumb")
        thumb.setFixedSize(220, 144)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(image_path)
        if not pix.isNull():
            thumb.setPixmap(pix.scaled(
                220, 144,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(8)
        info.setContentsMargins(0, 2, 0, 2)

        ts_lbl = QLabel(record.get("timestamp_str", "Unknown time"))
        ts_lbl.setObjectName("HistTime")
        info.addWidget(ts_lbl)

        try:
            cam_id = int(record.get("cam_id", 0))
        except (TypeError, ValueError):
            cam_id = 0
        cam_color = CAM_COLORS[cam_id % 4]

        classes_val = record.get("classes", {})
        class_items = []
        if isinstance(classes_val, dict):
            class_items = list(classes_val.items())
            classes_str = ", ".join(f"{k} ×{v}" for k, v in classes_val.items())
        elif isinstance(classes_val, (list, tuple, set)):
            counts = Counter(classes_val)
            class_items = list(counts.items())
            classes_str = ", ".join(f"{k} ×{v}" for k, v in counts.items())
        else:
            classes_str = "Unknown"

        try:
            num_obj = int(record.get("num_objects", 0))
        except (TypeError, ValueError):
            num_obj = 0
        try:
            max_conf = float(record.get("max_conf", 0.0))
        except (TypeError, ValueError):
            max_conf = 0.0

        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(_chip(f"Camera {cam_id + 1}", cam_color))
        meta.addWidget(_chip(f"{num_obj} object{'s' if num_obj != 1 else ''}", PALETTE["accent_2"]))
        meta.addWidget(_chip(f"Max conf {max_conf:.2f}", PALETTE["accent"]))
        meta.addStretch()
        info.addLayout(meta)

        detected_lbl = QLabel("DETECTED")
        detected_lbl.setObjectName("HistKicker")
        info.addWidget(detected_lbl)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        if class_items:
            for i, (name, count) in enumerate(class_items):
                color = CLASS_COLORS[i % len(CLASS_COLORS)]
                chips.addWidget(_chip(f"{name}  ×{count}", color))
        else:
            fallback = QLabel(f"Detected: {classes_str}")
            fallback.setObjectName("HistBody")
            fallback.setWordWrap(True)
            chips.addWidget(fallback)
        chips.addStretch()
        info.addLayout(chips)

        location_str = record.get("location_str", "Unknown")
        location = record.get("location")

        has_coords = (
            isinstance(location, dict)
            and location.get("lat") is not None
            and location.get("lon") is not None
            and location_str not in (None, "", "Unknown")
        )

        loc_row = QHBoxLayout()
        loc_row.setSpacing(10)

        if has_coords:
            loc_lbl = QLabel(f"Location  ·  {location_str}")
            loc_lbl.setObjectName("HistLocOn")
            loc_row.addWidget(loc_lbl, 1)

            btn = QPushButton("View on Map")
            btn.setObjectName("MapBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
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
            loc_row.addWidget(btn, 0)
        else:
            loc_lbl = QLabel(
                f"Location  ·  {location_str if location_str else 'Unknown'}"
            )
            loc_lbl.setObjectName("HistLocOff")
            loc_row.addWidget(loc_lbl, 1)

        info.addLayout(loc_row)
        info.addStretch()
        layout.addLayout(info, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)


class HistoryPage(QWidget):
    def __init__(self, evidence_manager: EvidenceManager):
        super().__init__()
        self.evidence_manager = evidence_manager
        self.setObjectName("HistoryRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self._qss())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(16)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        eyebrow = QLabel("E-SAFAI  ·  EVIDENCE")
        eyebrow.setObjectName("Eyebrow")
        titles.addWidget(eyebrow)

        title = QLabel("Detection History")
        title.setObjectName("PageTitle")
        titles.addWidget(title)

        self.meta_label = QLabel("Stored detections from connected cameras")
        self.meta_label.setObjectName("PageMeta")
        titles.addWidget(self.meta_label)
        header.addLayout(titles, 1)

        refresh_col = QVBoxLayout()
        refresh_col.addStretch()
        refresh_btn = QPushButton("  Refresh")
        refresh_btn.setObjectName("RefreshBtn")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.reload)
        refresh_btn.setMinimumHeight(34)
        refresh_col.addWidget(refresh_btn)
        header.addLayout(refresh_col, 0)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.container.setObjectName("HistoryList")
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setSpacing(12)
        self.vbox.setContentsMargins(2, 2, 10, 8)
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
            self.meta_label.setText("No stored detections yet")
            empty = QFrame()
            empty.setObjectName("EmptyState")
            el = QVBoxLayout(empty)
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon = QLabel("◌")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet("color: #5d6d82; font-size: 28px;")
            msg = QLabel("No detection records yet")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setObjectName("EmptyTitle")
            hint = QLabel("New evidence cards will appear here after garbage is detected.")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setObjectName("PageMeta")
            el.addWidget(icon)
            el.addWidget(msg)
            el.addWidget(hint)
            self.vbox.insertWidget(0, empty)
            return

        n = len(records)
        noun = "detection" if n == 1 else "detections"
        self.meta_label.setText(f"{n} stored {noun}  ·  newest first")

        for rec in records:
            path = self.evidence_manager.get_image_path(rec)
            if os.path.exists(path):
                card = HistoryCard(rec, path)
                self.vbox.insertWidget(self.vbox.count() - 1, card)

    @staticmethod
    def _qss():
        return f"""
            QWidget#HistoryRoot {{
                background: {PALETTE["bg"]};
                color: {PALETTE["text"]};
                font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif;
            }}
            QWidget#HistoryList {{
                background: {PALETTE["bg"]};
            }}
            QLabel#Eyebrow {{
                color: {PALETTE["accent"]};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2.4px;
            }}
            QLabel#PageTitle {{
                color: {PALETTE["text"]};
                font-size: 26px;
                font-weight: 800;
                letter-spacing: -0.4px;
            }}
            QLabel#PageMeta {{
                color: {PALETTE["muted"]};
                font-size: 12px;
            }}
            QLabel#HistTime {{
                color: {PALETTE["accent_2"]};
                font-size: 16px;
                font-weight: 800;
                letter-spacing: -0.2px;
            }}
            QLabel#HistKicker {{
                color: {PALETTE["dim"]};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.4px;
            }}
            QLabel#HistBody {{
                color: {PALETTE["text"]};
                font-size: 12px;
            }}
            QLabel#HistLocOn {{
                color: {PALETTE["accent"]};
                font-size: 12px;
            }}
            QLabel#HistLocOff {{
                color: {PALETTE["dim"]};
                font-size: 12px;
            }}
            QLabel#EmptyTitle {{
                color: {PALETTE["text"]};
                font-size: 15px;
                font-weight: 700;
            }}
            QLabel#HistThumb {{
                background: {PALETTE["surface"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 12px;
            }}
            QFrame#HistoryCard {{
                background: {PALETTE["card"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 16px;
            }}
            QFrame#EmptyState {{
                background: {PALETTE["card"]};
                border: 1px dashed {PALETTE["stroke"]};
                border-radius: 16px;
                min-height: 220px;
            }}
            QPushButton#RefreshBtn {{
                background: {PALETTE["accent"]};
                color: #062016;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 700;
                font-size: 13px;
            }}
            QPushButton#RefreshBtn:hover {{
                background: #62f0bb;
            }}
            QPushButton#RefreshBtn:pressed {{
                background: #2bc48d;
            }}
            QPushButton#MapBtn {{
                background: {PALETTE["card_alt"]};
                color: {PALETTE["text"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 8px;
                padding: 4px 12px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton#MapBtn:hover {{
                border: 1px solid {PALETTE["accent_2"]};
                color: {PALETTE["accent_2"]};
            }}
            QScrollArea {{
                border: none;
                background: {PALETTE["bg"]};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {PALETTE["stroke"]};
                border-radius: 5px;
                min-height: 32px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """


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
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(
            f"QFrame {{ background: {PALETTE['surface']};"
            f"  border-right: 1px solid {PALETTE['stroke']}; }}"
        )
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(14, 20, 14, 20)
        side_layout.setSpacing(6)

        # -- Logo area --
        logo_frame = QFrame()
        logo_frame.setStyleSheet(
            f"background: transparent; border: none;"
            f"border-bottom: 1px solid {PALETTE['stroke']};"
            f"padding-bottom: 12px; margin-bottom: 6px;"
        )
        logo_inner = QVBoxLayout(logo_frame)
        logo_inner.setContentsMargins(0, 0, 0, 10)
        logo_inner.setSpacing(2)

        logo_icon = QLabel("🛡️")
        logo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_icon.setStyleSheet("font-size: 28px; background: transparent; border: none;")
        logo_inner.addWidget(logo_icon)

        logo = QLabel("E-Safai")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            f"color: {PALETTE['text']}; font-size: 22px; font-weight: 800;"
            f"letter-spacing: -0.5px; background: transparent; border: none;"
        )
        logo_inner.addWidget(logo)

        logo_sub = QLabel("Smart Surveillance")
        logo_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_sub.setStyleSheet(
            f"color: {PALETTE['dim']}; font-size: 10px; font-weight: 600;"
            f"letter-spacing: 1.8px; text-transform: uppercase;"
            f"background: transparent; border: none;"
        )
        logo_inner.addWidget(logo_sub)
        side_layout.addWidget(logo_frame)

        side_layout.addSpacing(8)

        nav_label = QLabel("NAVIGATION")
        nav_label.setStyleSheet(
            f"color: {PALETTE['dim']}; font-size: 9px; font-weight: 700;"
            f"letter-spacing: 2px; padding: 4px 8px;"
        )
        side_layout.addWidget(nav_label)

        self.btn_live = QPushButton("  📹  Live Cameras")
        self.btn_history = QPushButton("  📋  History")
        self.btn_stats = QPushButton("  📊  Statistics")
        _nav_btn_qss = f"""
            QPushButton {{
                text-align: left; padding: 11px 14px; color: {PALETTE['muted']};
                background: transparent; border: none; border-radius: 10px;
                font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{
                background: {_rgba(PALETTE['accent_2'], 0.08)};
                color: {PALETTE['text']};
            }}
            QPushButton:checked {{
                background: {_rgba(PALETTE['accent_2'], 0.15)};
                color: {PALETTE['accent_2']};
                border-left: 3px solid {PALETTE['accent_2']};
            }}
        """
        for b in (self.btn_live, self.btn_history, self.btn_stats):
            b.setCheckable(True)
            b.setStyleSheet(_nav_btn_qss)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_live.setChecked(True)
        self.btn_live.clicked.connect(lambda: self.switch_page(0))
        self.btn_history.clicked.connect(lambda: self.switch_page(1))
        self.btn_stats.clicked.connect(lambda: self.switch_page(2))
        side_layout.addWidget(self.btn_live)
        side_layout.addWidget(self.btn_history)
        side_layout.addWidget(self.btn_stats)
        side_layout.addStretch()

        # -- Sidebar footer --
        ver_label = QLabel("Powered By Sharpen AI")
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_label.setStyleSheet(
            f"color: {PALETTE['dim']}; font-size: 10px; padding: 8px;"
        )
        side_layout.addWidget(ver_label)
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
        page.setObjectName("LiveRoot")
        page.setStyleSheet(f"""
            QWidget#LiveRoot {{
                background: {PALETTE['bg']};
                font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif;
            }}
        """)
        root = QVBoxLayout(page)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ── Header ──
        header = QVBoxLayout()
        header.setSpacing(3)

        eyebrow = QLabel("E-SAFAI")
        eyebrow.setStyleSheet(
            f"color: {PALETTE['accent']}; font-size: 10px; font-weight: 700;"
            f"letter-spacing: 2.6px;"
        )
        header.addWidget(eyebrow)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("Live Garbage Detection")
        title.setStyleSheet(
            f"color: {PALETTE['text']}; font-size: 24px; font-weight: 800;"
            f"letter-spacing: -0.4px;"
        )
        title_row.addWidget(title)
        title_row.addStretch()

        # Live indicator dot
        live_dot = QLabel("●  LIVE")
        live_dot.setStyleSheet(
            f"color: {PALETTE['accent']}; font-size: 11px; font-weight: 700;"
            f"letter-spacing: 1px;"
            f"background: {_rgba(PALETTE['accent'], 0.12)};"
            f"border: 1px solid {_rgba(PALETTE['accent'], 0.3)};"
            f"border-radius: 10px; padding: 4px 12px 4px 8px;"
        )
        title_row.addWidget(live_dot)
        header.addLayout(title_row)

        subtitle = QLabel("Real-time monitoring across all connected camera feeds")
        subtitle.setStyleSheet(
            f"color: {PALETTE['muted']}; font-size: 12px;"
        )
        header.addWidget(subtitle)
        root.addLayout(header, 0)

        # ── Thin separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {PALETTE['stroke']}; border: none;")
        root.addWidget(sep)

        # ── Camera grid ──
        grid = QGridLayout()
        grid.setSpacing(12)
        root.addLayout(grid, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        cam_accent_colors = [PALETTE['accent_2'], PALETTE['accent'], "#f6c177", "#ff8b7b"]

        for i in range(4):
            accent = cam_accent_colors[i]

            # Outer card container
            card = QFrame()
            card.setObjectName(f"CamCard{i}")
            card.setStyleSheet(f"""
                QFrame#CamCard{i} {{
                    background: {PALETTE['card']};
                    border: 1px solid {PALETTE['stroke']};
                    border-radius: 16px;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(6)

            # -- Top bar: camera label + location --
            top_bar = QHBoxLayout()
            top_bar.setSpacing(8)

            cam_badge = QLabel(f"  CAM {i + 1}")
            cam_badge.setStyleSheet(
                f"color: {accent};"
                f"background: {_rgba(accent, 0.12)};"
                f"border: 1px solid {_rgba(accent, 0.3)};"
                f"border-radius: 8px; padding: 3px 10px;"
                f"font-size: 10px; font-weight: 800; letter-spacing: 1.2px;"
            )
            top_bar.addWidget(cam_badge)

            loc_label = QLabel("📍 Location: Unknown")
            loc_label.setStyleSheet(
                f"color: {PALETTE['dim']}; font-size: 11px; font-weight: 500;"
            )
            top_bar.addWidget(loc_label, 1)

            map_btn = QPushButton("🗺 Map")
            map_btn.setFixedHeight(24)
            map_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            map_btn.setStyleSheet(
                f"QPushButton {{ background: {PALETTE['card_alt']};"
                f"  color: {PALETTE['text']}; border: 1px solid {PALETTE['stroke']};"
                f"  border-radius: 7px; padding: 2px 10px;"
                f"  font-size: 10px; font-weight: 600; }}"
                f"QPushButton:hover {{ border-color: {PALETTE['accent_2']};"
                f"  color: {PALETTE['accent_2']}; }}"
            )
            map_btn.setVisible(False)
            map_btn.clicked.connect(lambda _, cid=i: self.open_map(cid))
            top_bar.addWidget(map_btn, 0)
            card_layout.addLayout(top_bar)

            # -- Camera screen --
            screen = CameraScreen()
            screen.setStyleSheet(
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 #0d1520, stop:1 #111b28);"
                f"color: {PALETTE['dim']}; font-size: 40px; font-weight: 300;"
                f"border: 2px dashed {PALETTE['stroke']};"
                f"border-radius: 14px;"
            )
            screen.mousePressEvent = lambda e, cid=i: self.on_screen_clicked(cid)
            card_layout.addWidget(screen, 1)

            # -- Bottom status bar --
            bottom_bar = QHBoxLayout()
            bottom_bar.setSpacing(6)

            status_dot = QLabel("●")
            status_dot.setFixedWidth(14)
            status_dot.setStyleSheet(
                f"color: {PALETTE['dim']}; font-size: 8px;"
            )
            bottom_bar.addWidget(status_dot)

            status = QLabel("Not connected")
            status.setStyleSheet(
                f"color: {PALETTE['muted']}; font-size: 11px; font-weight: 500;"
            )
            bottom_bar.addWidget(status, 1)

            connect_hint = QLabel("Click to connect ›")
            connect_hint.setStyleSheet(
                f"color: {PALETTE['dim']}; font-size: 10px; font-style: italic;"
            )
            bottom_bar.addWidget(connect_hint)
            card_layout.addLayout(bottom_bar)

            grid.addWidget(card, i // 2, i % 2)

            self.screens[i] = screen
            self.status_labels[i] = status
            self.location_labels[i] = loc_label
            self.map_buttons[i] = map_btn
            # Store extra UI refs for status dot and connect hint
            if not hasattr(self, '_status_dots'):
                self._status_dots = {}
                self._connect_hints = {}
            self._status_dots[i] = status_dot
            self._connect_hints[i] = connect_hint

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
        self.screens[cam_id].setText("⟳")
        self.screens[cam_id].setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 #0d1520, stop:1 #111b28);"
            f"color: {PALETTE['accent_2']}; font-size: 32px; font-weight: 300;"
            f"border: 2px solid {_rgba(PALETTE['accent_2'], 0.3)};"
            f"border-radius: 14px;"
        )
        self.status_labels[cam_id].setText("Connecting...")
        self.status_labels[cam_id].setStyleSheet(
            f"color: {PALETTE['accent_2']}; font-size: 11px; font-weight: 500;"
        )
        self.location_labels[cam_id].setText("📍 Location: Locating...")
        self.location_labels[cam_id].setStyleSheet(
            f"color: {PALETTE['accent_2']}; font-size: 11px; font-weight: 500;"
        )
        self.map_buttons[cam_id].setVisible(False)
        if hasattr(self, '_status_dots') and cam_id in self._status_dots:
            self._status_dots[cam_id].setStyleSheet(
                f"color: {PALETTE['accent_2']}; font-size: 8px;"
            )
        if hasattr(self, '_connect_hints') and cam_id in self._connect_hints:
            self._connect_hints[cam_id].setText("Establishing connection...")
            self._connect_hints[cam_id].setStyleSheet(
                f"color: {PALETTE['accent_2']}; font-size: 10px; font-style: italic;"
            )

    def on_location_ready(self, cam_id, lat, lon):
        self.camera_locations[cam_id] = (lat, lon)
        if cam_id in self.location_labels:
            self.location_labels[cam_id].setText(f"📍 {lat:.5f}, {lon:.5f}")
            self.location_labels[cam_id].setStyleSheet(
                f"color: {PALETTE['accent']}; font-size: 11px; font-weight: 500;"
            )
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
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 #0d1520, stop:1 #111b28);"
            f"color: {PALETTE['dim']}; font-size: 40px; font-weight: 300;"
            f"border: 2px dashed {PALETTE['stroke']};"
            f"border-radius: 14px;"
        )
        self.status_labels[cam_id].setText(f"Disconnected ({reason})")
        self.status_labels[cam_id].setStyleSheet(
            f"color: #ff8b7b; font-size: 11px; font-weight: 500;"
        )
        screen.mousePressEvent = lambda e, cid=cam_id: self.on_screen_clicked(cid)

        if cam_id in self.location_labels:
            self.location_labels[cam_id].setText("📍 Location: Unknown")
            self.location_labels[cam_id].setStyleSheet(
                f"color: {PALETTE['dim']}; font-size: 11px; font-weight: 500;"
            )
        if cam_id in self.map_buttons:
            self.map_buttons[cam_id].setVisible(False)
        self.camera_locations.pop(cam_id, None)
        if hasattr(self, '_status_dots') and cam_id in self._status_dots:
            self._status_dots[cam_id].setStyleSheet(
                f"color: #ff8b7b; font-size: 8px;"
            )
        if hasattr(self, '_connect_hints') and cam_id in self._connect_hints:
            self._connect_hints[cam_id].setText("Click to reconnect ›")
            self._connect_hints[cam_id].setStyleSheet(
                f"color: {PALETTE['dim']}; font-size: 10px; font-style: italic;"
            )

    def update_screen(self, cam_id, frame, status):
        if cam_id not in self.workers:
            return
        self.status_labels[cam_id].setText(status)
        self.status_labels[cam_id].setStyleSheet(
            f"color: {PALETTE['accent']}; font-size: 11px; font-weight: 500;"
        )
        if hasattr(self, '_status_dots') and cam_id in self._status_dots:
            self._status_dots[cam_id].setStyleSheet(
                f"color: {PALETTE['accent']}; font-size: 8px;"
            )
        if hasattr(self, '_connect_hints') and cam_id in self._connect_hints:
            self._connect_hints[cam_id].setText("")
        if frame is None:
            return
        h, w, ch = frame.shape
        qimg = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.last_frames[cam_id] = pix
        self.screens[cam_id].set_frame(pix)
        # Update screen border when receiving frames
        self.screens[cam_id].setStyleSheet(
            f"background: #0a0f17; border: 1px solid {PALETTE['stroke']};"
            f"border-radius: 14px;"
        )

    def closeEvent(self, event):
        for w in self.workers.values():
            w.stop()
        event.accept()