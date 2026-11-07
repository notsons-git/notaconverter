from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QRadioButton, QButtonGroup, QLineEdit, QFileDialog,
    QSlider, QGroupBox, QWidget, QFrame, QScrollArea, QSizePolicy
)

from .config import AppConfig
from .widgets.tactical_input import TacticalNumberEdit
from .widgets.tactical_icons import get_tactical_icon

ASSETS_DIR = Path(__file__).parent / "assets"
CHECK_ICON = str(ASSETS_DIR / "check.svg").replace("\\", "/")
RADIO_ICON = str(ASSETS_DIR / "radio.svg").replace("\\", "/")


class NoWheelSlider(QSlider):
    """Horizontal slider that ignores mouse wheel so the parent QScrollArea scrolls smoothly."""
    def wheelEvent(self, event):
        event.ignore()


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("CONFIGURATION // NOTACONVERTER")
        self.resize(560, 680)
        self.setMinimumSize(480, 440)

        ico_path = ASSETS_DIR / "app.ico"
        if ico_path.exists():
            self.setWindowIcon(QIcon(str(ico_path)))

        style = """
            QDialog {
                background-color: #121411;
                color: #E8EBE4;
            }
            QGroupBox {
                background-color: #181B16;
                border: 1px solid #2B3026;
                border-radius: 4px;
                margin-top: 14px;
                padding: 16px 14px 14px 14px;
                font-family: "Segoe UI", -apple-system, sans-serif;
                font-weight: 700;
                font-size: 8.5pt;
                color: #9EF41A;
                letter-spacing: 0.5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background-color: #181B16;
            }
            QLabel {
                color: #E8EBE4;
                font-size: 8.5pt;
                font-family: "Segoe UI", -apple-system, sans-serif;
            }
            QRadioButton, QCheckBox {
                color: #E8EBE4;
                font-size: 8.5pt;
                spacing: 8px;
                padding: 2px 0px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: #121411;
                border: 1px solid #32372D;
                border-radius: 2px;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #9EF41A;
            }
            QCheckBox::indicator:checked {
                background-color: #9EF41A;
                border: 1px solid #9EF41A;
                image: url("__CHECK_ICON__");
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                background-color: #121411;
                border: 1px solid #32372D;
                border-radius: 8px;
            }
            QRadioButton::indicator:hover {
                border: 1px solid #9EF41A;
            }
            QRadioButton::indicator:checked {
                background-color: #9EF41A;
                border: 1px solid #9EF41A;
                image: url("__RADIO_ICON__");
            }
            QLineEdit {
                background-color: #121411;
                border: 1px solid #2B3026;
                border-radius: 3px;
                color: #E8EBE4;
                padding: 6px 10px;
                font-size: 8.5pt;
                font-family: "Cascadia Code", "Consolas", monospace;
            }
            QLineEdit:hover {
                border: 1px solid #3E4537;
            }
            QLineEdit:focus {
                border: 1px solid #9EF41A;
                background-color: #151813;
            }
            QLineEdit:disabled {
                background-color: #0E100D;
                color: #555B4F;
                border: 1px solid #1C201A;
            }
            QSlider {
                margin: 4px 0px 6px 0px;
            }
            QSlider::groove:horizontal {
                height: 3px;
                background: #252A20;
                border-radius: 1px;
            }
            QSlider::sub-page:horizontal {
                background: #9EF41A;
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: #E8EBE4;
                border: 1px solid #9EF41A;
                width: 12px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal:hover {
                background: #9EF41A;
            }
            QPushButton {
                background-color: #1E221B;
                color: #E8EBE4;
                border: 1px solid #2B3026;
                border-radius: 3px;
                padding: 7px 16px;
                font-weight: 600;
                font-size: 8.5pt;
                letter-spacing: 0.3px;
            }
            QPushButton:hover {
                background-color: #272C22;
                border-color: #3E4537;
            }
            QPushButton:pressed {
                background-color: #151813;
            }
            QPushButton#PrimaryBtn {
                background-color: #9EF41A;
                border: 1px solid #9EF41A;
                color: #121411;
                font-weight: 700;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #B2F835;
                border-color: #B2F835;
            }
            QPushButton#PrimaryBtn:pressed {
                background-color: #85D60D;
            }
        """
        self.setStyleSheet(style.replace("__CHECK_ICON__", CHECK_ICON).replace("__RADIO_ICON__", RADIO_ICON))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Tactical Header with Logo №09
        top_box = QHBoxLayout()
        top_box.setSpacing(10)

        logo_lbl = QLabel()
        logo_lbl.setFixedSize(28, 28)
        logo_pix = QPixmap(str(ASSETS_DIR / "logo.png"))
        if not logo_pix.isNull():
            logo_lbl.setPixmap(logo_pix.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        top_box.addWidget(logo_lbl)

        title_lbl = QLabel("SYSTEM CONFIGURATION")
        title_lbl.setStyleSheet("font-size: 11pt; font-weight: 800; color: #E8EBE4; letter-spacing: 0.5px;")
        tag_lbl = QLabel("[ ENGINE // VP9-WEBM ]")
        tag_lbl.setStyleSheet("font-size: 8pt; font-family: monospace; color: #9EF41A;")
        top_box.addWidget(title_lbl)
        top_box.addStretch()
        top_box.addWidget(tag_lbl)
        main_layout.addLayout(top_box)

        # Scroll Area for settings
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #121411;
                width: 5px;
                margin: 0px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background-color: #2B3026;
                min-height: 25px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #9EF41A;
            }
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        v_content = QVBoxLayout(content)
        v_content.setContentsMargins(0, 0, 8, 0)
        v_content.setSpacing(14)

        # 1. Output folder group
        grp_folder = QGroupBox("EXPORT TARGET DIRECTORY")
        v_folder = QVBoxLayout(grp_folder)
        v_folder.setSpacing(8)

        self.btn_grp_folder = QButtonGroup(self)
        self.rb_first = QRadioButton("Source directory (save alongside input media)")
        self.rb_custom = QRadioButton("Custom static output directory")
        self.btn_grp_folder.addButton(self.rb_first)
        self.btn_grp_folder.addButton(self.rb_custom)

        if self.config.output_mode == "custom":
            self.rb_custom.setChecked(True)
        else:
            self.rb_first.setChecked(True)

        v_folder.addWidget(self.rb_first)
        v_folder.addWidget(self.rb_custom)

        row_path = QHBoxLayout()
        self.txt_folder = QLineEdit(self.config.custom_folder)
        self.txt_folder.setPlaceholderText("Select target directory...")
        row_path.addWidget(self.txt_folder, 1)

        btn_browse = QPushButton("BROWSE")
        btn_browse.setIcon(get_tactical_icon("folder-open", size=13))
        btn_browse.clicked.connect(self._browse_folder)
        row_path.addWidget(btn_browse)
        v_folder.addLayout(row_path)

        v_content.addWidget(grp_folder)

        # 2. Telegram Quality & Specs Group
        grp_quality = QGroupBox("TELEGRAM STICKER SPECIFICATIONS")
        v_quality = QVBoxLayout(grp_quality)
        v_quality.setSpacing(8)

        # Max Side (Slider + TacticalNumberEdit)
        lbl_side = QLabel("Dimension Ceiling:")
        row_side = QHBoxLayout()
        self.slider_side = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_side.setRange(128, 512)
        self.slider_side.setSingleStep(32)
        self.slider_side.setValue(self.config.max_side)
        self.num_side = TacticalNumberEdit(value=self.config.max_side, min_value=128, max_value=512, step=32, unit="px", even_only=True)
        self.num_side.setFixedWidth(80)
        self.slider_side.valueChanged.connect(lambda v: self.num_side.setValue(v))
        self.num_side.valueChanged.connect(lambda v: self.slider_side.setValue(int(v)))
        row_side.addWidget(self.slider_side, 1)
        row_side.addWidget(self.num_side)
        v_quality.addWidget(lbl_side)
        v_quality.addLayout(row_side)
        v_quality.addSpacing(6)

        # File Size Limit (Payload Weight Limit) (Slider + TacticalNumberEdit)
        lbl_size = QLabel("Payload Weight Limit:")
        row_size = QHBoxLayout()
        self.slider_size = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(64, 256)
        self.slider_size.setValue(self.config.max_size_kb)
        self.num_size = TacticalNumberEdit(value=self.config.max_size_kb, min_value=64, max_value=256, step=1, unit="KB")
        self.num_size.setFixedWidth(80)
        self.slider_size.valueChanged.connect(lambda v: self.num_size.setValue(v))
        self.num_size.valueChanged.connect(lambda v: self.slider_size.setValue(int(v)))
        row_size.addWidget(self.slider_size, 1)
        row_size.addWidget(self.num_size)
        v_quality.addWidget(lbl_size)
        v_quality.addLayout(row_size)
        v_quality.addSpacing(6)

        # FPS (Slider + TacticalNumberEdit)
        lbl_fps = QLabel("Temporal Rate:")
        row_fps = QHBoxLayout()
        self.slider_fps = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_fps.setRange(15, 60)
        self.slider_fps.setValue(self.config.fps)
        self.num_fps = TacticalNumberEdit(value=self.config.fps, min_value=15, max_value=60, step=1, unit="FPS")
        self.num_fps.setFixedWidth(80)
        self.slider_fps.valueChanged.connect(lambda v: self.num_fps.setValue(v))
        self.num_fps.valueChanged.connect(lambda v: self.slider_fps.setValue(int(v)))
        row_fps.addWidget(self.slider_fps, 1)
        row_fps.addWidget(self.num_fps)
        v_quality.addWidget(lbl_fps)
        v_quality.addLayout(row_fps)
        v_quality.addSpacing(8)

        # Micro-Sharpness Boost
        self.chk_unsharp = QCheckBox("Micro-Contrast Filter (Lanczos Resampling + Subtle Edge Acutance)")
        self.chk_unsharp.setChecked(self.config.enable_unsharp)
        self.chk_unsharp.setStyleSheet("QCheckBox { margin: 6px 0px 6px 0px; font-weight: 500; }")
        v_quality.addWidget(self.chk_unsharp)
        v_quality.addSpacing(8)

        # Multitasking Concurrency (Slider + TacticalNumberEdit)
        lbl_conc = QLabel("Parallel Worker Threads:")
        row_conc = QHBoxLayout()
        self.slider_conc = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_conc.setRange(1, 4)
        self.slider_conc.setValue(self.config.concurrency)
        self.num_conc = TacticalNumberEdit(value=self.config.concurrency, min_value=1, max_value=4, step=1)
        self.num_conc.setFixedWidth(80)
        self.slider_conc.valueChanged.connect(lambda v: self.num_conc.setValue(v))
        self.num_conc.valueChanged.connect(lambda v: self.slider_conc.setValue(int(v)))
        row_conc.addWidget(self.slider_conc, 1)
        row_conc.addWidget(self.num_conc)
        v_quality.addWidget(lbl_conc)
        v_quality.addLayout(row_conc)

        v_content.addWidget(grp_quality)

        # 3. Behavior Group
        grp_behavior = QGroupBox("RUNTIME & FEEDBACK PIPELINE")
        v_behav = QVBoxLayout(grp_behavior)
        v_behav.setSpacing(8)

        # Sound row with volume field opposite checkbox
        sound_row = QHBoxLayout()
        sound_row.setSpacing(10)

        self.chk_sound = QCheckBox("Acoustic Telemetry (play audio cue on completion)")
        self.chk_sound.setChecked(self.config.play_sound)
        sound_row.addWidget(self.chk_sound, 1)

        vol_box = QHBoxLayout()
        vol_box.setSpacing(6)
        lbl_v = QLabel("Level:")
        lbl_v.setStyleSheet("color: #92968C; font-family: monospace;")
        vol_box.addWidget(lbl_v)

        init_vol = 80
        vol_str = getattr(self.config, "sound_volume_str", "80%").replace("%", "").strip()
        try:
            init_vol = int(float(vol_str))
        except ValueError:
            init_vol = 80

        self.txt_volume = TacticalNumberEdit(value=init_vol, min_value=0, max_value=100, step=5, unit="%")
        self.txt_volume.setFixedWidth(70)
        vol_box.addWidget(self.txt_volume)
        sound_row.addLayout(vol_box)

        def on_sound_toggled(checked: bool):
            self.txt_volume.setEnabled(checked)
            lbl_v.setEnabled(checked)

        self.chk_sound.toggled.connect(on_sound_toggled)
        on_sound_toggled(self.chk_sound.isChecked())

        v_behav.addLayout(sound_row)

        self.chk_overwrite = QCheckBox("Permit automatic stream overwrite")
        self.chk_overwrite.setChecked(self.config.overwrite)
        v_behav.addWidget(self.chk_overwrite)

        self.chk_open = QCheckBox("Open directory upon batch completion")
        self.chk_open.setChecked(self.config.open_after)
        v_behav.addWidget(self.chk_open)

        v_content.addWidget(grp_behavior)
        v_content.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("CANCEL")
        btn_cancel.setIcon(get_tactical_icon("x", size=13))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("APPLY CONFIGURATION")
        btn_save.setIcon(get_tactical_icon("check", normal_color="#121411", active_color="#121411", size=13))
        btn_save.setObjectName("PrimaryBtn")
        btn_save.clicked.connect(self._save_and_close)
        btn_row.addWidget(btn_save)

        main_layout.addLayout(btn_row)

    def _browse_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Select Default Export Folder", self.txt_folder.text())
        if f:
            self.txt_folder.setText(f)
            self.rb_custom.setChecked(True)

    def _save_and_close(self):
        self.config.output_mode = "custom" if self.rb_custom.isChecked() else "first_file"
        self.config.custom_folder = self.txt_folder.text().strip()
        self.config.max_side = self.num_side.int_value()
        self.config.max_size_kb = self.num_size.int_value()
        self.config.fps = self.num_fps.int_value()
        self.config.enable_unsharp = self.chk_unsharp.isChecked()
        self.config.concurrency = self.num_conc.int_value()
        self.config.play_sound = self.chk_sound.isChecked()
        self.config.sound_volume_str = f"{self.txt_volume.int_value()}%"
        self.config.overwrite = self.chk_overwrite.isChecked()
        self.config.open_after = self.chk_open.isChecked()
        self.config.save()
        self.accept()
