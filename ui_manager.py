from collections import Counter
import webbrowser
import time

from stats_page import StatsPage

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QLabel, QPushButton, QInputDialog,
    QVBoxLayout, QHBoxLayout, QSizePolicy, QStackedWidget, QScrollArea,
    QFrame, QGraphicsDropShadowEffect, QDialog, QFormLayout, QComboBox,
    QListView, QLineEdit, 
)
from PyQt6.QtGui import QImage, QPixmap, QColor, QPainter, QIcon, QPainterPath
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtSvg import QSvgRenderer
from camera_worker import CameraWorker
from detector_engine import GarbageDetector
from evidence_manager import EvidenceManager
from location_manager import LocationManager
import json, os
from PyQt6.QtCore import Qt, QSize, QRectF, QPropertyAnimation, QEasingCurve


CONFIG_PATH = "configs/cameras.json"

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
    "warn": "#f6c177",
    "danger": "#ff8b7b",
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


# ─────────────────────────────────────────────────────────────
# SVG icon system — Lucide-style, theme-colored
# ─────────────────────────────────────────────────────────────
_ICONS = {
    "map-pin": """
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
        <circle cx="12" cy="10" r="3" fill="{color}" stroke="none"/>
    """,
    "camera": """
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
        <circle cx="12" cy="13" r="4"/>
    """,
    "archive": """
        <rect x="3" y="3" width="18" height="5" rx="1"/>
        <path d="M5 8v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8"/>
        <path d="M10 12h4"/>
    """,
    "bar-chart": """
        <line x1="12" y1="20" x2="12" y2="10"/>
        <line x1="18" y1="20" x2="18" y2="4"/>
        <line x1="6" y1="20" x2="6" y2="16"/>
    """,
    "map": """
        <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/>
        <line x1="8" y1="2" x2="8" y2="18"/>
        <line x1="16" y1="6" x2="16" y2="22"/>
    """,
    "recycle": """
        <path d="M7 19H4.815a1.83 1.83 0 0 1-1.57-.881 1.785 1.785 0 0 1-.004-1.784L7.196 9.5"/>
        <path d="M11 19h8.203a1.83 1.83 0 0 0 1.556-.89 1.784 1.784 0 0 0 0-1.775l-1.226-2.12"/>
        <path d="M14 16l-3 3 3 3"/>
        <path d="M8.293 13.596L7.196 9.5 3.1 10.598"/>
        <path d="M9.344 5.811l.23-.395A1.83 1.83 0 0 1 11.138 4.5h.002a1.83 1.83 0 0 1 1.56.893l1.84 3.176"/>
        <path d="M13.378 9.633l4.096 1.098 1.097-4.096"/>
    """,
    "zap": """
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    """,
}


def _svg_pixmap(name, size=18, color=None, stroke_width=2.0):
    """Render a Lucide-style icon from the dict above at `size` px in `color`."""
    if color is None:
        color = PALETTE["accent_2"]
    body = _ICONS[name].format(color=color)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).encode("utf-8")
    renderer = QSvgRenderer(svg)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pm


def _svg_icon(name, size=18, color=None, stroke_width=2.0):
    """Same as _svg_pixmap but returns a QIcon, for QPushButton.setIcon()."""
    return QIcon(_svg_pixmap(name, size, color, stroke_width))


def _svg_label(name, size=18, color=None, stroke_width=2.0):
    """A QLabel preloaded with an SVG icon pixmap."""
    lab = QLabel()
    lab.setFixedSize(size, size)
    lab.setPixmap(_svg_pixmap(name, size, color, stroke_width))
    lab.setStyleSheet("background: transparent; border: none;")
    return lab


# ─────────────────────────────────────────────────────────────
# Camera connection dialog
# ─────────────────────────────────────────────────────────────
class CameraDialog(QDialog):
    IP_SAMPLES = ["192.168.1.10", "192.168.1.11", "192.168.0.100", "10.0.0.5"]
    PORT_SAMPLES = ["8080", "8081", "554", "8554", "9000"]

    def __init__(self, cam_id, current_ip="", current_port="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Camera {cam_id + 1} — Connection Settings")
        self.setMinimumWidth(420)
        self.setModal(True)

        self.setStyleSheet(f"""
            QDialog {{ background-color: {PALETTE['surface']}; color: {PALETTE['text']}; }}
            QLabel {{ color: {PALETTE['text']}; background: transparent; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 22, 24, 20)

        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        title_lbl = QLabel(f"Camera {cam_id + 1} Configuration")
        title_lbl.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {PALETTE['text']};")
        header_box.addWidget(title_lbl)

        hint = QLabel("Enter camera's IP address & port, or select a preset.")
        hint.setStyleSheet(f"font-size: 12px; color: {PALETTE['muted']};")
        header_box.addWidget(hint)
        layout.addLayout(header_box)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.ip_combo = QComboBox()
        self.ip_combo.setEditable(True)
        self.ip_combo.setView(QListView())
        self.ip_combo.addItems(self.IP_SAMPLES)
        self.ip_combo.setStyleSheet(self._combo_style())
        self.ip_combo.lineEdit().setPlaceholderText("e.g. 192.168.1.10")
        if current_ip:
            self.ip_combo.setEditText(str(current_ip))
        else:
            self.ip_combo.setEditText("")

        ip_label = QLabel("IP Address:")
        ip_label.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {PALETTE['text']};")
        form.addRow(ip_label, self.ip_combo)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setView(QListView())
        self.port_combo.addItems(self.PORT_SAMPLES)
        self.port_combo.setStyleSheet(self._combo_style())
        self.port_combo.lineEdit().setPlaceholderText("e.g. 8080")
        if current_port:
            self.port_combo.setEditText(str(current_port))
        else:
            self.port_combo.setEditText("")

        port_label = QLabel("Port:")
        port_label.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {PALETTE['text']};")
        form.addRow(port_label, self.port_combo)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['card_alt']};
                color: {PALETTE['muted']};
                border: 1px solid {PALETTE['stroke']};
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #24344a;
                color: {PALETTE['text']};
                border-color: {PALETTE['dim']};
            }}
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setDefault(True)
        self.btn_connect.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4ff0b0, stop:1 {PALETTE['accent']});
                color: #062016;
                border: none;
                border-radius: 8px;
                padding: 8px 22px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background: #62f0bb; }}
        """)
        self.btn_connect.clicked.connect(self._on_accept)
        btn_layout.addWidget(self.btn_connect)

        layout.addLayout(btn_layout)

    @staticmethod
    def _combo_style():
        return f"""
            QComboBox {{
                background-color: {PALETTE['card_alt']};
                color: {PALETTE['text']};
                border: 1px solid {PALETTE['stroke']};
                border-radius: 8px;
                padding: 7px 12px;
                font-size: 13px;
                font-weight: 500;
                min-height: 22px;
            }}
            QComboBox:hover {{ border-color: {PALETTE['accent_2']}; }}
            QComboBox:focus {{ border-color: {PALETTE['accent']}; }}
            QComboBox QLineEdit {{
                color: {PALETTE['text']};
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: 500;
                selection-background-color: #24344a;
                selection-color: {PALETTE['accent']};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border-left: 1px solid {PALETTE['stroke']};
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                background-color: {PALETTE['card']};
            }}
            QComboBox::drop-down:hover {{ background-color: #24344a; }}
            QComboBox::down-arrow {{
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {PALETTE['muted']};
                width: 0px;
                height: 0px;
            }}
            QComboBox::down-arrow:hover {{ border-top-color: {PALETTE['accent']}; }}
            QComboBox QAbstractItemView {{
                background-color: {PALETTE['card']};
                color: {PALETTE['text']};
                border: 1px solid {PALETTE['stroke']};
                border-radius: 8px;
                padding: 4px;
                selection-background-color: #24344a;
                selection-color: {PALETTE['accent']};
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 26px;
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {PALETTE['card_alt']};
                color: {PALETTE['accent_2']};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #24344a;
                color: {PALETTE['accent']};
            }}
        """

    def _on_accept(self):
        ip = self.ip_combo.currentText().strip()
        port = self.port_combo.currentText().strip()
        if not ip or not port:
            if not ip:
                self.ip_combo.setStyleSheet(self._combo_style() + " QComboBox { border: 1px solid #ff8b7b; }")
            if not port:
                self.port_combo.setStyleSheet(self._combo_style() + " QComboBox { border: 1px solid #ff8b7b; }")
            return
        self.accept()

    def get_values(self):
        return (
            self.ip_combo.currentText().strip(),
            self.port_combo.currentText().strip(),
        )


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

# History Page's Design

HIST_ACCENT = PALETTE["accent_2"]          # light blue


def _hist_rgba(color, alpha):
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def _info_chip(text):
    """Uniform pill used for timestamp-adjacent info: camera, objects, conf."""
    lbl = QLabel(text)
    lbl.setObjectName("HistChip")
    return lbl


def _class_pill(name, count, color):
    """Neutral pill with a small colour dot (dot colour = class colour used
    in the Statistics donut, so the two dashboards read the same)."""
    pill = QFrame()
    pill.setObjectName("HistClassPill")
    lay = QHBoxLayout(pill)
    lay.setContentsMargins(10, 4, 10, 4)
    lay.setSpacing(7)

    dot = QLabel()
    dot.setFixedSize(8, 8)
    dot.setStyleSheet(f"background: {color}; border-radius: 4px; border: none;")
    lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

    txt = QLabel(f"{name}")
    txt.setObjectName("HistClassName")
    lay.addWidget(txt)

    cnt = QLabel(f"×{count}")
    cnt.setObjectName("HistClassCount")
    lay.addWidget(cnt)
    return pill


def _rounded_thumb(pix, w, h, radius):
    """Scale (keeping the full evidence frame visible) and round the corners."""
    scaled = pix.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    x = (w - scaled.width()) / 2.0
    y = (h - scaled.height()) / 2.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, scaled.width(), scaled.height()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(int(x), int(y), scaled)
    p.end()
    return out


class HistoryCard(QFrame):
    _SHADOW_REST = 22
    _SHADOW_HOVER = 40

    def __init__(self, record, image_path):
        super().__init__()
        self.setObjectName("HistoryCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumHeight(168)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self._qss())

        # left accent strip + content
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        strip = QFrame()
        strip.setObjectName("HistAccent")
        strip.setFixedWidth(4)
        outer.addWidget(strip)

        layout = QHBoxLayout()
        layout.setContentsMargins(14, 12, 16, 12)
        layout.setSpacing(16)
        outer.addLayout(layout, 1)

        # ── thumbnail ──
        thumb = QLabel()
        thumb.setObjectName("HistThumb")
        thumb.setFixedSize(220, 144)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(image_path)
        if not pix.isNull():
            thumb.setPixmap(_rounded_thumb(pix, 220, 144, 10))
        else:
            thumb.setText("No preview")
        layout.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(9)
        info.setContentsMargins(0, 2, 0, 2)

        # ── timestamp ──
        ts_lbl = QLabel(record.get("timestamp_str", "Unknown time"))
        ts_lbl.setObjectName("HistTime")
        info.addWidget(ts_lbl)

        try:
            cam_id = int(record.get("cam_id", 0))
        except (TypeError, ValueError):
            cam_id = 0

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

        # ── camera / objects / confidence — one uniform colour ──
        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(_info_chip(f"Camera {cam_id + 1}"))
        meta.addWidget(_info_chip(f"{num_obj} object{'s' if num_obj != 1 else ''}"))
        meta.addWidget(_info_chip(f"Max conf {max_conf:.2f}"))
        meta.addStretch()
        info.addLayout(meta)

        # ── detected classes ──
        detected_lbl = QLabel("DETECTED")
        detected_lbl.setObjectName("HistKicker")
        info.addWidget(detected_lbl)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        if class_items:
            for i, (name, count) in enumerate(class_items):
                color = CLASS_COLORS[i % len(CLASS_COLORS)]
                chips.addWidget(_class_pill(name, count, color))
        else:
            fallback = QLabel(f"Detected: {classes_str}")
            fallback.setObjectName("HistBody")
            fallback.setWordWrap(True)
            chips.addWidget(fallback)
        chips.addStretch()
        info.addLayout(chips)

        # ── location ──
        location_str = record.get("location_str", "Unknown")
        location = record.get("location")

        has_coords = (
            isinstance(location, dict)
            and location.get("lat") is not None
            and location.get("lon") is not None
            and location_str not in (None, "", "Unknown")
        )

        loc_row = QHBoxLayout()
        loc_row.setSpacing(6)

        pin_color = HIST_ACCENT if has_coords else PALETTE["dim"]
        loc_row.addWidget(_svg_label("map-pin", 14, pin_color), 0, Qt.AlignmentFlag.AlignVCenter)

        if has_coords:
            loc_lbl = QLabel(f"{location_str}")
            loc_lbl.setObjectName("HistLocOn")
            loc_row.addWidget(loc_lbl, 1)

            btn = QPushButton("View on Map")
            btn.setObjectName("MapBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setIcon(_svg_icon("map", 14, HIST_ACCENT))
            btn.setIconSize(QSize(14, 14))
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
            loc_lbl = QLabel(f"{location_str if location_str else 'Unknown'}")
            loc_lbl.setObjectName("HistLocOff")
            loc_row.addWidget(loc_lbl, 1)

        info.addLayout(loc_row)
        info.addStretch()
        layout.addLayout(info, 1)

        # ── shadow that "lifts" on hover ──
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(self._SHADOW_REST)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(self._shadow)

        self._hover_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── hover feedback ──
    def _animate_shadow(self, target):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._shadow.blurRadius())
        self._hover_anim.setEndValue(float(target))
        self._hover_anim.start()

    def enterEvent(self, event):
        self._shadow.setColor(QColor(94, 184, 255, 70) if HIST_ACCENT == PALETTE["accent_2"]
                              else QColor(62, 224, 162, 70))
        self._animate_shadow(self._SHADOW_HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow.setColor(QColor(0, 0, 0, 80))
        self._animate_shadow(self._SHADOW_REST)
        super().leaveEvent(event)

    # ── styling (scoped to this card, overrides older global rules) ──
    @staticmethod
    def _qss():
        a = HIST_ACCENT
        return f"""
            QFrame#HistoryCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {PALETTE["card_alt"]}, stop:1 {PALETTE["card"]});
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 14px;
            }}
            QFrame#HistoryCard:hover {{
                border: 1px solid {_hist_rgba(a, 0.55)};
            }}
            QFrame#HistAccent {{
                background: {a};
                border: none;
                border-top-left-radius: 14px;
                border-bottom-left-radius: 14px;
            }}
            QLabel#HistThumb {{
                background: {PALETTE["bg"]};
                color: {PALETTE["dim"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 10px;
                font-size: 12px;
            }}
            QLabel#HistTime {{
                color: {PALETTE["text"]};
                font-size: 15px;
                font-weight: 700;
                letter-spacing: 0.2px;
                background: transparent;
                border: none;
            }}
            QLabel#HistChip {{
                color: {a};
                background: {_hist_rgba(a, 0.12)};
                border: 1px solid {_hist_rgba(a, 0.38)};
                border-radius: 11px;
                padding: 3px 11px;
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#HistKicker {{
                color: {PALETTE["dim"]};
                background: transparent;
                border: none;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.6px;
            }}
            QFrame#HistClassPill {{
                background: {PALETTE["surface"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 11px;
            }}
            QLabel#HistClassName {{
                color: {PALETTE["text"]};
                background: transparent;
                border: none;
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#HistClassCount {{
                color: {PALETTE["muted"]};
                background: transparent;
                border: none;
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#HistBody {{
                color: {PALETTE["muted"]};
                background: transparent;
                border: none;
                font-size: 12px;
            }}
            QLabel#HistLocOn {{
                color: {PALETTE["text"]};
                background: transparent;
                border: none;
                font-size: 12px;
            }}
            QLabel#HistLocOff {{
                color: {PALETTE["dim"]};
                background: transparent;
                border: none;
                font-size: 12px;
            }}
            QPushButton#MapBtn {{
                color: {a};
                background: transparent;
                border: 1px solid {_hist_rgba(a, 0.45)};
                border-radius: 8px;
                padding: 0px 12px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton#MapBtn:hover {{
                background: {_hist_rgba(a, 0.16)};
                border: 1px solid {a};
            }}
            QPushButton#MapBtn:pressed {{
                background: {_hist_rgba(a, 0.28)};
            }}
            QPushButton#MapBtn:disabled {{
                color: {PALETTE["dim"]};
                border: 1px solid {PALETTE["stroke"]};
            }}
        """


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
        titles.setSpacing(2)
        titles.setContentsMargins(0, 0, 0, 0)

        eyebrow = QLabel("E-SAFAI")
        eyebrow.setObjectName("Eyebrow")
        eyebrow.setStyleSheet(
            """
            QLabel#Eyebrow {
                font-family: 'Segoe UI', 'Poppins', 'Arial', sans-serif;
                font-size: 22px;
                font-weight: 800;
                letter-spacing: 3px;
                color: #3ee0a2;
                padding: 0px;
                margin: 0px;
                background: transparent;
            }
            """
        )
        titles.addWidget(eyebrow)

        title = QLabel("Reporting & Statistics")
        title.setObjectName("PageTitle")
        title.setStyleSheet(
            """
            QLabel#PageTitle {
                font-family: 'Segoe UI', 'Arial', sans-serif;
                font-size: 13px;
                font-weight: 500;
                letter-spacing: 1.2px;
                color: #FFFFFF;
                padding: 0px;
                margin: 0px;
                background: transparent;
            }
            """
        )
        titles.addWidget(title)
        self.meta_label = QLabel("Stored detections from connected cameras")
        self.meta_label.setObjectName("PageMeta")
        titles.addWidget(self.meta_label)
        header.addLayout(titles, 1)
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
            icon = _svg_label("archive", 28, PALETTE["dim"], 1.5)
            icon.setFixedSize(28, 28)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg = QLabel("No detection records yet")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setObjectName("EmptyTitle")
            hint = QLabel("New evidence cards will appear here after garbage is detected.")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setObjectName("PageMeta")
            el.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
            el.addWidget(msg)
            el.addWidget(hint)
            self.vbox.insertWidget(0, empty)
            return

        n = len(records)
        noun = "detection" if n == 1 else "detections"
        self.meta_label.setText(f"{n} stored {noun}")

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
            QWidget#HistoryList {{ background: {PALETTE["bg"]}; }}
            QLabel#Eyebrow {{
                color: {PALETTE["accent"]}; font-size: 11px;
                font-weight: 700; letter-spacing: 2.4px;
            }}
            QLabel#PageTitle {{
                color: {PALETTE["text"]}; font-size: 26px;
                font-weight: 800; letter-spacing: -0.4px;
            }}
            QLabel#PageMeta {{ color: {PALETTE["muted"]}; font-size: 12px; }}
            QLabel#HistTime {{
                color: {PALETTE["accent_2"]}; font-size: 16px;
                font-weight: 800; letter-spacing: -0.2px;
            }}
            # QLabel#EmptyTitle {{
            #     color: {PALETTE["text"]}; font-size: 15px; font-weight: 700;
            # }}
            QScrollArea {{ border: none; background: {PALETTE["bg"]}; }}
            QScrollBar:vertical {{
                background: transparent; width: 10px; margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {PALETTE["stroke"]};
                border-radius: 5px; min-height: 32px;
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

        self.location_labels = {}
        self.location_icons = {}
        self.map_buttons = {}
        self.camera_locations = {}
        self.camera_garbage = {i: False for i in range(4)}
        self.alert_active = False
        self.blink_state = False

        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(500)
        self.blink_timer.timeout.connect(self._blink_tick)

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
        side_layout.setContentsMargins(14, 22, 14, 20)
        side_layout.setSpacing(4)

        logo_frame = QFrame()
        logo_frame.setStyleSheet(
            f"background: transparent; border: none;"
            f"border-bottom: 1px solid {PALETTE['stroke']};"
            f"padding-bottom: 14px; margin-bottom: 8px;"
        )
        logo_inner = QVBoxLayout(logo_frame)
        logo_inner.setContentsMargins(0, 0, 0, 12)
        logo_inner.setSpacing(6)

        logo_icon = _svg_label("recycle", 55, PALETTE["accent"], 2.0)
        logo_icon.setFixedSize(50, 92)
        logo_inner.addWidget(logo_icon, alignment=Qt.AlignmentFlag.AlignCenter)

        logo = QLabel("E-Safai")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            f"color: {PALETTE['text']}; font-size: 21px; font-weight: 800;"
            f"letter-spacing: -0.3px; background: transparent; border: none;"
        )
        logo_inner.addWidget(logo)

        logo_sub = QLabel("WASTE MANAGEMENT")
        logo_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_sub.setStyleSheet(
            f"color: {PALETTE['dim']}; font-size: 9px; font-weight: 700;"
            f"letter-spacing: 2.2px;"
            f"background: transparent; border: none;"
        )
        logo_inner.addWidget(logo_sub)
        side_layout.addWidget(logo_frame)

        side_layout.addSpacing(10)

        nav_label = QLabel("MENU")
        nav_label.setStyleSheet(
            f"color: {PALETTE['dim']}; font-size: 9px; font-weight: 700;"
            f"letter-spacing: 2px; padding: 0px 8px 6px 8px;"
            f"background: transparent; border: none;"
        )
        side_layout.addWidget(nav_label)

        self.btn_live = QPushButton("  Live Cameras")
        self.btn_history = QPushButton("  History")
        self.btn_stats = QPushButton("  Statistics")

        self.btn_live.setIcon(_svg_icon("camera", 16, PALETTE["muted"]))
        self.btn_history.setIcon(_svg_icon("archive", 16, PALETTE["muted"]))
        self.btn_stats.setIcon(_svg_icon("bar-chart", 16, PALETTE["muted"]))
        for b in (self.btn_live, self.btn_history, self.btn_stats):
            b.setIconSize(QSize(16, 16))

        _nav_btn_qss = f"""
            QPushButton {{
                text-align: left;
                padding: 11px 14px;
                color: {PALETTE['muted']};
                background: transparent;
                border: none;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.2px;
            }}
            QPushButton:hover {{
                background: {_rgba(PALETTE['accent_2'], 0.08)};
                color: {PALETTE['text']};
            }}
            QPushButton:checked {{
                background: {_rgba(PALETTE['accent_2'], 0.14)};
                color: {PALETTE['accent_2']};
                border-left: 3px solid {PALETTE['accent_2']};
                padding-left: 11px;
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

        footer_frame = QFrame()
        footer_frame.setStyleSheet(
            f"background: transparent; border: none;"
            f"border-top: 1px solid {PALETTE['stroke']};"
            f"padding-top: 14px;"
        )
        footer_inner = QVBoxLayout(footer_frame)
        footer_inner.setContentsMargins(0, 12, 0, 0)
        footer_inner.setSpacing(8)

        LOGO_SIZE = 110

        brand_logo = QLabel()
        brand_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_logo.setFixedSize(LOGO_SIZE, LOGO_SIZE)
        brand_logo.setStyleSheet("background: transparent; border: none;")

        brand_logo_pixmap = QPixmap("assets/sharpen_Ai.JPEG")
        if not brand_logo_pixmap.isNull():
            brand_logo.setPixmap(
                brand_logo_pixmap.scaled(
                    LOGO_SIZE, LOGO_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            brand_logo.setPixmap(_svg_pixmap("zap", LOGO_SIZE // 2, PALETTE["accent"]))
        footer_inner.addWidget(brand_logo, alignment=Qt.AlignmentFlag.AlignCenter)

        ver_label = QLabel("POWERED BY\nSHARPEN AI")
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_label.setStyleSheet(
            f"color: {PALETTE['dim']};"
            f"font-size: 9px;"
            f"font-weight: 700;"
            f"letter-spacing: 1.6px;"
            f"background: transparent; border: none;"
        )
        footer_inner.addWidget(ver_label)

        side_layout.addWidget(footer_frame)
        root.addWidget(sidebar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.live_page = self._build_live_page()
        self.stack.addWidget(self.live_page)

        self.history_page = HistoryPage(self.evidence_manager)
        self.stack.addWidget(self.history_page)

        self.stats_page = StatsPage(self.evidence_manager)
        self.stack.addWidget(self.stats_page)

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

        header = QVBoxLayout()
        header.setSpacing(2)
        header.setContentsMargins(0, 0, 0, 0)

        eyebrow = QLabel("E-SAFAI")
        eyebrow.setObjectName("Eyebrow")
        eyebrow.setStyleSheet(
            f"font-family: 'Segoe UI', 'Poppins', 'Arial', sans-serif;"
            f"color: {PALETTE['accent']};"
            f"font-size: 22px;"
            f"font-weight: 800;"
            f"letter-spacing: 3px;"
            f"padding: 0px; margin: 0px; background: transparent;"
        )
        header.addWidget(eyebrow)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("Live Garbage Detection")
        title.setObjectName("PageTitle")
        title.setStyleSheet(
            f"font-family: 'Segoe UI', 'Arial', sans-serif;"
            f"color: {PALETTE['text']};"
            f"font-size: 13px;"
            f"font-weight: 500;"
            f"letter-spacing: 1.2px;"
            f"padding: 0px; margin: 0px; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch()

        header.addLayout(title_row)
        subtitle = QLabel("Real-time monitoring across all connected camera feeds")
        subtitle.setStyleSheet(
            f"color: {PALETTE['muted']}; font-size: 12px;"
        )
        header.addWidget(subtitle)
        root.addLayout(header, 0)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {PALETTE['stroke']}; border: none;")
        root.addWidget(sep)

        grid = QGridLayout()
        grid.setSpacing(12)
        root.addLayout(grid, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        cam_accent_colors = ["#f6c177"] * 4

        for i in range(4):
            accent = cam_accent_colors[i]

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

            # ── top bar: CAM badge + location pin + location text + map button
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

            # Location pin icon (SVG, theme-colored)
            loc_icon = _svg_label("map-pin", 14, PALETTE["dim"])
            top_bar.addWidget(loc_icon, 0, Qt.AlignmentFlag.AlignVCenter)

            # Location text
            loc_label = QLabel("Location: Unknown")
            loc_label.setStyleSheet(
                f"color: {PALETTE['dim']}; font-size: 11px; font-weight: 500;"
            )
            top_bar.addWidget(loc_label, 1)

            # Map button — SVG icon, hidden until GPS arrives
            map_btn = QPushButton(" Map")
            map_btn.setFixedHeight(24)
            map_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            map_btn.setIcon(_svg_icon("map", 12, PALETTE["text"]))
            map_btn.setIconSize(QSize(12, 12))
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

            # ── camera stream
            screen = CameraScreen()
            screen.mousePressEvent = lambda e, cid=i: self.on_screen_clicked(cid)
            card_layout.addWidget(screen, 1)

            # ── bottom bar: status dot + status text + connect hint
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


            card_layout.addLayout(bottom_bar)

            grid.addWidget(card, i // 2, i % 2)

            self.screens[i] = screen
            self.status_labels[i] = status
            self.location_labels[i] = loc_label
            self.location_icons[i] = loc_icon
            self.map_buttons[i] = map_btn

            if not hasattr(self, '_status_dots'):
                self._status_dots = {}
                self._connect_hints = {}
            self._status_dots[i] = status_dot

        # ── Alert banner (hidden by default, top-right overlay)
        self.alert_banner = QFrame(page)
        self.alert_banner.setObjectName("AlertBanner")
        self.alert_banner.setStyleSheet(f"""
            QFrame#AlertBanner {{
                background: #c62828;
                border: 1px solid #ff5252;
                border-radius: 10px;
            }}
        """)
        banner_layout = QHBoxLayout(self.alert_banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        banner_layout.setSpacing(0)

        self.alert_label = QLabel("Garbage detected in multiple cameras")
        self.alert_label.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: 700; "
            "letter-spacing: 0.3px; background: transparent; border: none;"
        )
        banner_layout.addWidget(self.alert_label)
        self.alert_banner.setVisible(False)

        shadow = QGraphicsDropShadowEffect(self.alert_banner)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(198, 40, 40, 160))
        self.alert_banner.setGraphicsEffect(shadow)

        return page

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "alert_banner") and self.alert_banner.isVisible():
            self._position_banner()

    def _position_banner(self):
        if not hasattr(self, "alert_banner") or not hasattr(self, "live_page"):
            return
        self.alert_banner.adjustSize()
        w = self.alert_banner.width()
        margin = 16
        target_x = max(margin, self.live_page.width() - w - margin)
        self.alert_banner.move(target_x, margin)
        self.alert_banner.raise_()

    def switch_page(self, idx):
        self.stack.setCurrentIndex(idx)
        self.btn_live.setChecked(idx == 0)
        self.btn_history.setChecked(idx == 1)
        self.btn_stats.setChecked(idx == 2)
        # Update icon color to reflect active state
        active = PALETTE["accent_2"]
        inactive = PALETTE["muted"]
        self.btn_live.setIcon(_svg_icon("camera", 16, active if idx == 0 else inactive))
        self.btn_history.setIcon(_svg_icon("archive", 16, active if idx == 1 else inactive))
        self.btn_stats.setIcon(_svg_icon("bar-chart", 16, active if idx == 2 else inactive))
        if idx == 0:
            self._position_banner()
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

        cfg = self.config.get(str(cam_id), {})
        current_ip = cfg.get("ip", "")
        current_port = cfg.get("port", "")

        dialog = CameraDialog(cam_id, current_ip=current_ip, current_port=current_port, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        ip, port = dialog.get_values()
        if not ip or not port:
            return

        self.start_camera(cam_id, ip, port)

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
        self.location_labels[cam_id].setText("Locating...")
        self.location_labels[cam_id].setStyleSheet(
            f"color: {PALETTE['accent_2']}; font-size: 11px; font-weight: 500;"
        )
        if cam_id in self.location_icons:
            self.location_icons[cam_id].setPixmap(
                _svg_pixmap("map-pin", 14, PALETTE["accent_2"])
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
            self.location_labels[cam_id].setText(f"{lat:.5f}, {lon:.5f}")
            self.location_labels[cam_id].setStyleSheet(
                f"color: {PALETTE['accent']}; font-size: 11px; font-weight: 500;"
            )
        if cam_id in self.location_icons:
            self.location_icons[cam_id].setPixmap(
                _svg_pixmap("map-pin", 14, PALETTE["accent"])
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
            self.location_labels[cam_id].setText("Location: Unknown")
            self.location_labels[cam_id].setStyleSheet(
                f"color: {PALETTE['dim']}; font-size: 11px; font-weight: 500;"
            )
        if cam_id in self.location_icons:
            self.location_icons[cam_id].setPixmap(
                _svg_pixmap("map-pin", 14, PALETTE["dim"])
            )
        if cam_id in self.map_buttons:
            self.map_buttons[cam_id].setVisible(False)
        self.camera_locations.pop(cam_id, None)

        if self.camera_garbage.get(cam_id):
            self.camera_garbage[cam_id] = False
            self._evaluate_alert()

        if hasattr(self, '_status_dots') and cam_id in self._status_dots:
            self._status_dots[cam_id].setStyleSheet(
                f"color: #ff8b7b; font-size: 8px;"
            )
        if hasattr(self, '_connect_hints') and cam_id in self._connect_hints:
            self._connect_hints[cam_id].setText("Click to reconnect ›")
            self._connect_hints[cam_id].setStyleSheet(
                f"color: {PALETTE['dim']}; font-size: 10px; font-style: italic;"
            )

    def _evaluate_alert(self):
        garbage_cams = [c for c, g in self.camera_garbage.items() if g]
        count = len(garbage_cams)

        if count >= 2:
            if not self.alert_active:
                self.alert_active = True
                self.alert_label.setText(
                    f"Garbage Alert  ·  {count} cameras active"
                )
                self.alert_banner.setVisible(True)
                self._position_banner()
                self.blink_timer.start()
            else:
                self.alert_label.setText(
                    f"Garbage Alert  ·  {count} cameras active"
                )
                self._position_banner()
        else:
            if self.alert_active:
                self.alert_active = False
                self.alert_banner.setVisible(False)
                self.blink_timer.stop()
                self.blink_state = False
                for cid in self.screens:
                    if cid in self.workers:
                        self.screens[cid].setStyleSheet(
                            f"background: #0a0f17; border: 1px solid {PALETTE['stroke']};"
                            f"border-radius: 14px;"
                        )

    def _blink_tick(self):
        self.blink_state = not self.blink_state
        for cid, is_garbage in self.camera_garbage.items():
            if not is_garbage or cid not in self.screens:
                continue
            if self.blink_state:
                self.screens[cid].setStyleSheet(
                    "background: #0a0f17; border: 3px solid #ff1744;"
                    "border-radius: 14px;"
                )
            else:
                self.screens[cid].setStyleSheet(
                    "background: #0a0f17; border: 3px solid #7f0e1a;"
                    "border-radius: 14px;"
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

        is_garbage = status.lower().startswith("garbage detected")
        if self.camera_garbage.get(cam_id) != is_garbage:
            self.camera_garbage[cam_id] = is_garbage
            self._evaluate_alert()

        if frame is None:
            return
        h, w, ch = frame.shape
        qimg = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.last_frames[cam_id] = pix
        self.screens[cam_id].set_frame(pix)
        if not (self.alert_active and self.camera_garbage.get(cam_id)):
            self.screens[cam_id].setStyleSheet(
                f"background: #0a0f17; border: 1px solid #f6c177;"
                f"border-radius: 14px;"
            )

    def closeEvent(self, event):
        for w in self.workers.values():
            w.stop()
        event.accept()