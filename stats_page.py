from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class KpiCard(QFrame):
    def __init__(self, title, value, color="#4fc3f7"):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background: #2a2a2a; border: 1px solid #444; "
            f"border-radius: 8px; }}"
        )
        self.setMinimumHeight(90)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet("color: #999; font-size: 12px;")
        layout.addWidget(t)

        v = QLabel(str(value))
        v.setStyleSheet(f"color: {color}; font-size: 26px; font-weight: bold;")
        layout.addWidget(v)


class StatsPage(QWidget):
    def __init__(self, evidence_manager):
        super().__init__()
        self.evidence_manager = evidence_manager

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- Header with filters ----
        header = QHBoxLayout()
        title = QLabel("Reporting & Statistics")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #fff;")
        header.addWidget(title)
        header.addStretch()

        header.addWidget(QLabel("Range:"))
        self.range_combo = QComboBox()
        self.range_combo.addItem("All time", None)
        self.range_combo.addItem("Today", 1)
        self.range_combo.addItem("Last 7 days", 7)
        self.range_combo.addItem("Last 30 days", 30)
        self.range_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.range_combo)

        header.addWidget(QLabel("Camera:"))
        self.cam_combo = QComboBox()
        self.cam_combo.addItem("All", None)
        for i in range(4):
            self.cam_combo.addItem(f"Camera {i + 1}", i)
        self.cam_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.cam_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        root.addLayout(header)

        # ---- KPI row ----
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self.kpi_total = KpiCard("Total Detections", "0")
        self.kpi_today = KpiCard("Today", "0", color="#81c784")
        self.kpi_top = KpiCard("Most Common", "—", color="#ffb74d")
        self.kpi_busy = KpiCard("Busiest Camera", "—", color="#e57373")
        for k in (self.kpi_total, self.kpi_today, self.kpi_top, self.kpi_busy):
            kpi_row.addWidget(k)
        root.addLayout(kpi_row)

        # ---- Chart area ----
        self.figure = Figure(figsize=(10, 6), facecolor="#1e1e1e")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.setStyleSheet("background: #1e1e1e;")
        root.addWidget(self.canvas, 1)

        self.refresh()

    def refresh(self):
        days = self.range_combo.currentData()
        cam_id = self.cam_combo.currentData()
        stats = self.evidence_manager.compute_stats(days=days, cam_id=cam_id)

        # Update KPI cards
        self.kpi_total.findChild(QLabel, "").setText(str(stats["total"])) if False else None
        # KPI cards: replace value labels directly
        def set_kpi(card, value):
            labels = card.findChildren(QLabel)
            if len(labels) >= 2:
                labels[1].setText(str(value))

        set_kpi(self.kpi_total, stats["total"])
        set_kpi(self.kpi_today, stats["today"])
        set_kpi(self.kpi_top, stats["top_class"])
        set_kpi(self.kpi_busy,
                f"Cam {int(stats['busiest_cam']) + 1}"
                if isinstance(stats["busiest_cam"], int) else "—")

        # Redraw charts
        self.figure.clear()
        self.figure.patch.set_facecolor("#1e1e1e")

        if stats["num_records"] == 0:
            ax = self.figure.add_subplot(111)
            ax.set_facecolor("#1e1e1e")
            ax.text(0.5, 0.5, "No data for the selected filter",
                    ha="center", va="center", color="#888", fontsize=14)
            ax.set_xticks([])
            ax.set_yticks([])
            self.canvas.draw()
            return

        # --- 1. Per-camera bar chart (top-left) ---
        ax1 = self.figure.add_subplot(221)
        self._style_axes(ax1)
        cams = sorted(stats["per_cam"].keys())
        cam_labels = [f"Cam {int(c) + 1}" for c in cams]
        cam_counts = [stats["per_cam"][c] for c in cams]
        ax1.bar(cam_labels, cam_counts, color="#42a5f5")
        ax1.set_title("Detections per Camera", color="#ddd", fontsize=11)
        ax1.tick_params(colors="#aaa", labelsize=9)
        for i, v in enumerate(cam_counts):
            ax1.text(i, v, str(v), ha="center", va="bottom", color="#ddd", fontsize=9)

        # --- 2. Class distribution (top-right) ---
        ax2 = self.figure.add_subplot(222)
        self._style_axes(ax2)
        if stats["class_dist"]:
            classes = sorted(stats["class_dist"].items(),
                             key=lambda x: x[1], reverse=True)
            labels = [c[0] for c in classes]
            values = [c[1] for c in classes]
            colors = ["#ef5350", "#ab47bc", "#5c6bc0", "#26a69a",
                      "#66bb6a", "#ffa726", "#8d6e63", "#78909c", "#d4e157"]
            ax2.bar(labels, values, color=colors[:len(labels)])
            ax2.set_title("Class Distribution", color="#ddd", fontsize=11)
            ax2.tick_params(colors="#aaa", labelsize=8)
            for i, v in enumerate(values):
                ax2.text(i, v, str(v), ha="center", va="bottom",
                         color="#ddd", fontsize=8)
            for lbl in ax2.get_xticklabels():
                lbl.set_rotation(30)
                lbl.set_ha("right")
        else:
            ax2.text(0.5, 0.5, "No classes", ha="center", va="center",
                     color="#888", fontsize=12)
            ax2.set_xticks([])
            ax2.set_yticks([])
        ax2.set_title("Class Distribution", color="#ddd", fontsize=11)

        # --- 3. Daily timeline (bottom, full width) ---
        ax3 = self.figure.add_subplot(212)
        self._style_axes(ax3)
        days_sorted = list(stats["per_day"].keys())
        day_counts = [stats["per_day"][d] for d in days_sorted]
        ax3.plot(days_sorted, day_counts, marker="o", color="#4fc3f7", linewidth=2)
        ax3.fill_between(days_sorted, day_counts, color="#4fc3f7", alpha=0.2)
        ax3.set_title("Detections per Day", color="#ddd", fontsize=11)
        ax3.tick_params(colors="#aaa", labelsize=8)
        for lbl in ax3.get_xticklabels():
            lbl.set_rotation(20)
            lbl.set_ha("right")

        self.figure.tight_layout(pad=1.5)
        self.canvas.draw()

    @staticmethod
    def _style_axes(ax):
        ax.set_facecolor("#1e1e1e")
        ax.spines["bottom"].set_color("#555")
        ax.spines["top"].set_color("#555")
        ax.spines["left"].set_color("#555")
        ax.spines["right"].set_color("#555")
        ax.grid(True, alpha=0.15)