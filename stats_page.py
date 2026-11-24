import math
import warnings
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QSizePolicy, QGridLayout, QGraphicsDropShadowEffect,
    QScrollArea, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle, Wedge
from matplotlib.ticker import MaxNLocator
import numpy as np

matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = [
    "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans",
]


# Visual system only — data still comes from evidence_manager.compute_stats
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

# Length of the Refresh animation (seconds) and its frame interval (ms).
ANIM_SECONDS = 5.0
ANIM_INTERVAL_MS = 33


# ───────────────────────── helpers ─────────────────────────
def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgba(c, a):
    r, g, b = (int(round(x * 255)) for x in _hex(c))
    return f"rgba({r}, {g}, {b}, {a})"


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _ease_out(x):
    x = _clamp(x)
    return 1.0 - (1.0 - x) ** 3


def _ease_in_out(x):
    x = _clamp(x)
    return x * x * (3.0 - 2.0 * x)


def _envelope(s):
    """1.0 while the animation is 'live', fades to 0 in the last 0.9 s so the
    charts glide back to their exact resting state."""
    settle = 0.9
    if s <= ANIM_SECONDS - settle:
        return 1.0
    return _clamp((ANIM_SECONDS - s) / settle)


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _fmt_day(value):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d %b")
    except Exception:
        return str(value)


def _smooth_curve(y, per=24):
    """Monotone cubic (PCHIP-style) interpolation through the daily counts.
    Never overshoots, so the curve can't dip below zero or above the real peak."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 2:
        return np.array([0.0]), y.copy()
    xs = np.linspace(0, n - 1, (n - 1) * per + 1)
    if n == 2:
        return xs, np.interp(xs, [0, 1], y)
    d = np.diff(y)
    m = np.zeros(n)
    same = d[:-1] * d[1:] > 0
    m[1:-1] = np.where(same, 2 * d[:-1] * d[1:] / (d[:-1] + d[1:] + 1e-12), 0.0)
    m[0], m[-1] = d[0], d[-1]
    i = np.minimum(xs.astype(int), n - 2)
    t = xs - i
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    ys = h00 * y[i] + h10 * m[i] + h01 * y[i + 1] + h11 * m[i + 1]
    return xs, np.maximum(ys, 0.0)


# ───────────────────────── widgets ─────────────────────────
class RefreshButton(QPushButton):
    """Refresh button with a built-in icon, spinner and progress strip."""

    def __init__(self, text="Refresh"):
        super().__init__(text)
        self._busy = False
        self._angle = 0
        self._progress = 0.0
        self.setProperty("busy", False)
        self._spin = QTimer(self)
        self._spin.setInterval(16)
        self._spin.timeout.connect(self._tick)

    def set_busy(self, busy):
        self._busy = busy
        self.setProperty("busy", busy)
        self.setText("Refreshing…" if busy else "Refresh")
        self.setCursor(
            Qt.CursorShape.BusyCursor if busy else Qt.CursorShape.PointingHandCursor
        )
        if busy:
            self._spin.start()
        else:
            self._spin.stop()
            self._angle = 0
            self._progress = 0.0
        _repolish(self)

    def set_progress(self, p):
        self._progress = _clamp(p)

    def _tick(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#062016")
        cx, cy, r = 20.0, self.height() / 2.0, 7.0
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)

        if self._busy:
            track = QColor(color)
            track.setAlpha(55)
            p.setPen(QPen(track, 2.2))
            p.drawEllipse(rect)
            pen = QPen(color, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, int(-self._angle * 16), int(-110 * 16))
            # progress strip along the bottom edge
            strip = QColor(color)
            strip.setAlpha(150)
            w = (self.width() - 24) * self._progress
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(strip)
            p.drawRoundedRect(QRectF(12, self.height() - 5, w, 2.4), 1.2, 1.2)
        else:
            pen = QPen(color, 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, 30 * 16, 300 * 16)
            # arrow head at the end of the arc
            th = math.radians(330)
            ex, ey = cx + r * math.cos(th), cy - r * math.sin(th)
            dx, dy = -math.sin(th), -math.cos(th)
            for sign in (1, -1):
                a = math.atan2(-dy, -dx) + sign * math.radians(40)
                p.drawLine(
                    QRectF(0, 0, 0, 0).topLeft() + __import__("PyQt6.QtCore", fromlist=["QPointF"]).QPointF(ex, ey),
                    __import__("PyQt6.QtCore", fromlist=["QPointF"]).QPointF(
                        ex + 5 * math.cos(a), ey + 5 * math.sin(a)
                    ),
                )
        p.end()


class KpiCard(QFrame):
    def __init__(self, title, value, color="#5eb8ff", icon="●", hint=""):
        super().__init__()
        self.setObjectName("KpiCard")
        self.setProperty("accent", color)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._accent = QFrame()
        self._accent.setObjectName("KpiAccent")
        self._accent.setFixedWidth(4)
        self._accent.setStyleSheet(
            f"background: {color}; border: none; border-radius: 4px;"
        )

        icon_box = QLabel(icon)
        icon_box.setObjectName("KpiIcon")
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setFixedSize(36, 36)
        icon_box.setStyleSheet(
            f"background: {_rgba(color, 0.14)}; color: {color}; border-radius: 10px; "
            f"font-size: 15px; font-weight: 700; border: 1px solid {_rgba(color, 0.35)};"
        )

        t = QLabel(title.upper())
        t.setObjectName("KpiTitle")
        t.setStyleSheet(
            "color: #8b9bb0; font-size: 11px; font-weight: 600; letter-spacing: 1.2px;"
        )

        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("KpiValue")
        self.value_label.setStyleSheet(
            f"color: {color}; font-size: 28px; font-weight: 800; letter-spacing: -0.4px;"
        )
        self.value_label.setWordWrap(True)

        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("KpiHint")
        self.hint_label.setStyleSheet("color: #5d6d82; font-size: 11px;")

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.addWidget(t)
        text_col.addWidget(self.value_label)
        text_col.addWidget(self.hint_label)
        text_col.addStretch()

        body = QHBoxLayout()
        body.setContentsMargins(14, 14, 16, 14)
        body.setSpacing(12)
        body.addWidget(icon_box, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(text_col, 1)

        wrap = QHBoxLayout(self)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(0)
        wrap.addWidget(self._accent)
        wrap.addLayout(body, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)

    def set_value(self, value):
        self.value_label.setText(str(value))


class ChartCard(QFrame):
    def __init__(self, title, subtitle="", wide=False):
        super().__init__()
        self.setObjectName("ChartCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._badge_text = ""
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 12)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("ChartTitle")
        t.setStyleSheet("color: #e8eef7; font-size: 14px; font-weight: 700;")
        titles.addWidget(t)
        s = QLabel(subtitle)
        s.setObjectName("ChartSub")
        s.setStyleSheet("color: #8b9bb0; font-size: 11px;")
        titles.addWidget(s)
        head.addLayout(titles, 1)

        self.badge = QLabel("")
        self.badge.setObjectName("ChartBadge")
        self.badge.setProperty("syncing", False)
        self.badge.hide()
        head.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        self.figure = Figure(figsize=(5, 3), facecolor=PALETTE["card"])
        self.figure.patch.set_facecolor(PALETTE["card"])
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        # The wide trend chart needs less height than the square-ish ones.
        self.canvas.setMinimumHeight(170 if wide else 200)
        self.canvas.setStyleSheet("background: transparent;")
        # let the mouse wheel scroll the page instead of being swallowed
        self.canvas.wheelEvent = lambda e: e.ignore()
        layout.addWidget(self.canvas, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

    def set_badge(self, text):
        self._badge_text = text
        self._refresh_badge()

    def set_syncing(self, on):
        self._syncing = on
        self._refresh_badge()

    def _refresh_badge(self):
        text = "●  Syncing" if self._syncing else self._badge_text
        self.badge.setText(text)
        self.badge.setProperty("syncing", self._syncing)
        self.badge.setVisible(bool(text))
        _repolish(self.badge)


# ───────────────────────── page ─────────────────────────
class StatsPage(QWidget):
    def __init__(self, evidence_manager):
        super().__init__()
        self.evidence_manager = evidence_manager
        self.setObjectName("StatsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self._qss())

        # animation state
        self._anim = {}              # chart name -> update(s) callable
        self._anim_running = False
        self._kpi_raw = {}
        self._clock = QElapsedTimer()
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(ANIM_INTERVAL_MS)
        self._anim_timer.timeout.connect(self._tick_animation)

        # thin top progress bar (visible only while refreshing)
        self.sync_bar = QProgressBar()
        self.sync_bar.setObjectName("SyncBar")
        self.sync_bar.setRange(0, 1000)
        self.sync_bar.setValue(0)
        self.sync_bar.setTextVisible(False)
        self.sync_bar.setFixedHeight(3)

        # scroll area so nothing is ever clipped on small screens
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.sync_bar)

        scroll = QScrollArea()
        scroll.setObjectName("StatsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("StatsContent")
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        root = QVBoxLayout(content)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(16)

        root.addLayout(self._build_header())
        root.addLayout(self._build_kpis())

        charts = QGridLayout()
        charts.setSpacing(14)
        self.cam_card = ChartCard(
            "Detections per Camera",
            "Load across the four connected feeds",
        )
        self.class_card = ChartCard(
            "Class Distribution",
            "Waste mix from stored detections",
        )
        self.day_card = ChartCard(
            "Detections per Day",
            "How cleanup volume moved over time",
            wide=True,
        )
        charts.addWidget(self.cam_card, 0, 0)
        charts.addWidget(self.class_card, 0, 1)
        charts.addWidget(self.day_card, 1, 0, 1, 2)
        charts.setRowStretch(0, 5)
        charts.setRowStretch(1, 4)
        charts.setColumnStretch(0, 1)
        charts.setColumnStretch(1, 1)
        root.addLayout(charts, 1)

        # keep axes/labels inside the card whenever the window is resized
        for card in (self.cam_card, self.day_card):
            card.canvas.mpl_connect(
                "resize_event", lambda ev, f=card.figure: self._tidy(f)
            )

        self.refresh()

    # ── header / filters ──
    def _build_header(self):
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

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self.meta_label = QLabel("Historical detections across cameras")
        self.meta_label.setObjectName("PageMeta")
        meta_row.addWidget(self.meta_label)
        self.stamp_label = QLabel("")
        self.stamp_label.setObjectName("PageStamp")
        meta_row.addWidget(self.stamp_label)
        meta_row.addStretch()
        titles.addLayout(meta_row)
        header.addLayout(titles, 1)

        filters = QFrame()
        filters.setObjectName("FilterBar")
        fl = QHBoxLayout(filters)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(10)

        range_box = QVBoxLayout()
        range_box.setSpacing(3)
        rl = QLabel("RANGE")
        rl.setObjectName("FilterLabel")
        range_box.addWidget(rl)
        self.range_combo = QComboBox()
        self.range_combo.addItem("All time", None)
        self.range_combo.addItem("Today", 1)
        self.range_combo.addItem("Last 7 days", 7)
        self.range_combo.addItem("Last 30 days", 30)
        self.range_combo.currentIndexChanged.connect(self.refresh)
        self.range_combo.setMinimumWidth(132)
        self.range_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        range_box.addWidget(self.range_combo)
        fl.addLayout(range_box)

        cam_box = QVBoxLayout()
        cam_box.setSpacing(3)
        cl = QLabel("CAMERA")
        cl.setObjectName("FilterLabel")
        cam_box.addWidget(cl)
        self.cam_combo = QComboBox()
        self.cam_combo.addItem("All", None)
        for i in range(4):
            self.cam_combo.addItem(f"Camera {i + 1}", i)
        self.cam_combo.currentIndexChanged.connect(self.refresh)
        self.cam_combo.setMinimumWidth(120)
        self.cam_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        cam_box.addWidget(self.cam_combo)
        fl.addLayout(cam_box)

        refresh_col = QVBoxLayout()
        refresh_col.addStretch()
        self.refresh_btn = RefreshButton("Refresh")
        self.refresh_btn.setObjectName("RefreshBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        self.refresh_btn.setMinimumHeight(34)
        self.refresh_btn.setMinimumWidth(138)
        refresh_col.addWidget(self.refresh_btn)
        fl.addLayout(refresh_col)

        header.addWidget(filters, 0, Qt.AlignmentFlag.AlignBottom)
        return header

    def _build_kpis(self):
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.kpi_total = KpiCard(
            "Total Detections", "0", color="#FFFFFF", icon="🗑️",
            hint="In selected range",
        )
        self.kpi_today = KpiCard(
            "Today", "0", color="#FFFFFF", icon="📅",
            hint="Since midnight",
        )
        self.kpi_top = KpiCard(
            "Most Common", "—", color="#FFFFFF", icon="🏆",
            hint="Leading waste class",
        )
        self.kpi_busy = KpiCard(
            "Busiest Camera", "—", color="#FFFFFF", icon="🎥",
            hint="Highest detection volume",
        )
        for k in (self.kpi_total, self.kpi_today, self.kpi_top, self.kpi_busy):
            kpi_row.addWidget(k)
        return kpi_row

    # ── data (logic unchanged) ──
    def refresh(self):
        self._cancel_animation()

        days = self.range_combo.currentData()
        cam_id = self.cam_combo.currentData()
        stats = self.evidence_manager.compute_stats(days=days, cam_id=cam_id)

        self.kpi_total.set_value(stats["total"])
        self.kpi_today.set_value(stats["today"])
        self.kpi_top.set_value(stats["top_class"])
        self.kpi_busy.set_value(
            f"Cam {int(stats['busiest_cam']) + 1}"
            if isinstance(stats["busiest_cam"], int) else "—"
        )
        self._kpi_raw = {"total": stats["total"], "today": stats["today"]}

        range_txt = self.range_combo.currentText()
        cam_txt = self.cam_combo.currentText()
        n = stats["num_records"]
        noun = "detection" if n == 1 else "detections"
        self.meta_label.setText(
            f"{n} {noun}  ·  {range_txt}  ·  {cam_txt} cameras"
            if cam_txt == "All"
            else f"{n} {noun}  ·  {range_txt}  ·  {cam_txt}"
        )
        # self.stamp_label.setText(f"·  Updated {datetime.now():%H:%M:%S}")

        self._draw_camera_chart(stats)
        self._draw_class_chart(stats)
        self._draw_day_chart(stats)

    # ── refresh animation ──
    def _on_refresh_clicked(self):
        if self._anim_running:
            return
        self.refresh()          # pull fresh data + draw the resting state
        self._begin_animation()

    def _begin_animation(self):
        self._anim_running = True
        self.refresh_btn.set_busy(True)
        for card in (self.cam_card, self.class_card, self.day_card):
            card.set_syncing(True)
        self._clock.start()
        self._anim_timer.start()
        self._tick_animation()

    def _tick_animation(self):
        s = self._clock.elapsed() / 1000.0
        if s >= ANIM_SECONDS:
            self._end_animation()
            return
        self.refresh_btn.set_progress(s / ANIM_SECONDS)
        self.sync_bar.setValue(int(1000 * s / ANIM_SECONDS))
        self._apply_frame(s)

    def _end_animation(self):
        self._anim_timer.stop()
        self._anim_running = False
        self._apply_frame(None)            # exact resting state
        self._reset_sync_ui()

    def _cancel_animation(self):
        if self._anim_running:
            self._anim_timer.stop()
            self._anim_running = False
            self._reset_sync_ui()

    def _reset_sync_ui(self):
        self.refresh_btn.set_busy(False)
        self.sync_bar.setValue(0)
        for card in (self.cam_card, self.class_card, self.day_card):
            card.set_syncing(False)

    def _apply_frame(self, s):
        for name, card in (
            ("camera", self.cam_card),
            ("class", self.class_card),
            ("day", self.day_card),
        ):
            fn = self._anim.get(name)
            if fn:
                fn(s)
                card.canvas.draw_idle()
        # KPI numbers count up while the charts build in
        g = 1.0 if s is None else _ease_out(s / 1.3)
        for card, key in ((self.kpi_total, "total"), (self.kpi_today, "today")):
            v = self._kpi_raw.get(key)
            if s is not None and g < 1.0 and isinstance(v, (int, float)):
                card.set_value(int(round(v * g)))
            elif v is not None:
                card.set_value(v)

    # ── charts ──
    def _tidy(self, fig):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                fig.tight_layout(pad=0.9)
            except Exception:
                pass

    def _draw_camera_chart(self, stats):
        fig = self.cam_card.figure
        fig.clear()
        fig.patch.set_facecolor(PALETTE["card"])
        ax = fig.add_subplot(111)
        self._style_axes(ax)
        self._anim["camera"] = None

        if stats["num_records"] == 0:
            icon = self._empty(ax, "No camera activity\nfor this filter")
            self._anim["camera"] = self._empty_updater(icon)
            self.cam_card.set_badge("No data")
            self._tidy(fig)
            self.cam_card.canvas.draw()
            return

        by_cam = {}
        for key, val in stats["per_cam"].items():
            try:
                by_cam[int(key)] = val
            except (TypeError, ValueError):
                continue
        labels = [f"Cam {i + 1}" for i in range(4)]
        counts = [by_cam.get(i, 0) for i in range(4)]

        x = np.arange(4)
        ymax = max(counts) if max(counts) > 0 else 1
        top = ymax * 1.22 + 0.35
        ax.set_xlim(-0.6, 3.6)
        ax.set_ylim(0, top)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.tick_params(axis="x", labelsize=9)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
        ax.set_ylabel("Detections", color=PALETTE["muted"], fontsize=8)

        ax.bar(x, [top] * 4, width=0.56, color="#1b2636", edgecolor="none", zorder=2)
        glow = ax.bar(
            x, counts, width=0.84, color=CAM_COLORS, alpha=0.10,
            edgecolor="none", zorder=2.4,
        )
        bars = ax.bar(
            x, counts, width=0.56, color=CAM_COLORS, edgecolor="none", zorder=3,
        )
        cap_h = top * 0.02
        caps = ax.bar(
            x, [cap_h] * 4, bottom=counts, width=0.56, color="white",
            alpha=0.35, edgecolor="none", zorder=3.2,
        )
        texts = [
            ax.text(
                i, 0, str(c), ha="center", va="bottom", zorder=5,
                color=PALETTE["text"] if c > 0 else PALETTE["dim"],
                fontsize=9, fontweight="bold",
            )
            for i, c in enumerate(counts)
        ]
        band = Rectangle(
            (-0.9, 0), 0.9, top, facecolor="white", edgecolor="none",
            alpha=0.0, zorder=1.8,
        )
        ax.add_patch(band)

        def update(s):
            if s is None:
                env, t, g = 0.0, 0.0, [1.0] * 4
            else:
                env, t = _envelope(s), s
                g = [_ease_out((s - 0.12 * i) / 1.1) for i in range(4)]
            for i, c in enumerate(counts):
                wave = 1 + 0.15 * env * math.sin(2 * math.pi * 0.85 * t - i * 0.9)
                h = c * g[i] * wave
                bars[i].set_height(h)
                glow[i].set_height(h)
                caps[i].set_y(max(h - cap_h, 0))
                caps[i].set_visible(h > cap_h * 1.5)
                if c > 0:
                    texts[i].set_position((i, h + top * 0.025))
                    texts[i].set_text(str(int(round(c * g[i]))))
                else:
                    texts[i].set_position((i, top * 0.02))
                texts[i].set_alpha(_clamp(g[i] * 1.6))
            pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 1.2 * t)
            for gl in glow:
                gl.set_alpha(0.10 + 0.08 * env * pulse)
            band.set_visible(env > 0)
            band.set_x(-0.9 + 4.8 * ((t / 1.6) % 1.0))
            band.set_alpha(0.07 * env)

        update(None)
        self._anim["camera"] = update
        best = int(np.argmax(counts))
        self.cam_card.set_badge(f"Top  ·  Cam {best + 1}" if counts[best] > 0 else "")
        self._tidy(fig)
        self.cam_card.canvas.draw()

    def _draw_class_chart(self, stats):
        fig = self.class_card.figure
        fig.clear()
        fig.patch.set_facecolor(PALETTE["card"])
        self._anim["class"] = None

        if stats["num_records"] == 0 or not stats["class_dist"]:
            ax = fig.add_subplot(111)
            ax.set_facecolor(PALETTE["card"])
            for spine in ax.spines.values():
                spine.set_visible(False)
            icon = self._empty(ax, "No class mix yet\nfor this filter")
            self._anim["class"] = self._empty_updater(icon)
            self.class_card.set_badge("No data")
            self._tidy(fig)
            self.class_card.canvas.draw()
            return

        classes = sorted(stats["class_dist"].items(), key=lambda x: x[1], reverse=True)
        labels = [c[0] for c in classes]
        values = [c[1] for c in classes]
        colors = [CLASS_COLORS[i % len(CLASS_COLORS)] for i in range(len(labels))]
        total = sum(values) or 1
        fracs = [v / total * 360.0 for v in values]
        cums = [sum(fracs[:i]) for i in range(len(fracs))]

        ax = fig.add_axes([0.02, 0.04, 0.46, 0.92])
        ax.set_facecolor(PALETTE["card"])
        for spine in ax.spines.values():
            spine.set_visible(False)

        wedges, _ = ax.pie(
            values,
            startangle=90,
            colors=colors,
            wedgeprops=dict(width=0.42, edgecolor=PALETTE["card"], linewidth=2.2),
        )
        ax.set_aspect("equal")
        ax.set_xlim(-1.3, 1.3)
        ax.set_ylim(-1.3, 1.3)

        ax.add_patch(Wedge(
            (0, 0), 1.14, 0, 360, width=0.008,
            facecolor=PALETTE["stroke"], edgecolor="none", zorder=1,
        ))
        orbit = Wedge(
            (0, 0), 1.14, 0, 60, width=0.03,
            facecolor=PALETTE["accent"], edgecolor="none", alpha=0.0, zorder=6,
        )
        sweep = Wedge(
            (0, 0), 1.0, 0, 40, width=0.42,
            facecolor="white", edgecolor="none", alpha=0.0, zorder=5,
        )
        ax.add_patch(orbit)
        ax.add_patch(sweep)

        ctext = ax.text(
            0, 0.08, str(int(total)), ha="center", va="center",
            color=PALETTE["text"], fontsize=18, fontweight="bold", zorder=7,
        )
        ax.text(
            0, -0.2, "items", ha="center", va="center",
            color=PALETTE["muted"], fontsize=9, zorder=7,
        )

        # custom legend panel: swatch · name · count · share bar
        axl = fig.add_axes([0.52, 0.06, 0.46, 0.88])
        axl.set_xlim(0, 1)
        axl.set_ylim(0, 1)
        axl.axis("off")
        max_rows = 8
        shown = list(range(min(len(labels), max_rows)))
        extra = len(labels) - len(shown)
        rows = len(shown) + (1 if extra > 0 else 0)
        rh = min(0.2, 1.0 / max(rows, 1))
        y0 = 0.5 + rh * rows / 2.0
        bar_x, bar_w = 0.07, 0.91
        bar_h = min(0.02, rh * 0.14)
        fills = []
        for k, i in enumerate(shown):
            yc = y0 - (k + 0.5) * rh
            yt = yc + rh * 0.13
            yb = yc - rh * 0.22
            axl.plot(
                [0.02], [yt], marker="s", ms=7, color=colors[i], ls="",
                clip_on=False,
            )
            axl.text(
                bar_x, yt, str(labels[i]), ha="left", va="center",
                color=PALETTE["text"], fontsize=9, fontweight="bold",
            )
            axl.text(
                0.98, yt, f"{values[i]}  ·  {values[i] / total * 100:.0f}%",
                ha="right", va="center", color=PALETTE["muted"], fontsize=8.5,
            )
            axl.add_patch(Rectangle(
                (bar_x, yb - bar_h / 2), bar_w, bar_h,
                facecolor="#1f2a3b", edgecolor="none",
            ))
            fill = Rectangle(
                (bar_x, yb - bar_h / 2), bar_w * values[i] / total, bar_h,
                facecolor=colors[i], edgecolor="none",
            )
            axl.add_patch(fill)
            fills.append((fill, values[i] / total))
        if extra > 0:
            axl.text(
                bar_x, y0 - (len(shown) + 0.5) * rh, f"+{extra} more classes",
                ha="left", va="center", color=PALETTE["dim"], fontsize=8.5,
            )

        def update(s):
            if s is None:
                g, env, rot, wid = 1.0, 0.0, 0.0, 0.42
                t = 0.0
            else:
                t = s
                g = _ease_out(s / 1.4)
                env = _envelope(s)
                rot = 360.0 * _ease_in_out((s - 1.0) / 3.0)
                wid = 0.42 + 0.05 * env * math.sin(2 * math.pi * 0.8 * s)
            for w, c, f in zip(wedges, cums, fracs):
                a1 = 90.0 + rot + g * c
                w.set_theta1(a1)
                w.set_theta2(a1 + g * f)
                w.set_width(wid)
            sweep.set_width(wid)
            ang = 90.0 - 360.0 * 0.55 * t
            sweep.set_theta1(ang)
            sweep.set_theta2(ang + 42)
            sweep.set_alpha(0.20 * env)
            ang2 = 90.0 + 360.0 * 0.8 * t
            orbit.set_theta1(ang2)
            orbit.set_theta2(ang2 + 70)
            orbit.set_alpha(env)
            ctext.set_text(str(int(round(total * g))))
            for fill, share in fills:
                fill.set_width(bar_w * share * g)

        update(None)
        self._anim["class"] = update
        self.class_card.set_badge(f"{len(labels)} class" + ("" if len(labels) == 1 else "es"))
        self.class_card.canvas.draw()

    def _draw_day_chart(self, stats):
        fig = self.day_card.figure
        fig.clear()
        fig.patch.set_facecolor(PALETTE["card"])
        ax = fig.add_subplot(111)
        self._style_axes(ax)
        self._anim["day"] = None

        if stats["num_records"] == 0 or not stats["per_day"]:
            icon = self._empty(ax, "No daily trend\nfor this filter")
            self._anim["day"] = self._empty_updater(icon)
            self.day_card.set_badge("No data")
            self._tidy(fig)
            self.day_card.canvas.draw()
            return

        days_sorted = list(stats["per_day"].keys())
        day_counts = [stats["per_day"][d] for d in days_sorted]
        n = len(days_sorted)
        x = np.arange(n)
        y = np.asarray(day_counts, dtype=float)
        ymax = max(day_counts) if max(day_counts) > 0 else 1
        top = ymax * 1.22 + 0.4

        pad = 1.4 if n == 1 else max(0.45, 0.04 * n)
        ax.set_xlim(-pad, n - 1 + pad)
        ax.set_ylim(0, top)
        step = max(1, math.ceil(n / 12))
        tick_idx = list(range(0, n, step))
        ax.set_xticks(tick_idx)
        ax.set_xticklabels([_fmt_day(days_sorted[i]) for i in tick_idx])
        ax.tick_params(axis="x", labelsize=9)
        if len(tick_idx) > 8:
            for lbl in ax.get_xticklabels():
                lbl.set_rotation(18)
                lbl.set_ha("right")
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
        ax.set_ylabel("Detections", color=PALETTE["muted"], fontsize=8)

        xs, ys = _smooth_curve(y)
        line, = ax.plot(
            [], [], color=PALETTE["accent_2"], linewidth=2.6,
            solid_capstyle="round", zorder=4,
        )
        stems = ax.vlines(
            x, 0, y, color=PALETTE["accent_2"], alpha=0.30, linewidth=1.6, zorder=3,
        )
        markers = ax.scatter(
            x, y, s=70, facecolor=PALETTE["bg"], edgecolor=PALETTE["accent"],
            linewidths=2.2, zorder=6,
        )
        glow = ax.scatter(
            [x[0]], [y[0]], s=300, color=PALETTE["accent"], alpha=0.0,
            linewidths=0, zorder=5,
        )
        dot = ax.scatter(
            [x[0]], [y[0]], s=36, color="white", alpha=0.0, linewidths=0, zorder=7,
        )
        texts = [
            ax.text(
                i, v + top * 0.05, str(day_counts[i]), ha="center", va="bottom",
                color=PALETTE["text"], fontsize=9, fontweight="bold", zorder=7,
            )
            for i, v in enumerate(day_counts)
        ]
        fills = []

        def update(s):
            if s is None:
                p, env, t = 1.0, 0.0, 0.0
            else:
                p, env, t = _ease_out(s / 1.8), _envelope(s), s

            for c in fills:
                c.remove()
            fills.clear()

            if n > 1:
                k = max(2, int(p * len(xs)))
                line.set_data(xs[:k], ys[:k])
                for f in (1.0, 0.72, 0.46, 0.22):
                    fills.append(ax.fill_between(
                        xs[:k], ys[:k] * f, color=PALETTE["accent_2"],
                        alpha=0.07, linewidth=0, zorder=2,
                    ))
                xcur = xs[k - 1]
                mask = x <= xcur + 1e-9
                sc = np.ones(n)
            else:
                line.set_data([], [])
                k = 1
                mask = np.array([p > 0.2])
                sc = np.full(n, p)

            vis = np.column_stack([x[mask], (y * sc)[mask]]) if mask.any() else np.empty((0, 2))
            markers.set_offsets(vis)
            segs = [[(x[i], 0.0), (x[i], y[i] * sc[i])] for i in range(n) if mask[i]]
            stems.set_segments(segs)
            for i, tx in enumerate(texts):
                tx.set_visible(bool(mask[i]))
                tx.set_position((x[i], y[i] * sc[i] + top * 0.05))

            if s is None:
                glow.set_alpha(0.0)
                dot.set_alpha(0.0)
            else:
                if n > 1:
                    idx = int(((t * 0.4) % 1.0) * (k - 1))
                    pos = (xs[idx], ys[idx])
                else:
                    pos = (x[0], y[0] * sc[0])
                pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 1.2 * t)
                glow.set_offsets([pos])
                glow.set_sizes([320 + 260 * pulse])
                glow.set_alpha(0.22 * env * _clamp(p * 2))
                dot.set_offsets([pos])
                dot.set_alpha(0.9 * env * _clamp(p * 2))

        update(None)
        self._anim["day"] = update
        peak = int(np.argmax(y))
        self.day_card.set_badge(f"Peak  {int(y[peak])}  ·  {_fmt_day(days_sorted[peak])}")
        self._tidy(fig)
        self.day_card.canvas.draw()

    # ── shared chart helpers ──
    @staticmethod
    def _empty(ax, message):
        ax.set_facecolor(PALETTE["card"])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        icon = ax.text(
            0.5, 0.55, "◌",
            ha="center", va="center",
            color=PALETTE["dim"], fontsize=24,
            transform=ax.transAxes,
        )
        ax.text(
            0.5, 0.38, message,
            ha="center", va="center",
            color=PALETTE["muted"], fontsize=11,
            transform=ax.transAxes,
        )
        return icon

    @staticmethod
    def _empty_updater(icon):
        def update(s):
            if s is None:
                icon.set_alpha(1.0)
            else:
                icon.set_alpha(0.35 + 0.65 * abs(math.sin(math.pi * s * 0.8)))
        return update

    @staticmethod
    def _style_axes(ax):
        ax.set_facecolor(PALETTE["card"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_color(PALETTE["stroke"])
        ax.tick_params(colors=PALETTE["muted"], labelsize=8, length=0, pad=6)
        ax.grid(axis="x", visible=False)
        ax.grid(axis="y", color=PALETTE["stroke"], linestyle="--", linewidth=0.7, alpha=0.7)
        ax.set_axisbelow(True)

    @staticmethod
    def _qss():
        return f"""
            QWidget#StatsRoot {{
                background: {PALETTE["bg"]};
                color: {PALETTE["text"]};
                font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif;
            }}
            QScrollArea#StatsScroll {{
                background: {PALETTE["bg"]};
                border: none;
            }}
            QWidget#StatsContent {{
                background: {PALETTE["bg"]};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {PALETTE["stroke"]};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {PALETTE["dim"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QProgressBar#SyncBar {{
                background: transparent;
                border: none;
            }}
            QProgressBar#SyncBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {PALETTE["accent_2"]}, stop:1 {PALETTE["accent"]});
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
            QLabel#PageStamp {{
                color: {PALETTE["dim"]};
                font-size: 12px;
            }}
            QFrame#FilterBar {{
                background: {PALETTE["surface"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 14px;
            }}
            QLabel#FilterLabel {{
                color: {PALETTE["dim"]};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.4px;
            }}
            QComboBox {{
                background: {PALETTE["card_alt"]};
                color: {PALETTE["text"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 8px;
                padding: 6px 10px;
                min-height: 20px;
            }}
            QComboBox:hover {{
                border: 1px solid {PALETTE["accent_2"]};
            }}
            QComboBox:focus {{
                border: 1px solid {PALETTE["accent"]};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 22px;
            }}
            QComboBox QAbstractItemView {{
                background: {PALETTE["card"]};
                color: {PALETTE["text"]};
                border: 1px solid {PALETTE["stroke"]};
                selection-background-color: #24344a;
                outline: none;
            }}
            QPushButton#RefreshBtn {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4ff0b0, stop:1 {PALETTE["accent"]});
                color: #062016;
                border: none;
                border-radius: 8px;
                padding: 8px 16px 8px 36px;
                font-weight: 700;
                font-size: 13px;
            }}
            QPushButton#RefreshBtn:hover {{
                background: #62f0bb;
            }}
            QPushButton#RefreshBtn:pressed {{
                background: #2bc48d;
            }}
            QPushButton#RefreshBtn[busy="true"] {{
                background: #35c994;
            }}
            QFrame#KpiCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {PALETTE["card_alt"]}, stop:1 {PALETTE["card"]});
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 14px;
            }}
            QFrame#KpiCard:hover {{
                border: 1px solid #3a4b63;
            }}
            QFrame#ChartCard {{
                background: {PALETTE["card"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 16px;
            }}
            QFrame#ChartCard:hover {{
                border: 1px solid #36465d;
            }}
            QLabel#ChartBadge {{
                color: {PALETTE["muted"]};
                background: {PALETTE["card_alt"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: 600;
            }}
            QLabel#ChartBadge[syncing="true"] {{
                color: {PALETTE["accent"]};
                background: {_rgba(PALETTE["accent"], 0.10)};
                border: 1px solid {_rgba(PALETTE["accent"], 0.45)};
            }}
        """