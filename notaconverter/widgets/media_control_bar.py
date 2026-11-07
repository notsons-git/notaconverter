import math
from typing import Optional, Tuple
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout
)
from .tactical_input import TacticalNumberEdit
from .tactical_icons import get_tactical_icon


POPUP_STYLE = """
QFrame#UpwardPopup {
    background-color: #181B16;
    border: 1px solid #2B3026;
    border-radius: 4px;
}
QLabel {
    color: #E8EBE4;
    font-size: 8.5pt;
    font-family: "Segoe UI", -apple-system, sans-serif;
}
QLabel#PopupHeader {
    color: #9EF41A;
    font-weight: 700;
    font-size: 8pt;
    letter-spacing: 0.8px;
    font-family: "Consolas", monospace;
    border: none;
    padding-bottom: 2px;
    margin-bottom: 4px;
}
QLabel#TechLabel {
    color: #92968C;
    font-size: 8pt;
    font-family: "Consolas", monospace;
}
QPushButton {
    background-color: #1E221B;
    color: #E8EBE4;
    border: 1px solid #2B3026;
    border-radius: 3px;
    padding: 5px 10px;
    font-size: 8pt;
    font-weight: 600;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #262B21;
    border-color: #3E4636;
}
QPushButton:pressed {
    background-color: #151813;
    border-color: #9EF41A;
}
QPushButton#ActiveBtn {
    background-color: #232B1C;
    border: 1px solid #9EF41A;
    color: #9EF41A;
}
QPushButton#PrimaryActionBtn {
    background-color: #9EF41A;
    border: 1px solid #9EF41A;
    color: #121411;
    font-weight: 700;
}
QPushButton#PrimaryActionBtn:hover {
    background-color: #ACF738;
}
"""


class BaseUpwardPopup(QFrame):
    """Base frameless popup opening directly ABOVE its anchor button."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("UpwardPopup")
        self.setStyleSheet(POPUP_STYLE)

    def show_above(self, anchor: QWidget):
        self.adjustSize()
        anchor_pos = anchor.mapToGlobal(QPoint(0, 0))
        size = self.sizeHint()

        target_x = anchor_pos.x()
        target_y = anchor_pos.y() - size.height() - 4

        # Clamp against screen boundaries
        screen = anchor.screen()
        if screen:
            geo = screen.availableGeometry()
            if target_x + size.width() > geo.right():
                target_x = geo.right() - size.width() - 8
            if target_x < geo.left():
                target_x = geo.left() + 8
            if target_y < geo.top():
                target_y = anchor_pos.y() + anchor.height() + 4

        self.move(target_x, target_y)
        self.show()


class TrimCropPopup(BaseUpwardPopup):
    """Popup 1: ОБРЕЗКА (Trim boundaries & crop presets)."""
    trim_changed = pyqtSignal(float, float)        # start, end
    fit_3s_requested = pyqtSignal()
    reset_trim_requested = pyqtSignal()
    crop_preset_selected = pyqtSignal(object)       # float ratio or None
    reset_crop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        lbl_head = QLabel("ОБРЕЗКА")
        lbl_head.setObjectName("PopupHeader")
        v.addWidget(lbl_head)

        # 1. IN / OUT controls with TacticalNumberEdit
        time_grid = QGridLayout()
        time_grid.setSpacing(6)

        lbl_in = QLabel("IN:")
        lbl_in.setObjectName("TechLabel")
        self.spin_start = TacticalNumberEdit(value=0.0, min_value=0.0, max_value=999.0, decimals=2, step=0.05, unit="s")
        self.spin_start.valueChanged.connect(self._on_values_committed)
        time_grid.addWidget(lbl_in, 0, 0)
        time_grid.addWidget(self.spin_start, 0, 1)

        lbl_out = QLabel("OUT:")
        lbl_out.setObjectName("TechLabel")
        self.spin_end = TacticalNumberEdit(value=3.0, min_value=0.0, max_value=999.0, decimals=2, step=0.05, unit="s")
        self.spin_end.valueChanged.connect(self._on_values_committed)
        time_grid.addWidget(lbl_out, 1, 0)
        time_grid.addWidget(self.spin_end, 1, 1)

        v.addLayout(time_grid)

        # 2. Segment duration display
        self.lbl_duration_info = QLabel("ДЛИТЕЛЬНОСТЬ: 3.00s")
        self.lbl_duration_info.setObjectName("TechLabel")
        v.addWidget(self.lbl_duration_info)

        # 3. Actions: Fit 3s & Reset Trim
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_fit = QPushButton("FIT 3.0s")
        self.btn_fit.clicked.connect(self._on_fit_clicked)
        btn_row.addWidget(self.btn_fit)

        self.btn_reset_trim = QPushButton("СБРОС")
        self.btn_reset_trim.setIcon(get_tactical_icon("rotate-ccw", size=11))
        self.btn_reset_trim.clicked.connect(self.reset_trim_requested.emit)
        btn_row.addWidget(self.btn_reset_trim)
        v.addLayout(btn_row)

        # Separator line
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #2B3026; margin-top: 2px; margin-bottom: 2px;")
        v.addWidget(sep)

        # 4. Aspect Ratio Crop Presets
        lbl_crop_head = QLabel("ПРОПОРЦИИ:")
        lbl_crop_head.setObjectName("TechLabel")
        v.addWidget(lbl_crop_head)

        crop_grid = QGridLayout()
        crop_grid.setSpacing(5)

        self.btn_square = QPushButton("1:1")
        self.btn_square.clicked.connect(lambda: self.crop_preset_selected.emit(1.0))
        crop_grid.addWidget(self.btn_square, 0, 0)

        self.btn_free = QPushButton("СВОБОДНЫЙ")
        self.btn_free.clicked.connect(lambda: self.crop_preset_selected.emit(None))
        crop_grid.addWidget(self.btn_free, 0, 1)

        self.btn_4_3 = QPushButton("4:3")
        self.btn_4_3.clicked.connect(lambda: self.crop_preset_selected.emit(4.0 / 3.0))
        crop_grid.addWidget(self.btn_4_3, 1, 0)

        self.btn_16_9 = QPushButton("16:9")
        self.btn_16_9.clicked.connect(lambda: self.crop_preset_selected.emit(16.0 / 9.0))
        crop_grid.addWidget(self.btn_16_9, 1, 1)

        v.addLayout(crop_grid)

        self.btn_reset_crop = QPushButton("СБРОС")
        self.btn_reset_crop.setIcon(get_tactical_icon("rotate-ccw", size=11))
        self.btn_reset_crop.clicked.connect(self.reset_crop_requested.emit)
        v.addWidget(self.btn_reset_crop)

    def set_values(self, start: float, end: float, max_dur: float):
        self._updating = True
        self.spin_start.setRange(0.0, max_dur)
        self.spin_end.setRange(0.0, max_dur)
        self.spin_start.setValue(start)
        self.spin_end.setValue(end)
        self._update_dur_label(start, end)
        self._updating = False

    def _on_values_committed(self):
        if self._updating:
            return
        s = self.spin_start.value()
        e = self.spin_end.value()
        if e <= s:
            e = s + 0.05
            self.spin_end.setValue(e)
        self._update_dur_label(s, e)
        self.trim_changed.emit(s, e)

    def _on_fit_clicked(self):
        self.fit_3s_requested.emit()

    def _update_dur_label(self, start: float, end: float):
        dur = max(0.0, end - start)
        if dur > 3.01:
            self.lbl_duration_info.setText(f"ДЛИТЕЛЬНОСТЬ: {dur:.2f}s  ⚠ > 3.0s")
            self.lbl_duration_info.setStyleSheet("color: #FF4D4D; font-family: 'Consolas', monospace; font-weight: bold;")
        else:
            self.lbl_duration_info.setText(f"ДЛИТЕЛЬНОСТЬ: {dur:.2f}s")
            self.lbl_duration_info.setStyleSheet("color: #9EF41A; font-family: 'Consolas', monospace;")


class SpeedPopup(BaseUpwardPopup):
    """Popup 2: СКОРОСТЬ (Playback Speed & Result Duration Calculation, unlimited speed)."""
    speed_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._speed: float = 1.0
        self._source_dur: float = 3.0
        self._updating = False

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        lbl_head = QLabel("СКОРОСТЬ")
        lbl_head.setObjectName("PopupHeader")
        v.addWidget(lbl_head)

        # Quick preset buttons (1x, 1.5x, 2x, 3x, 4x, 6x)
        btn_grid = QGridLayout()
        btn_grid.setSpacing(5)
        self.preset_btns = {}
        presets = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
        for idx, spd in enumerate(presets):
            btn = QPushButton(f"{spd:.1f}x" if spd != int(spd) else f"{int(spd)}x")
            btn.clicked.connect(lambda checked, s=spd: self._set_speed(s))
            btn_grid.addWidget(btn, idx // 3, idx % 3)
            self.preset_btns[spd] = btn
        v.addLayout(btn_grid)

        # Custom speed input with TacticalNumberEdit (up to 50x)
        cust_row = QHBoxLayout()
        cust_row.setSpacing(6)
        lbl_custom = QLabel("СКОРОСТЬ:")
        lbl_custom.setObjectName("TechLabel")
        cust_row.addWidget(lbl_custom)

        self.spin_speed = TacticalNumberEdit(
            value=1.0,
            min_value=0.10,
            max_value=50.00,
            decimals=2,
            step=0.25,
            unit="x"
        )
        self.spin_speed.valueChanged.connect(self._on_input_speed_changed)
        cust_row.addWidget(self.spin_speed)
        v.addLayout(cust_row)

        # Output duration feedback
        self.lbl_dur_calc = QLabel("ИТОГ: 3.00s")
        self.lbl_dur_calc.setObjectName("TechLabel")
        v.addWidget(self.lbl_dur_calc)

        # Reset button
        btn_reset = QPushButton("СБРОС (1x)")
        btn_reset.setIcon(get_tactical_icon("rotate-ccw", size=11))
        btn_reset.clicked.connect(lambda: self._set_speed(1.00))
        v.addWidget(btn_reset)

    def set_source_duration(self, dur: float):
        self._source_dur = max(0.05, dur)
        self._update_display()

    def set_speed(self, speed: float):
        self._set_speed(speed, emit_signal=False)

    def _set_speed(self, spd: float, emit_signal: bool = True):
        self._updating = True
        self._speed = max(0.10, min(50.00, spd))
        self.spin_speed.setValue(self._speed)
        self._update_display()
        self._updating = False
        if emit_signal:
            self.speed_changed.emit(self._speed)

    def _on_input_speed_changed(self, val: float):
        if self._updating:
            return
        self._speed = val
        self._update_display()
        self.speed_changed.emit(self._speed)

    def _update_display(self):
        out_dur = self._source_dur / max(0.05, self._speed)
        # Highlight active preset
        for spd, btn in self.preset_btns.items():
            if abs(spd - self._speed) < 0.01:
                btn.setObjectName("ActiveBtn")
            else:
                btn.setObjectName("")
            btn.setStyle(btn.style())

        if out_dur > 3.01:
            self.lbl_dur_calc.setText(f"ИТОГ: {out_dur:.2f}s  ⚠ > 3.0s")
            self.lbl_dur_calc.setStyleSheet("color: #FF4D4D; font-family: 'Consolas', monospace; font-size: 8pt; font-weight: bold;")
        else:
            self.lbl_dur_calc.setText(f"ИТОГ: {out_dur:.2f}s")
            self.lbl_dur_calc.setStyleSheet("color: #9EF41A; font-family: 'Consolas', monospace; font-size: 8pt;")


class FpsPopup(BaseUpwardPopup):
    """Popup 3: FPS (Frame Rate Selection for Export)."""
    fps_selected = pyqtSignal(int)  # 0 for Auto, or 15, 24, 30, or custom

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fps: int = 0  # 0 = Auto
        self._updating = False

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)

        lbl_head = QLabel("FPS")
        lbl_head.setObjectName("PopupHeader")
        v.addWidget(lbl_head)

        self.btns = {}
        options = [
            (0, "AUTO"),
            (30, "30 FPS"),
            (24, "24 FPS"),
            (15, "15 FPS"),
        ]

        for val, label in options:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, v=val: self._select_fps(v))
            v.addWidget(btn)
            self.btns[val] = btn

        # Custom FPS input row
        custom_row = QHBoxLayout()
        custom_row.setSpacing(6)
        lbl_c = QLabel("СВОЙ:")
        lbl_c.setObjectName("TechLabel")
        custom_row.addWidget(lbl_c)

        self.spin_fps = TacticalNumberEdit(
            value=30,
            min_value=5,
            max_value=30,
            decimals=0,
            step=1,
            unit="FPS"
        )
        self.spin_fps.valueChanged.connect(self._on_custom_fps_changed)
        custom_row.addWidget(self.spin_fps)
        v.addLayout(custom_row)

    def set_fps(self, fps: int):
        self._fps = fps if fps >= 0 else 0
        if self._fps > 0:
            self.spin_fps.setValue(self._fps)
        self._update_highlight()

    def _select_fps(self, fps: int):
        self._fps = fps
        if fps > 0:
            self.spin_fps.setValue(fps)
        self._update_highlight()
        self.fps_selected.emit(fps)

    def _on_custom_fps_changed(self, val: float):
        fps = int(round(val))
        self._fps = fps
        self._update_highlight()
        self.fps_selected.emit(fps)

    def _update_highlight(self):
        for val, btn in self.btns.items():
            if val == self._fps:
                btn.setObjectName("ActiveBtn")
            else:
                btn.setObjectName("")
            btn.setStyle(btn.style())


class ResolutionPopup(BaseUpwardPopup):
    """Popup 4: РАЗРЕШЕНИЕ (Dimensions & Independent Non-Proportional Scaling Lock)."""
    resolution_changed = pyqtSignal(int, int, bool) # width, height, is_locked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._width: int = 512
        self._height: int = 512
        self._is_locked: bool = True
        self._aspect_ratio: float = 1.0  # current reference ratio (width / height)
        self._updating: bool = False

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        lbl_head = QLabel("РАЗРЕШЕНИЕ")
        lbl_head.setObjectName("PopupHeader")
        v.addWidget(lbl_head)

        # Row with W, Lock, H using TacticalNumberEdit
        row = QHBoxLayout()
        row.setSpacing(6)

        lbl_w = QLabel("W:")
        lbl_w.setObjectName("TechLabel")
        self.spin_w = TacticalNumberEdit(
            value=512,
            min_value=32,
            max_value=512,
            decimals=0,
            step=2,
            unit="px",
            even_only=True
        )
        self.spin_w.valueChanged.connect(self._on_w_committed)
        row.addWidget(lbl_w)
        row.addWidget(self.spin_w)

        # Lock toggle button
        self.btn_lock = QPushButton()
        self.btn_lock.setIcon(get_tactical_icon("lock", size=14))
        self.btn_lock.setCheckable(True)
        self.btn_lock.setChecked(True)
        self.btn_lock.setFixedWidth(34)
        self.btn_lock.clicked.connect(self._on_lock_toggled)
        row.addWidget(self.btn_lock)

        lbl_h = QLabel("H:")
        lbl_h.setObjectName("TechLabel")
        self.spin_h = TacticalNumberEdit(
            value=512,
            min_value=32,
            max_value=512,
            decimals=0,
            step=2,
            unit="px",
            even_only=True
        )
        self.spin_h.valueChanged.connect(self._on_h_committed)
        row.addWidget(lbl_h)
        row.addWidget(self.spin_h)

        v.addLayout(row)

        # Reset button
        btn_reset = QPushButton("СБРОС (512px)")
        btn_reset.clicked.connect(self._reset_to_default)
        v.addWidget(btn_reset)

    def set_dimensions(self, w: int, h: int, locked: bool, ref_aspect: Optional[float] = None):
        self._updating = True
        self._width = max(32, min(512, (w // 2) * 2))
        self._height = max(32, min(512, (h // 2) * 2))
        self._is_locked = locked
        if ref_aspect and ref_aspect > 0:
            self._aspect_ratio = ref_aspect
        else:
            self._aspect_ratio = self._width / max(1, self._height)

        self.spin_w.setValue(self._width)
        self.spin_h.setValue(self._height)
        self.btn_lock.setChecked(self._is_locked)
        self._update_lock_ui()
        self._updating = False

    def _on_lock_toggled(self):
        self._is_locked = self.btn_lock.isChecked()
        if self._is_locked:
            self._aspect_ratio = self.spin_w.value() / max(1, self.spin_h.value())
        self._update_lock_ui()
        self.resolution_changed.emit(self.spin_w.int_value(), self.spin_h.int_value(), self._is_locked)

    def _on_w_committed(self, new_w_val: float):
        if self._updating:
            return
        new_w = (int(round(new_w_val)) // 2) * 2
        if self._is_locked and self._aspect_ratio > 0:
            self._updating = True
            new_h = int(round(new_w / self._aspect_ratio))
            new_h = max(32, min(512, (new_h // 2) * 2))
            self.spin_h.setValue(new_h)
            self._updating = False
        self._update_lock_ui()
        self.resolution_changed.emit(self.spin_w.int_value(), self.spin_h.int_value(), self._is_locked)

    def _on_h_committed(self, new_h_val: float):
        if self._updating:
            return
        new_h = (int(round(new_h_val)) // 2) * 2
        if self._is_locked and self._aspect_ratio > 0:
            self._updating = True
            new_w = int(round(new_h * self._aspect_ratio))
            new_w = max(32, min(512, (new_w // 2) * 2))
            self.spin_w.setValue(new_w)
            self._updating = False
        self._update_lock_ui()
        self.resolution_changed.emit(self.spin_w.int_value(), self.spin_h.int_value(), self._is_locked)

    def _reset_to_default(self):
        ar = self._aspect_ratio if self._aspect_ratio > 0 else 1.0
        if ar >= 1.0:
            w = 512
            h = max(32, min(512, int(round(512 / ar)) // 2 * 2))
        else:
            h = 512
            w = max(32, min(512, int(round(512 * ar)) // 2 * 2))

        self.set_dimensions(w, h, locked=True, ref_aspect=ar)
        self.resolution_changed.emit(w, h, True)

    def _update_lock_ui(self):
        if self._is_locked:
            self.btn_lock.setIcon(get_tactical_icon("lock", size=14))
            self.btn_lock.setText("")
            self.btn_lock.setObjectName("ActiveBtn")
            self.btn_lock.setToolTip("Пропорции зафиксированы")
        else:
            self.btn_lock.setIcon(get_tactical_icon("unlock", normal_color="#92968C", active_color="#FFB830", size=14))
            self.btn_lock.setText("")
            self.btn_lock.setObjectName("")
            self.btn_lock.setToolTip("Свободное изменение пропорций (растяжение)")
        self.btn_lock.setStyle(self.btn_lock.style())


class MediaControlBar(QFrame):
    """
    Compact control toolbar situated directly ABOVE the timeline.
    Houses Transport [Play/Pause] and 4 upward popups:
    1. ОБРЕЗКА
    2. СКОРОСТЬ
    3. FPS
    4. РАЗРЕШЕНИЕ
    """
    play_toggled = pyqtSignal()
    trim_updated = pyqtSignal(float, float)
    speed_updated = pyqtSignal(float)
    fps_updated = pyqtSignal(int)
    resolution_updated = pyqtSignal(int, int, bool)
    fit_3s_requested = pyqtSignal()
    crop_preset_requested = pyqtSignal(object)
    reset_crop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet("""
            QFrame {
                background-color: #141712;
                border: 1px solid #23271E;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #1A1E17;
                color: #E8EBE4;
                border: 1px solid #2B3026;
                border-radius: 3px;
                padding: 4px 10px;
                font-size: 8pt;
                font-weight: 600;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            QPushButton:hover {
                background-color: #242920;
                border-color: #3E4636;
            }
            QPushButton:pressed {
                background-color: #121411;
                border-color: #9EF41A;
            }
            QPushButton#PrimaryPlayBtn {
                background-color: #1E2519;
                border: 1px solid #9EF41A;
                color: #9EF41A;
                font-weight: 700;
                min-width: 86px;
            }
            QPushButton#PrimaryPlayBtn:hover {
                background-color: #27331F;
                border-color: #B2F835;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # 1. Transport Play Button
        self.btn_play = QPushButton("PLAY")
        self.btn_play.setIcon(get_tactical_icon("play", normal_color="#121411", active_color="#121411", size=13))
        self.btn_play.setObjectName("PrimaryPlayBtn")
        self.btn_play.clicked.connect(self.play_toggled.emit)
        layout.addWidget(self.btn_play)

        # Separator
        sep1 = QFrame()
        sep1.setFixedSize(1, 18)
        sep1.setStyleSheet("background-color: #2B3026;")
        layout.addWidget(sep1)

        # 2. Popup 1 Button: ОБРЕЗКА
        self.btn_trim = QPushButton("3.00s ▲")
        self.btn_trim.setIcon(get_tactical_icon("scissors", size=13))
        self.btn_trim.setToolTip("Настройка границ обрезки и пропорций кадрирования")
        self.btn_trim.clicked.connect(lambda: self.popup_trim.show_above(self.btn_trim))
        layout.addWidget(self.btn_trim)

        # 3. Popup 2 Button: СКОРОСТЬ
        self.btn_speed = QPushButton("1.0× ▲")
        self.btn_speed.setIcon(get_tactical_icon("zap", size=13))
        self.btn_speed.setToolTip("Скорость воспроизведения и масштаб таймлайна")
        self.btn_speed.clicked.connect(lambda: self.popup_speed.show_above(self.btn_speed))
        layout.addWidget(self.btn_speed)

        # 4. Popup 3 Button: FPS
        self.btn_fps = QPushButton("AUTO ▲")
        self.btn_fps.setIcon(get_tactical_icon("film", size=13))
        self.btn_fps.setToolTip("Частота кадров экспорта")
        self.btn_fps.clicked.connect(lambda: self.popup_fps.show_above(self.btn_fps))
        layout.addWidget(self.btn_fps)

        # 5. Popup 4 Button: РАЗРЕШЕНИЕ
        self.btn_resolution = QPushButton("512×512 🔒 ▲")
        self.btn_resolution.setIcon(get_tactical_icon("maximize-2", size=13))
        self.btn_resolution.setToolTip("Выходное разрешение и замок пропорций")
        self.btn_resolution.clicked.connect(lambda: self.popup_resolution.show_above(self.btn_resolution))
        layout.addWidget(self.btn_resolution)

        layout.addStretch()

        # Instantiate popups
        self.popup_trim = TrimCropPopup(self)
        self.popup_speed = SpeedPopup(self)
        self.popup_fps = FpsPopup(self)
        self.popup_resolution = ResolutionPopup(self)

        # Connect internal popup signals
        self.popup_trim.trim_changed.connect(self._on_trim_changed)
        self.popup_trim.fit_3s_requested.connect(self.fit_3s_requested.emit)
        self.popup_trim.reset_trim_requested.connect(lambda: self.trim_updated.emit(0.0, 3.0))
        self.popup_trim.crop_preset_selected.connect(self.crop_preset_requested.emit)
        self.popup_trim.reset_crop_requested.connect(self.reset_crop_requested.emit)

        self.popup_speed.speed_changed.connect(self._on_speed_changed)
        self.popup_fps.fps_selected.connect(self._on_fps_changed)
        self.popup_resolution.resolution_changed.connect(self._on_resolution_changed)

    def set_playing_state(self, is_playing: bool):
        if is_playing:
            self.btn_play.setIcon(get_tactical_icon("pause", normal_color="#121411", active_color="#121411", size=13))
            self.btn_play.setText("PAUSE")
        else:
            self.btn_play.setIcon(get_tactical_icon("play", normal_color="#121411", active_color="#121411", size=13))
            self.btn_play.setText("PLAY")

    def update_trim_display(self, start: float, end: float, max_dur: float, source_dur: Optional[float] = None):
        dur = max(0.0, end - start)
        self.btn_trim.setIcon(get_tactical_icon("scissors", size=13))
        self.btn_trim.setText(f"{dur:.2f}s ▲")
        self.popup_trim.set_values(start, end, max_dur)
        if source_dur is not None:
            self.popup_speed.set_source_duration(source_dur)
        else:
            self.popup_speed.set_source_duration(dur * getattr(self.popup_speed, "_speed", 1.0))

    def update_speed_display(self, speed: float):
        spd_str = f"{speed:.1f}×" if speed != int(speed) else f"{int(speed)}×"
        self.btn_speed.setIcon(get_tactical_icon("zap", size=13))
        self.btn_speed.setText(f"{spd_str} ▲")
        self.popup_speed.set_speed(speed)

    def update_fps_display(self, fps: int):
        txt = "AUTO" if fps <= 0 else str(fps)
        self.btn_fps.setIcon(get_tactical_icon("film", size=13))
        self.btn_fps.setText(f"{txt} ▲")
        self.popup_fps.set_fps(fps)

    def update_resolution_display(self, w: int, h: int, locked: bool, ref_aspect: Optional[float] = None):
        lock_icon = "🔒" if locked else "🔓"
        self.btn_resolution.setIcon(get_tactical_icon("maximize-2", size=13))
        self.btn_resolution.setText(f"{w}×{h} {lock_icon} ▲")
        self.popup_resolution.set_dimensions(w, h, locked, ref_aspect)

    def _on_trim_changed(self, start: float, end: float):
        dur = max(0.0, end - start)
        self.btn_trim.setIcon(get_tactical_icon("scissors", size=13))
        self.btn_trim.setText(f"{dur:.2f}s ▲")
        self.popup_speed.set_source_duration(dur)
        self.trim_updated.emit(start, end)

    def _on_speed_changed(self, speed: float):
        spd_str = f"{speed:.1f}×" if speed != int(speed) else f"{int(speed)}×"
        self.btn_speed.setIcon(get_tactical_icon("zap", size=13))
        self.btn_speed.setText(f"{spd_str} ▲")
        self.speed_updated.emit(speed)

    def _on_fps_changed(self, fps: int):
        txt = "AUTO" if fps <= 0 else str(fps)
        self.btn_fps.setIcon(get_tactical_icon("film", size=13))
        self.btn_fps.setText(f"{txt} ▲")
        self.fps_updated.emit(fps)

    def _on_resolution_changed(self, w: int, h: int, locked: bool):
        lock_icon = "🔒" if locked else "🔓"
        self.btn_resolution.setIcon(get_tactical_icon("maximize-2", size=13))
        self.btn_resolution.setText(f"{w}×{h} {lock_icon} ▲")
        self.resolution_updated.emit(w, h, locked)
