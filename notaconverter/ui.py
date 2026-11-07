import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QPixmap, QImage, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QSplitter, QProgressBar, QMessageBox,
    QFrame, QDoubleSpinBox, QApplication
)

from .config import AppConfig, TELEGRAM_MAX_DURATION
from .media_probe import MediaProbe, MediaInfo, is_supported_file, ALL_SUPPORTED_EXTS
from .converter import CropRect, ItemSettings
from .task_queue import QueueManager, QueueItem, TaskStatus
from .widgets import (
    InteractiveCropWidget, TimelineRangeSlider, FileQueueList,
    MediaControlBar, get_tactical_icon, get_pixmap
)
from .settings_dialog import SettingsDialog
from .frame_cache import FrameCache, pil_to_qpixmap


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NotAconverter 1.2.0 — Telegram Sticker Studio")
        self.resize(1140, 780)
        self.setMinimumSize(880, 560)

        # Set window icon
        icon_path = Path(__file__).parent / "assets" / "app.ico"
        if not icon_path.exists():
            icon_path = Path("assets/app.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.config = AppConfig.load()
        self.queue_mgr = QueueManager(self.config)

        self.current_item: Optional[QueueItem] = None
        self.session_export_folder = ""

        # ── Frame cache: pre-extracts all preview frames ──
        self.frame_cache = FrameCache(self)
        self.frame_cache.frames_ready.connect(self._on_frames_ready)
        self.frame_cache.first_frame_ready.connect(self._on_first_frame_ready)

        # ── Playback timer: reads ONLY from cache, zero subprocess calls ──
        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(33)  # ~30 fps smooth playback
        self.playback_timer.timeout.connect(self._on_playback_step)
        self.is_playing = False

        # ── Scrub debounce: prevents flooding frame lookups during drag ──
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setSingleShot(True)
        self._scrub_timer.setInterval(16)  # ~60hz max refresh
        self._scrub_timer.timeout.connect(self._do_scrub_update)
        self._pending_scrub_time: float = 0.0

        # Install application-level event filter so Space ALWAYS toggles play/pause
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        self._setup_style()
        self._build_ui()
        self._connect_signals()
        self._check_dependencies()

    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0F120E;
            }
            QWidget {
                color: #FFFFFF;
                selection-background-color: #2D441B;
                selection-color: #FFFFFF;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            }
            QLabel {
                border: none;
                background: transparent;
            }
            QSplitter::handle {
                background-color: #222A1E;
                width: 1px;
            }
            QPushButton {
                background-color: #161A13;
                color: #E8ECE4;
                border: 1px solid #273321;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 8.5pt;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1F261B;
                border-color: #3C4E33;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #10140E;
                border-color: #A6FF00;
            }
            QPushButton:disabled {
                background-color: #131710;
                border-color: #1F261A;
                color: #485441;
            }
            QPushButton#PrimaryBtn {
                background-color: #A6FF00;
                border: 1px solid #A6FF00;
                color: #0F120E;
                font-size: 9.5pt;
                font-weight: 800;
                padding: 9px 20px;
                border-radius: 4px;
                letter-spacing: 0.3px;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #B5FF24;
                border-color: #B5FF24;
            }
            QPushButton#PrimaryBtn:disabled {
                background-color: #161A13;
                border-color: #273321;
                color: #485441;
            }
            QPushButton#StopBtn {
                background-color: #FF4444;
                border: 1px solid #FF4444;
                color: #FFFFFF;
                font-size: 9.5pt;
                font-weight: 700;
                padding: 9px 20px;
                border-radius: 4px;
            }
            QPushButton#StopBtn:hover {
                background-color: #FF6666;
                border-color: #FF6666;
            }
            QPushButton#ActivePreset {
                background-color: #18260F;
                border: 1px solid #A6FF00;
                color: #A6FF00;
            }
            QDoubleSpinBox {
                background-color: #121610;
                border: 1px solid #273321;
                border-radius: 4px;
                color: #FFFFFF;
                padding: 3px 6px;
                font-size: 8.5pt;
                font-family: "Consolas", monospace;
                selection-background-color: #2D441B;
                selection-color: #FFFFFF;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                width: 14px;
                background-color: #182015;
                border: 1px solid #273321;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #0F120E;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #242E1F;
                min-height: 25px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #3B4B32;
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #A6FF00;
            }
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                height: 0px;
                width: 0px;
            }
        """)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # 1. Header Row: Logo №09 + App Title & Subtitle + Settings
        header = QHBoxLayout()
        header.setSpacing(12)

        # Crisp Vector Logo №09 (Quantum Chevron)
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(32, 32)
        logo_path = Path(__file__).parent / "assets" / "logo.png"
        if not logo_path.exists():
            logo_path = Path("assets/logo.png")
        if logo_path.exists():
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                logo_lbl.setPixmap(pm.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(logo_lbl)

        title_box = QHBoxLayout()
        title_box.setSpacing(8)
        title_box.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        app_title = QLabel("NotAconverter")
        app_title.setStyleSheet("font-size: 13pt; font-weight: 800; letter-spacing: 0.5px; color: #E8EBE4;")

        self.lbl_version_badge = QLabel("1.2.0")
        self.lbl_version_badge.setFixedHeight(18)
        self.lbl_version_badge.setStyleSheet("""
            background-color: #14220A;
            color: #A6FF00;
            border: 1px solid #284414;
            border-radius: 3px;
            padding: 1px 6px;
            font-size: 7.5pt;
            font-weight: 700;
            font-family: 'Consolas', monospace;
        """)

        title_box.addWidget(app_title)
        title_box.addWidget(self.lbl_version_badge)
        header.addLayout(title_box)

        header.addStretch()

        self.dep_warning = QLabel("")
        self.dep_warning.setStyleSheet("color: #FF4D4D; font-weight: bold; font-size: 8.5pt;")
        header.addWidget(self.dep_warning)

        self.btn_settings = QPushButton("SETTINGS")
        self.btn_settings.setIcon(get_tactical_icon("settings", size=13))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)
        header.addWidget(self.btn_settings)

        main_layout.addLayout(header)

        # 2. Main Horizontal Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # --- Left Panel: Queue & File Management ---
        left_panel = QFrame()
        left_panel.setObjectName("LeftPanel")
        left_panel.setStyleSheet("QFrame#LeftPanel { background-color: #121411; border: 1px solid #1E231B; border-radius: 6px; }")
        v_left = QVBoxLayout(left_panel)
        v_left.setContentsMargins(12, 12, 12, 12)
        v_left.setSpacing(10)

        # Queue Header
        q_head = QHBoxLayout()
        q_title = QLabel("FILE QUEUE")
        q_title.setStyleSheet("font-size: 9.5pt; font-weight: 700; color: #E8EBE4; letter-spacing: 0.5px;")
        self.lbl_queue_count = QLabel("0")
        self.lbl_queue_count.setStyleSheet("""
            background-color: transparent;
            color: #9EF41A;
            font-size: 8.5pt;
            font-weight: 700;
            font-family: 'Consolas', monospace;
            padding: 0px 4px;
            border: none;
        """)
        q_head.addWidget(q_title)
        q_head.addWidget(self.lbl_queue_count)
        q_head.addStretch()

        self.btn_clear = QPushButton("CLEAR")
        self.btn_clear.setIcon(get_tactical_icon("trash", size=13))
        self.btn_clear.clicked.connect(self._clear_queue)
        q_head.addWidget(self.btn_clear)
        v_left.addLayout(q_head)

        # Queue List
        self.queue_list = FileQueueList()
        v_left.addWidget(self.queue_list, 1)

        # Queue Action Buttons
        btn_box = QHBoxLayout()
        self.btn_add_files = QPushButton("ADD FILES")
        self.btn_add_files.setIcon(get_tactical_icon("file-plus", size=14))
        self.btn_add_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_files.clicked.connect(self._select_files)

        self.btn_add_folder = QPushButton("FOLDER")
        self.btn_add_folder.setIcon(get_tactical_icon("folder-plus", size=14))
        self.btn_add_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_folder.clicked.connect(self._select_folder)

        btn_box.addWidget(self.btn_add_files)
        btn_box.addWidget(self.btn_add_folder)
        v_left.addLayout(btn_box)

        # Export Directory Bar
        dest_box = QVBoxLayout()
        dest_box.setSpacing(4)
        lbl_dest = QLabel("EXPORT DIRECTORY")
        lbl_dest.setStyleSheet("color: #92968C; font-size: 8pt; font-weight: 600; font-family: 'Consolas', monospace;")

        dest_row = QHBoxLayout()
        dest_row.setContentsMargins(0, 0, 0, 0)
        dest_row.setSpacing(6)

        self.lbl_dest_path = QLabel()
        self.lbl_dest_path.setFixedHeight(28)
        self.lbl_dest_path.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.lbl_dest_path.setStyleSheet("""
            QLabel {
                background-color: #0E100D;
                border: 1px solid #1E231B;
                border-radius: 4px;
                padding: 0px 8px;
                color: #E8EBE4;
                font-size: 8pt;
                font-family: 'Consolas', monospace;
            }
        """)

        self.btn_change_dest = QPushButton()
        self.btn_change_dest.setFixedSize(28, 28)
        self.btn_change_dest.setIcon(get_tactical_icon("folder-edit", size=14))
        self.btn_change_dest.setToolTip("Change export destination folder")
        self.btn_change_dest.clicked.connect(self._change_export_folder)

        self.btn_open_folder = QPushButton()
        self.btn_open_folder.setFixedSize(28, 28)
        self.btn_open_folder.setIcon(get_tactical_icon("folder-open", size=14))
        self.btn_open_folder.setToolTip("Open export folder in explorer")
        self.btn_open_folder.clicked.connect(self._open_export_folder)

        dest_row.addWidget(self.lbl_dest_path, 1)
        dest_row.addWidget(self.btn_change_dest)
        dest_row.addWidget(self.btn_open_folder)

        dest_box.addWidget(lbl_dest)
        dest_box.addLayout(dest_row)
        v_left.addLayout(dest_box)

        splitter.addWidget(left_panel)

        # --- Right Panel: Interactive Visual Crop & Trim Editor ---
        right_panel = QFrame()
        right_panel.setObjectName("RightPanel")
        right_panel.setStyleSheet("QFrame#RightPanel { background-color: #121411; border: 1px solid #1E231B; border-radius: 6px; }")
        v_right = QVBoxLayout(right_panel)
        v_right.setContentsMargins(14, 14, 14, 14)
        v_right.setSpacing(10)

        # Editor Header
        ed_head = QHBoxLayout()
        ed_head.setContentsMargins(0, 0, 0, 0)
        ed_head.setSpacing(10)

        self.lbl_item_name = QLabel("No media selected")
        self.lbl_item_name.setStyleSheet("font-size: 9.5pt; font-weight: 700; color: #8D9387;")

        ed_head.addWidget(self.lbl_item_name)
        ed_head.addStretch()

        # Clean segmented mode toggle [ Preview | Crop ]
        mode_box = QHBoxLayout()
        mode_box.setSpacing(2)

        self.btn_mode_preview = QPushButton("Preview")
        self.btn_mode_preview.setIcon(get_tactical_icon("maximize-2", size=12))
        self.btn_mode_preview.setFixedHeight(26)
        self.btn_mode_preview.clicked.connect(lambda: self._set_view_mode("preview"))

        self.btn_mode_crop = QPushButton("Crop")
        self.btn_mode_crop.setIcon(get_tactical_icon("crop", size=12))
        self.btn_mode_crop.setFixedHeight(26)
        self.btn_mode_crop.clicked.connect(lambda: self._set_view_mode("crop"))

        mode_box.addWidget(self.btn_mode_preview)
        mode_box.addWidget(self.btn_mode_crop)
        ed_head.addLayout(mode_box)

        v_right.addLayout(ed_head)

        # Crop Canvas Viewport
        self.crop_widget = InteractiveCropWidget()
        v_right.addWidget(self.crop_widget, 1)

        # Trimming & Parameter Control Section (Media Control Bar + Timeline Slider)
        self.trim_container = QWidget()
        v_trim = QVBoxLayout(self.trim_container)
        v_trim.setContentsMargins(0, 2, 0, 0)
        v_trim.setSpacing(6)

        # Compact Settings Bar directly ABOVE timeline
        self.media_bar = MediaControlBar(self)
        v_trim.addWidget(self.media_bar)

        # Interactive Timeline Range Slider
        self.timeline_slider = TimelineRangeSlider(self)
        v_trim.addWidget(self.timeline_slider)

        v_right.addWidget(self.trim_container)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

        main_layout.addWidget(splitter, 1)

        # 3. Footer Bar: Global Progress & Export Action
        footer = QHBoxLayout()
        footer.setSpacing(14)

        status_box = QVBoxLayout()
        status_box.setSpacing(4)
        self.lbl_global_status = QLabel("IDLE // AWAITING MEDIA INPUT")
        self.lbl_global_status.setStyleSheet("color: #92968C; font-size: 8.5pt; font-family: 'Consolas', monospace;")

        self.global_progress = QProgressBar()
        self.global_progress.setFixedHeight(4)
        self.global_progress.setTextVisible(False)
        self.global_progress.setStyleSheet("""
            QProgressBar {
                background-color: #121411;
                border: 1px solid #2B3026;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #9EF41A;
                border-radius: 2px;
            }
        """)
        self.global_progress.setValue(0)

        status_box.addWidget(self.lbl_global_status)
        status_box.addWidget(self.global_progress)
        footer.addLayout(status_box, 1)

        self.btn_export = QPushButton("EXPORT STICKERS")
        self.btn_export.setIcon(get_tactical_icon("download", normal_color="#121411", active_color="#121411", size=15))
        self.btn_export.setObjectName("PrimaryBtn")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._on_export_clicked)
        footer.addWidget(self.btn_export)

        main_layout.addLayout(footer)

        # Ensure no buttons ever steal focus from Space play/pause
        for btn in self.findChildren(QPushButton):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._update_export_destination_label()
        self._update_mode_buttons()
        self._update_ui_state()

    def _set_view_mode(self, mode: str):
        self.crop_widget.set_view_mode(mode)
        self._update_mode_buttons()

    def _on_crop_view_mode_changed(self, mode: str):
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        is_prev = (self.crop_widget.view_mode == "preview")
        active_style = """
            QPushButton {
                background-color: #17240E;
                color: #A6FF00;
                border: 1px solid #A6FF00;
                border-radius: 3px;
                padding: 3px 10px;
                font-weight: 700;
                font-size: 8.5pt;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #141811;
                color: #929E8A;
                border: 1px solid #273321;
                border-radius: 3px;
                padding: 3px 10px;
                font-weight: 500;
                font-size: 8.5pt;
            }
            QPushButton:hover {
                background-color: #1D2419;
                color: #FFFFFF;
                border-color: #3C4E33;
            }
        """
        self.btn_mode_preview.setStyleSheet(active_style if is_prev else inactive_style)
        self.btn_mode_crop.setStyleSheet(inactive_style if is_prev else active_style)

    def _connect_signals(self):
        self.queue_list.item_selected.connect(self._on_item_selected)
        self.queue_list.item_removed.connect(self._on_item_removed)
        self.queue_list.files_dropped.connect(self._add_file_paths)
        self.queue_list.empty_clicked.connect(self._select_files)

        self.queue_mgr.item_added.connect(self._on_queue_item_added)
        self.queue_mgr.item_updated.connect(self._on_queue_item_updated)
        self.queue_mgr.item_finished.connect(self._on_item_finished)
        self.queue_mgr.all_finished.connect(self._on_all_finished)

        self.crop_widget.crop_changed.connect(self._on_crop_changed)
        self.crop_widget.view_mode_changed.connect(self._on_crop_view_mode_changed)
        self.timeline_slider.interaction_started.connect(self._stop_playback)
        self.timeline_slider.range_changed.connect(self._on_trim_range_changed)
        self.timeline_slider.playhead_changed.connect(self._on_playhead_changed)

        self.media_bar.play_toggled.connect(self._toggle_playback)
        self.media_bar.trim_updated.connect(self._on_control_bar_trim_changed)
        self.media_bar.speed_updated.connect(self._on_speed_changed)
        self.media_bar.fps_updated.connect(self._on_fps_changed)
        self.media_bar.resolution_updated.connect(self._on_resolution_changed)
        self.media_bar.fit_3s_requested.connect(self.timeline_slider.fit_to_three_seconds)
        self.media_bar.crop_preset_requested.connect(self._set_aspect_preset)
        self.media_bar.reset_crop_requested.connect(self._reset_crop)

    def _check_dependencies(self):
        missing = []
        if not shutil.which("ffmpeg"):
            missing.append("FFmpeg")
        if not shutil.which("ffprobe"):
            missing.append("FFprobe")
        if missing:
            self.dep_warning.setText(f"⚠ Missing dependencies: {', '.join(missing)}!")
            self.btn_export.setEnabled(False)

    # ════════════════════════════════════════════════════════
    #  Queue & File Selection
    # ════════════════════════════════════════════════════════
    def _select_files(self):
        ext_filter = "All Media (*.mp4 *.mov *.webm *.mkv *.avi *.gif *.png *.jpg *.jpeg *.webp);;Videos (*.mp4 *.mov *.webm *.mkv *.avi);;Images (*.png *.jpg *.jpeg *.webp *.gif);;All Files (*.*)"
        files, _ = QFileDialog.getOpenFileNames(self, "Select Media Files", "", ext_filter)
        if files:
            self._add_file_paths(files)

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder with Media")
        if folder:
            paths = []
            for root, _, files in os.walk(folder):
                for f in files:
                    full = os.path.join(root, f)
                    if is_supported_file(full):
                        paths.append(full)
            if paths:
                self._add_file_paths(paths)

    def _add_file_paths(self, paths: List[str]):
        added = 0
        failed = []
        for p in paths:
            if is_supported_file(p):
                item = self.queue_mgr.add_file(p)
                if item:
                    added += 1
                else:
                    failed.append(Path(p).name)
            else:
                failed.append(Path(p).name)
        if added > 0:
            self.lbl_queue_count.setText(str(len(self.queue_mgr.items)))
            self._update_export_destination_label()
            self._update_ui_state()
        if failed:
            self.lbl_global_status.setText(
                f"⚠ Skipped {len(failed)} unsupported or unreadable file(s): {', '.join(failed[:2])}"
                + (f" +{len(failed) - 2} more" if len(failed) > 2 else "")
            )

    def _clear_queue(self):
        self._stop_playback()
        self.frame_cache.clear()
        self.queue_mgr.clear()
        self.queue_list.clear_all()
        self.current_item = None
        self.lbl_queue_count.setText("0")
        self.crop_widget.set_image(None, 1, 1)
        self.lbl_item_name.setText("No media selected")
        self.lbl_item_name.setStyleSheet("font-size: 9.5pt; font-weight: 700; color: #8D9387;")
        self._update_export_destination_label()
        self._update_ui_state()

    def _on_queue_item_added(self, item: QueueItem):
        self.queue_list.add_queue_item(item)
        self.lbl_queue_count.setText(str(len(self.queue_mgr.items)))

    def _on_queue_item_updated(self, item: QueueItem):
        self.queue_list.update_item(item)
        self._update_global_progress()

    def _on_item_removed(self, task_id: str):
        if self.current_item and self.current_item.id == task_id:
            self._stop_playback()
            self.frame_cache.clear()
            self.current_item = None
            self.crop_widget.set_image(None, 1, 1)
            self.lbl_item_name.setText("No media selected")
        self.lbl_item_name.setStyleSheet("font-size: 9.5pt; font-weight: 700; color: #8D9387;")
        self.queue_mgr.remove_item(task_id)
        self.queue_list.remove_queue_item(task_id)
        self.lbl_queue_count.setText(str(len(self.queue_mgr.items)))
        self._update_export_destination_label()
        self._update_ui_state()

    def _on_item_selected(self, task_id: str):
        item = self.queue_mgr.items.get(task_id)
        if not item:
            return

        self._stop_playback()
        self.current_item = item

        # Immediately clear old media from viewer so photo never leaks into video
        self.crop_widget.set_image(None, item.info.width, item.info.height)

        self.lbl_item_name.setText(item.info.filename)
        self.lbl_item_name.setStyleSheet("font-size: 9.5pt; font-weight: 700; color: #E8EBE4;")

        # Show / hide timeline controls for static images
        is_dynamic = item.info.is_video or item.info.is_animated
        self.timeline_slider.setVisible(is_dynamic)
        self.media_bar.btn_play.setVisible(is_dynamic)
        self.media_bar.btn_trim.setVisible(is_dynamic)
        self.media_bar.btn_speed.setVisible(is_dynamic)
        self.media_bar.btn_fps.setVisible(is_dynamic)
        self.trim_container.setVisible(True)

        spd = getattr(item.settings, "speed", 1.0)
        source_dur = item.info.duration if item.info.duration > 0 else 3.0
        effective_dur = source_dur / max(0.1, spd)

        src_start = max(0.0, item.settings.trim_start)
        src_end = item.settings.trim_end if item.settings.trim_end > src_start else min(source_dur, src_start + 3.0 * spd)
        start_out = src_start / max(0.1, spd)
        end_out = src_end / max(0.1, spd)

        # Configure timeline
        if is_dynamic:
            self.timeline_slider.set_speed(spd)
            self.timeline_slider.set_duration(effective_dur, default_clamp_3s=False)
            self.timeline_slider.set_range(start_out, end_out)
            self.media_bar.update_trim_display(start_out, end_out, effective_dur, source_dur=src_end - src_start)
        else:
            self.media_bar.update_trim_display(0.0, 1.0, 1.0, source_dur=1.0)

        self.media_bar.update_speed_display(spd)
        self.media_bar.update_fps_display(getattr(item.settings, "fps", 0))

        # ── Kick off frame cache loading ──
        # GIF/WEBP: synchronous PIL decode (~instant)
        # Video: background ffmpeg extraction (UI stays responsive)
        self.lbl_global_status.setText(f"Loading preview for {item.info.filename}...")
        self.frame_cache.load(
            path=item.info.path,
            duration=source_dur,
            orig_w=item.info.width,
            orig_h=item.info.height,
            is_animated_image=item.info.is_animated and not item.info.is_video,
        )

        # For GIF/images the frames are already ready (sync load),
        # so show the first frame immediately:
        self._show_cached_frame(src_start)

        # Restore crop
        self.crop_widget.set_crop_rect(item.settings.crop)
        self._update_target_dimensions_display()

    # ════════════════════════════════════════════════════════
    #  Frame Preview & Playback  (ALL from cache, zero ffmpeg)
    # ════════════════════════════════════════════════════════

    def _on_first_frame_ready(self, qimg: QImage, timestamp: float):
        """Immediately displays frame 0 of video without waiting for full 90-frame batch."""
        if self.current_item and (self.current_item.info.is_video or self.current_item.info.is_animated):
            pm = QPixmap.fromImage(qimg)
            self.crop_widget.set_image(pm, self.current_item.info.width, self.current_item.info.height)
            self._update_target_dimensions_display()

    def _on_frames_ready(self):
        """Called when background video frame extraction finishes."""
        self.lbl_global_status.setText(
            f"Preview ready ({self.frame_cache.frame_count} frames cached)"
        )
        if self.current_item:
            spd = getattr(self.current_item.settings, "speed", 1.0)
            self._show_cached_frame(self.timeline_slider.current_time * spd)

    def _show_cached_frame(self, timestamp: float):
        """Display a frame from the cache in the crop widget. Instant lookup using source timestamp."""
        if not self.current_item:
            return
        pix = self.frame_cache.get_frame_at(timestamp)
        if pix and not pix.isNull():
            self.crop_widget.set_image(
                pix,
                self.current_item.info.width,
                self.current_item.info.height
            )
        self._update_target_dimensions_display()

    def _toggle_playback(self):
        if self.is_playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        if not self.current_item:
            return
        if not (self.current_item.info.is_video or self.current_item.info.is_animated):
            return
        if self.frame_cache.frame_count == 0:
            return  # frames not ready yet
        self.is_playing = True
        self.media_bar.set_playing_state(True)
        self.playback_timer.start()

    def _stop_playback(self):
        self.is_playing = False
        self.playback_timer.stop()
        self.media_bar.set_playing_state(False)

    def _on_playback_step(self):
        """Advance playhead in output time and show corresponding source frame."""
        if not self.current_item or self.frame_cache.frame_count == 0:
            self._stop_playback()
            return

        spd = getattr(self.current_item.settings, "speed", 1.0) if self.current_item else 1.0
        # Playhead advances by real elapsed time dt in output coordinates
        dt = self.playback_timer.interval() / 1000.0
        new_t = self.timeline_slider.current_time + dt
        if new_t > self.timeline_slider.end_time:
            new_t = self.timeline_slider.start_time

        self.timeline_slider.current_time = new_t
        self.timeline_slider.update()
        # Retrieve frame from cache using source time: t_src = t_out * spd
        self._show_cached_frame(new_t * spd)

    # ════════════════════════════════════════════════════════
    #  Cropping & Trimming Handlers
    # ════════════════════════════════════════════════════════

    def _set_aspect_preset(self, ratio: Optional[float]):
        self.crop_widget.set_aspect_ratio(ratio)
        self._update_target_dimensions_display()

    def _reset_crop(self):
        self.crop_widget.reset_crop()
        self._update_target_dimensions_display()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QLineEdit, QTextEdit, QAbstractSpinBox
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space:
            focus_w = self.focusWidget()
            # If user is in a text input or spinbox, let space type space
            if isinstance(focus_w, (QLineEdit, QTextEdit, QAbstractSpinBox)):
                return super().eventFilter(obj, event)
            # Otherwise, space exclusively toggles video/gif playback and NEVER clicks buttons
            self._toggle_playback()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            focus_w = self.focusWidget()
            from PyQt6.QtWidgets import QLineEdit, QTextEdit, QAbstractSpinBox
            if isinstance(focus_w, (QLineEdit, QTextEdit, QAbstractSpinBox)):
                super().keyPressEvent(event)
                return
            self._toggle_playback()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_crop_changed(self, crop: CropRect):
        if self.current_item:
            self.current_item.settings.crop = crop
            if self.current_item.status == TaskStatus.SUCCESS:
                self.current_item.status = TaskStatus.QUEUED
                self.current_item.status_text = "Ready"
                self.queue_list.update_item(self.current_item)
            self._update_target_dimensions_display()

    def _on_trim_range_changed(self, start_out: float, end_out: float):
        if self.current_item:
            spd = getattr(self.current_item.settings, "speed", 1.0)
            src_start = start_out * spd
            src_end = end_out * spd
            self.current_item.settings.trim_start = src_start
            self.current_item.settings.trim_end = src_end
            if self.current_item.status == TaskStatus.SUCCESS:
                self.current_item.status = TaskStatus.QUEUED
                self.current_item.status_text = "Ready"
                self.queue_list.update_item(self.current_item)
            effective_dur = self.timeline_slider.total_duration
            self.media_bar.update_trim_display(start_out, end_out, effective_dur, source_dur=src_end - src_start)

    def _on_control_bar_trim_changed(self, start_out: float, end_out: float):
        if self.current_item:
            spd = getattr(self.current_item.settings, "speed", 1.0)
            src_start = start_out * spd
            src_end = end_out * spd
            self.current_item.settings.trim_start = src_start
            self.current_item.settings.trim_end = src_end
            if self.current_item.status == TaskStatus.SUCCESS:
                self.current_item.status = TaskStatus.QUEUED
                self.current_item.status_text = "Ready"
                self.queue_list.update_item(self.current_item)
            self.timeline_slider.set_range(start_out, end_out)
            self._show_cached_frame(src_start)

    def _on_speed_changed(self, speed: float):
        if not self.current_item:
            return
        self.current_item.settings.speed = speed
        if self.current_item.status == TaskStatus.SUCCESS:
            self.current_item.status = TaskStatus.QUEUED
            self.current_item.status_text = "Ready"
            self.queue_list.update_item(self.current_item)

        source_dur = self.current_item.info.duration if self.current_item.info.duration > 0 else 3.0
        new_effective_total = source_dur / max(0.1, speed)

        # Preserve the current desired output duration (e.g. 3.0s), clamped to new total
        curr_out_dur = self.timeline_slider.selected_duration
        if curr_out_dur <= 0.05:
            curr_out_dur = min(new_effective_total, 3.0)
        out_dur = min(curr_out_dur, new_effective_total)

        start_out = self.timeline_slider.start_time
        if start_out + out_dur > new_effective_total:
            start_out = max(0.0, new_effective_total - out_dur)
        end_out = min(new_effective_total, start_out + out_dur)

        self.timeline_slider.set_speed(speed)
        self.timeline_slider.set_duration(new_effective_total, default_clamp_3s=False)
        self.timeline_slider.set_range(start_out, end_out)

        src_start = start_out * speed
        src_end = end_out * speed
        self.current_item.settings.trim_start = src_start
        self.current_item.settings.trim_end = src_end

        self.media_bar.update_speed_display(speed)
        self.media_bar.update_trim_display(start_out, end_out, new_effective_total, source_dur=src_end - src_start)

        self._show_cached_frame(src_start)

    def _on_fps_changed(self, fps: int):
        if self.current_item:
            self.current_item.settings.fps = fps
            if self.current_item.status == TaskStatus.SUCCESS:
                self.current_item.status = TaskStatus.QUEUED
                self.current_item.status_text = "Ready"
                self.queue_list.update_item(self.current_item)

    def _on_resolution_changed(self, w: int, h: int, locked: bool):
        if self.current_item:
            self.current_item.settings.custom_width = w
            self.current_item.settings.custom_height = h
            self.current_item.settings.lock_aspect_ratio = locked
            if self.current_item.status == TaskStatus.SUCCESS:
                self.current_item.status = TaskStatus.QUEUED
                self.current_item.status_text = "Ready"
                self.queue_list.update_item(self.current_item)
            self.crop_widget.set_target_dimensions(w, h, locked)
            self._update_target_dimensions_display()

    def _on_playhead_changed(self, current_time: float):
        """Debounced scrub: current_time is in output seconds."""
        spd = getattr(self.current_item.settings, "speed", 1.0) if self.current_item else 1.0
        self._pending_scrub_time = current_time * spd
        if not self._scrub_timer.isActive():
            self._scrub_timer.start()

    def _do_scrub_update(self):
        """Perform the actual frame display for the latest scrub position in source time."""
        self._show_cached_frame(self._pending_scrub_time)

    def _update_target_dimensions_display(self):
        if not self.current_item:
            return
        info = self.current_item.info
        crop = self.current_item.settings.crop
        from .converter import StickerConverter
        calc = StickerConverter(self.config)
        w, h = calc.calculate_target_dims(
            info.width, info.height, crop,
            self.current_item.settings.custom_width,
            self.current_item.settings.custom_height
        )
        locked = getattr(self.current_item.settings, "lock_aspect_ratio", True)
        ref_aspect = info.width / max(1, info.height)
        if crop and crop.is_valid:
            ref_aspect = crop.width / max(1, crop.height)

        self.crop_widget.set_target_dimensions(w, h, locked)
        self.media_bar.update_resolution_display(w, h, locked, ref_aspect)

    # ════════════════════════════════════════════════════════
    #  Export & Destinations
    # ════════════════════════════════════════════════════════

    def _current_export_folder(self) -> str:
        if self.session_export_folder:
            return self.session_export_folder
        if self.config.output_mode == "custom" and self.config.custom_folder:
            return self.config.custom_folder
        if self.queue_mgr.items:
            first = next(iter(self.queue_mgr.items.values()))
            return str(Path(first.info.path).parent)
        return ""

    def _update_export_destination_label(self):
        folder = self._current_export_folder()
        if folder:
            self.lbl_dest_path.clear()
            self.lbl_dest_path.setText(folder)
            self.lbl_dest_path.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.lbl_dest_path.setStyleSheet("""
                QLabel {
                    background-color: #0E100D;
                    border: 1px solid #1E231B;
                    border-radius: 4px;
                    padding: 0px 8px;
                    color: #E8EBE4;
                    font-size: 8pt;
                    font-family: 'Consolas', monospace;
                }
            """)
            self.lbl_dest_path.setToolTip(folder)
            self.btn_open_folder.setEnabled(os.path.isdir(folder))
        else:
            self.lbl_dest_path.clear()
            self.lbl_dest_path.setPixmap(get_pixmap("ban", color="#555B4F", size=14))
            self.lbl_dest_path.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_dest_path.setStyleSheet("""
                QLabel {
                    background-color: #0E100D;
                    border: 1px solid #1E231B;
                    border-radius: 4px;
                    padding: 0px 8px;
                }
            """)
            self.lbl_dest_path.setToolTip("Папка экспорта не выбрана (по умолчанию сохранится рядом с исходником)")
            self.btn_open_folder.setEnabled(False)

    def _change_export_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Export Folder for this Session")
        if folder:
            self.session_export_folder = folder
            self._update_export_destination_label()

    def _open_export_folder(self):
        folder = self._current_export_folder()
        if folder and os.path.isdir(folder):
            try:
                os.startfile(folder)
            except Exception:
                subprocess.Popen(["explorer", folder])
        else:
            QMessageBox.information(self, "Export Folder", "Output folder is not set or does not exist yet.")

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self._update_export_destination_label()
            self._update_target_dimensions_display()

    # ════════════════════════════════════════════════════════
    #  Conversion Execution
    # ════════════════════════════════════════════════════════

    def _on_export_clicked(self):
        if self.queue_mgr.is_running:
            self.queue_mgr.cancel_all()
            self.btn_export.setText("EXPORT STICKERS")
            self.btn_export.setIcon(get_tactical_icon("download", normal_color="#121411", active_color="#121411", size=15))
            self.btn_export.setObjectName("PrimaryBtn")
            self.btn_export.setStyle(self.btn_export.style())
            self.lbl_global_status.setText("STATUS: OPERATION ABORTED BY USER")
            return

        if not self.queue_mgr.items:
            QMessageBox.warning(self, "No Files", "Please add at least one video, GIF, or image.")
            return

        export_dir = self._current_export_folder()
        if not export_dir:
            QMessageBox.warning(self, "No Destination", "Please specify an export destination folder.")
            return

        self._stop_playback()
        self.btn_export.setText("CANCEL EXPORT")
        self.btn_export.setIcon(get_tactical_icon("square-stop", normal_color="#121411", active_color="#121411", size=15))
        self.btn_export.setObjectName("StopBtn")
        self.btn_export.setStyle(self.btn_export.style())
        self.lbl_global_status.setText(f"PROCESSING // ENCODING {len(self.queue_mgr.items)} ITEM(S) WITH VP9...")

        self.queue_mgr.start_processing(export_dir)

    def _update_global_progress(self):
        items = list(self.queue_mgr.items.values())
        if not items:
            self.global_progress.setValue(0)
            return

        total_prog = sum(item.progress for item in items)
        avg = total_prog / len(items)
        self.global_progress.setValue(int(avg))

    def _on_item_finished(self, item: QueueItem):
        pass

    def _on_all_finished(self):
        self.btn_export.setText("EXPORT STICKERS")
        self.btn_export.setIcon(get_tactical_icon("download", normal_color="#121411", active_color="#121411", size=15))
        self.btn_export.setObjectName("PrimaryBtn")
        self.btn_export.setStyle(self.btn_export.style())

        items = list(self.queue_mgr.items.values())
        successful = sum(1 for item in items if item.status == TaskStatus.SUCCESS)
        errors = sum(1 for item in items if item.status == TaskStatus.ERROR)

        if errors == 0 and successful > 0:
            self.lbl_global_status.setText(f"COMPLETED // {successful} STICKER(S) EXPORTED SUCCESSFULLY")
            self.global_progress.setValue(100)
            if self.config.play_sound:
                from .sound import play_completion_sound, parse_volume
                vol = parse_volume(self.config.sound_volume_str, 0.8)
                play_completion_sound(volume=vol)
            if self.config.open_after:
                self._open_export_folder()
        else:
            self.lbl_global_status.setText(f"STATUS // {successful} SUCCEEDED, {errors} FAILED")

    def _update_ui_state(self):
        has_items = bool(self.queue_mgr.items)
        self.btn_export.setEnabled(has_items)
        self.btn_clear.setEnabled(has_items)

    def closeEvent(self, event):
        self._stop_playback()
        self.frame_cache.cancel()
        self.queue_mgr.cancel_all()
        self.config.save()
        super().closeEvent(event)
