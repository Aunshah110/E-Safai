from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QSizePolicy, QGridLayout, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
import numpy as np


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


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgba(c, a):
    r, g, b = (int(round(x * 255)) for x in _hex(c))
    return f"rgba({r}, {g}, {b}, {a})"


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
    def __init__(self, title, subtitle="", tall=False):
        super().__init__()
        self.setObjectName("ChartCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
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
        layout.addLayout(head)

        self.figure = Figure(figsize=(5, 3), facecolor=PALETTE["card"])
        self.figure.patch.set_facecolor(PALETTE["card"])
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.canvas.setMinimumHeight(220 if not tall else 240)
        self.canvas.setStyleSheet("background: transparent;")
        layout.addWidget(self.canvas, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)


class StatsPage(QWidget):
    def __init__(self, evidence_manager):
        super().__init__()
        self.evidence_manager = evidence_manager
        self.setObjectName("StatsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self._qss())

        root = QVBoxLayout(self)
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
            tall=True,
        )
        charts.addWidget(self.cam_card, 0, 0)
        charts.addWidget(self.class_card, 0, 1)
        charts.addWidget(self.day_card, 1, 0, 1, 2)
        charts.setRowStretch(0, 5)
        charts.setRowStretch(1, 4)
        root.addLayout(charts, 1)

        self.refresh()

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(16)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        eyebrow = QLabel("E-SAFAI  ·  ANALYTICS")
        eyebrow.setObjectName("Eyebrow")
        titles.addWidget(eyebrow)

        title = QLabel("Reporting & Statistics")
        title.setObjectName("PageTitle")
        titles.addWidget(title)

        self.meta_label = QLabel("Historical detections across cameras")
        self.meta_label.setObjectName("PageMeta")
        titles.addWidget(self.meta_label)
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
        cam_box.addWidget(self.cam_combo)
        fl.addLayout(cam_box)

        refresh_col = QVBoxLayout()
        refresh_col.addStretch()
        refresh_btn = QPushButton("  Refresh")
        refresh_btn.setObjectName("RefreshBtn")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        refresh_btn.setMinimumHeight(34)
        refresh_col.addWidget(refresh_btn)
        fl.addLayout(refresh_col)

        header.addWidget(filters, 0, Qt.AlignmentFlag.AlignBottom)
        return header

    def _build_kpis(self):
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.kpi_total = KpiCard(
            "Total Detections", "0", color="#5eb8ff", icon="●",
            hint="In selected range",
        )
        self.kpi_today = KpiCard(
            "Today", "0", color="#3ee0a2", icon="◆",
            hint="Since midnight",
        )
        self.kpi_top = KpiCard(
            "Most Common", "—", color="#f6c177", icon="■",
            hint="Leading waste class",
        )
        self.kpi_busy = KpiCard(
            "Busiest Camera", "—", color="#ff8b7b", icon="◎",
            hint="Highest detection volume",
        )
        for k in (self.kpi_total, self.kpi_today, self.kpi_top, self.kpi_busy):
            kpi_row.addWidget(k)
        return kpi_row

    def refresh(self):
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

        range_txt = self.range_combo.currentText()
        cam_txt = self.cam_combo.currentText()
        n = stats["num_records"]
        noun = "detection" if n == 1 else "detections"
        self.meta_label.setText(
            f"{n} {noun}  ·  {range_txt}  ·  {cam_txt} cameras"
            if cam_txt == "All"
            else f"{n} {noun}  ·  {range_txt}  ·  {cam_txt}"
        )

        self._draw_camera_chart(stats)
        self._draw_class_chart(stats)
        self._draw_day_chart(stats)

    def _draw_camera_chart(self, stats):
        fig = self.cam_card.figure
        fig.clear()
        fig.patch.set_facecolor(PALETTE["card"])
        ax = fig.add_subplot(111)
        self._style_axes(ax)

        if stats["num_records"] == 0:
            self._empty(ax, "No camera activity\nfor this filter")
            fig.tight_layout(pad=0.6)
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
        bars = ax.bar(
            x, counts, width=0.56, color=CAM_COLORS,
            edgecolor="none", zorder=3,
        )
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
        ax.set_ylabel("Detections", color=PALETTE["muted"], fontsize=8)
        ymax = max(counts) if max(counts) > 0 else 1
        ax.set_ylim(0, ymax * 1.22 + 0.35)
        for bar, val in zip(bars, counts):
            if val <= 0:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + ymax * 0.04,
                str(val), ha="center", va="bottom",
                color=PALETTE["text"], fontsize=9, fontweight="bold",
            )
        fig.tight_layout(pad=0.7)
        self.cam_card.canvas.draw()

    def _draw_class_chart(self, stats):
        fig = self.class_card.figure
        fig.clear()
        fig.patch.set_facecolor(PALETTE["card"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(PALETTE["card"])
        for spine in ax.spines.values():
            spine.set_visible(False)

        if stats["num_records"] == 0 or not stats["class_dist"]:
            self._empty(ax, "No class mix yet\nfor this filter")
            fig.tight_layout(pad=0.6)
            self.class_card.canvas.draw()
            return

        classes = sorted(stats["class_dist"].items(), key=lambda x: x[1], reverse=True)
        labels = [c[0] for c in classes]
        values = [c[1] for c in classes]
        colors = CLASS_COLORS[: len(labels)]
        total = sum(values) or 1

        wedges, _ = ax.pie(
            values,
            startangle=90,
            colors=colors,
            wedgeprops=dict(width=0.42, edgecolor=PALETTE["card"], linewidth=2.2),
        )
        ax.text(
            0, 0.08, str(int(total)),
            ha="center", va="center",
            color=PALETTE["text"], fontsize=16, fontweight="bold",
        )
        ax.text(
            0, -0.18, "items",
            ha="center", va="center",
            color=PALETTE["muted"], fontsize=8,
        )
        legend_labels = [
            f"{lbl}   {val}  ({val / total * 100:.0f}%)"
            for lbl, val in zip(labels, values)
        ]
        ax.legend(
            wedges, legend_labels,
            loc="center left",
            bbox_to_anchor=(0.98, 0.5),
            frameon=False,
            labelcolor=PALETTE["text"],
            fontsize=8,
            handlelength=1.0,
            handleheight=1.0,
            borderpad=0.2,
        )
        ax.set_aspect("equal")
        fig.subplots_adjust(left=0.02, right=0.58, top=0.96, bottom=0.04)
        self.class_card.canvas.draw()

    def _draw_day_chart(self, stats):
        fig = self.day_card.figure
        fig.clear()
        fig.patch.set_facecolor(PALETTE["card"])
        ax = fig.add_subplot(111)
        self._style_axes(ax)

        if stats["num_records"] == 0 or not stats["per_day"]:
            self._empty(ax, "No daily trend\nfor this filter")
            fig.tight_layout(pad=0.6)
            self.day_card.canvas.draw()
            return

        days_sorted = list(stats["per_day"].keys())
        day_counts = [stats["per_day"][d] for d in days_sorted]
        x = np.arange(len(days_sorted))

        ax.fill_between(
            x, day_counts, color=_hex("#5eb8ff") + (0.18,),
            zorder=2, linewidth=0,
        )
        ax.plot(
            x, day_counts,
            color="#5eb8ff", linewidth=2.4,
            marker="o", markersize=7,
            markerfacecolor="#0c1118",
            markeredgecolor="#3ee0a2",
            markeredgewidth=2,
            zorder=4,
        )
        ax.set_xticks(x)
        ax.set_xticklabels(days_sorted)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
        ax.set_ylabel("Detections", color=PALETTE["muted"], fontsize=8)
        ymax = max(day_counts) if day_counts else 1
        ax.set_ylim(0, ymax * 1.22 + 0.4)
        for i, v in enumerate(day_counts):
            ax.text(
                i, v + ymax * 0.06, str(v),
                ha="center", va="bottom",
                color=PALETTE["text"], fontsize=8, fontweight="bold",
            )
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(18)
            lbl.set_ha("right")
        fig.tight_layout(pad=0.8)
        self.day_card.canvas.draw()

    @staticmethod
    def _empty(ax, message):
        ax.set_facecolor(PALETTE["card"])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(
            0.5, 0.55, "◌",
            ha="center", va="center",
            color=PALETTE["dim"], fontsize=22,
            transform=ax.transAxes,
        )
        ax.text(
            0.5, 0.38, message,
            ha="center", va="center",
            color=PALETTE["muted"], fontsize=11,
            transform=ax.transAxes,
        )

    @staticmethod
    def _style_axes(ax):
        ax.set_facecolor(PALETTE["card"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(PALETTE["stroke"])
        ax.spines["bottom"].set_color(PALETTE["stroke"])
        ax.tick_params(colors=PALETTE["muted"], labelsize=8, length=0)
        ax.grid(axis="x", visible=False)
        ax.grid(axis="y", color=PALETTE["stroke"], linestyle="--", linewidth=0.7, alpha=0.85)
        ax.set_axisbelow(True)

    @staticmethod
    def _qss():
        return f"""
            QWidget#StatsRoot {{
                background: {PALETTE["bg"]};
                color: {PALETTE["text"]};
                font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif;
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
            QFrame#KpiCard {{
                background: {PALETTE["card"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 14px;
            }}
            QFrame#ChartCard {{
                background: {PALETTE["card"]};
                border: 1px solid {PALETTE["stroke"]};
                border-radius: 16px;
            }}
        """
