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
from .widgets import InteractiveCropWidget, TimelineRangeSlider, FileQueueList
from .settings_dialog import SettingsDialog
from .frame_cache import FrameCache, pil_to_qpixmap


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NotAconverter 1.1.1 — Telegram Sticker Studio")
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
                background-color: #121411;
            }
            QWidget {
                color: #E8EBE4;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            }
            QSplitter::handle {
                background-color: #2B3026;
                width: 1px;
            }
            QPushButton {
                background-color: #1E211B;
                color: #E8EBE4;
                border: 1px solid #2B3026;
                border-radius: 3px;
                padding: 6px 14px;
                font-size: 8.5pt;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #262B21;
                border-color: #3E4636;
            }
            QPushButton:pressed {
                background-color: #151813;
                border-color: #9EF41A;
            }
            QPushButton#PrimaryBtn {
                background-color: #9EF41A;
                border: 1px solid #9EF41A;
                color: #121411;
                font-size: 9.5pt;
                font-weight: 700;
                padding: 9px 20px;
                border-radius: 3px;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #ACF738;
                border-color: #ACF738;
            }
            QPushButton#PrimaryBtn:disabled {
                background-color: #181B16;
                border-color: #2B3026;
                color: #4D5247;
            }
            QPushButton#StopBtn {
                background-color: #FF4D4D;
                border: 1px solid #FF4D4D;
                color: #121411;
                font-size: 9.5pt;
                font-weight: 700;
                padding: 9px 20px;
                border-radius: 3px;
            }
            QPushButton#StopBtn:hover {
                background-color: #FF6666;
                border-color: #FF6666;
            }
            QPushButton#ActivePreset {
                background-color: #232B1C;
                border: 1px solid #9EF41A;
                color: #9EF41A;
            }
            QDoubleSpinBox {
                background-color: #181B16;
                border: 1px solid #2B3026;
                border-radius: 3px;
                color: #E8EBE4;
                padding: 3px 6px;
                font-size: 8.5pt;
                font-family: "Consolas", monospace;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                width: 14px;
                background-color: #1E211B;
                border: 1px solid #2B3026;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #121411;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #262B21;
                min-height: 25px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #363D2E;
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #9EF41A;
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

        # 1. Header Row
        header = QHBoxLayout()
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        app_title = QLabel("NOTACONVERTER")
        app_title.setStyleSheet("font-size: 14pt; font-weight: 800; letter-spacing: 1px; color: #E8EBE4;")

        app_desc = QLabel("VP9 WEBM COMPRESSION ENGINE // TELEGRAM COMPLIANCE [ 512PX • ≤256KB • ≤3.0S ]")
        app_desc.setStyleSheet("font-size: 8pt; color: #92968C; font-family: 'Consolas', monospace;")

        title_box.addWidget(app_title)
        title_box.addWidget(app_desc)
        header.addLayout(title_box)

        header.addStretch()

        self.dep_warning = QLabel("")
        self.dep_warning.setStyleSheet("color: #FF4D4D; font-weight: bold; font-size: 8.5pt;")
        header.addWidget(self.dep_warning)

        self.btn_settings = QPushButton("SETTINGS")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)
        header.addWidget(self.btn_settings)

        main_layout.addLayout(header)

        # 2. Main Horizontal Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # --- Left Panel: Queue & File Management ---
        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #181B16; border: 1px solid #2B3026; border-radius: 4px;")
        v_left = QVBoxLayout(left_panel)
        v_left.setContentsMargins(12, 12, 12, 12)
        v_left.setSpacing(10)

        # Queue Header
        q_head = QHBoxLayout()
        q_title = QLabel("FILE QUEUE")
        q_title.setStyleSheet("font-size: 9.5pt; font-weight: 700; color: #E8EBE4; letter-spacing: 0.5px;")
        self.lbl_queue_count = QLabel("0")
        self.lbl_queue_count.setStyleSheet("""
            background-color: #1E211B;
            color: #9EF41A;
            font-size: 7.5pt;
            font-weight: bold;
            font-family: 'Consolas', monospace;
            padding: 2px 7px;
            border: 1px solid #2B3026;
            border-radius: 3px;
        """)
        q_head.addWidget(q_title)
        q_head.addWidget(self.lbl_queue_count)
        q_head.addStretch()

        self.btn_clear = QPushButton("CLEAR")
        self.btn_clear.clicked.connect(self._clear_queue)
        q_head.addWidget(self.btn_clear)
        v_left.addLayout(q_head)

        # Queue List
        self.queue_list = FileQueueList()
        v_left.addWidget(self.queue_list, 1)

        # Queue Action Buttons
        btn_box = QHBoxLayout()
        self.btn_add_files = QPushButton("[ + ] ADD FILES")
        self.btn_add_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_files.clicked.connect(self._select_files)

        self.btn_add_folder = QPushButton("[ + ] FOLDER")
        self.btn_add_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_folder.clicked.connect(self._select_folder)

        btn_box.addWidget(self.btn_add_files)
        btn_box.addWidget(self.btn_add_folder)
        v_left.addLayout(btn_box)

        # Export Directory Bar
        dest_box = QVBoxLayout()
        dest_box.setSpacing(4)
        lbl_dest = QLabel("EXPORT DIRECTORY:")
        lbl_dest.setStyleSheet("color: #92968C; font-size: 8pt; font-weight: 600; font-family: 'Consolas', monospace;")

        dest_row = QHBoxLayout()
        self.lbl_dest_path = QLabel("—")
        self.lbl_dest_path.setStyleSheet("color: #E8EBE4; font-size: 8pt; font-family: 'Consolas', monospace;")
        self.lbl_dest_path.setWordWrap(True)

        self.btn_change_dest = QPushButton("CHANGE")
        self.btn_change_dest.clicked.connect(self._change_export_folder)

        self.btn_open_folder = QPushButton("OPEN DIR")
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
        right_panel.setStyleSheet("background-color: #181B16; border: 1px solid #2B3026; border-radius: 4px;")
        v_right = QVBoxLayout(right_panel)
        v_right.setContentsMargins(14, 14, 14, 14)
        v_right.setSpacing(10)

        # Editor Header
        ed_head = QHBoxLayout()
        self.lbl_item_name = QLabel("NO MEDIA SELECTED")
        self.lbl_item_name.setStyleSheet("font-size: 10pt; font-weight: 700; color: #E8EBE4;")
        self.lbl_item_details = QLabel("")
        self.lbl_item_details.setStyleSheet("font-size: 8pt; color: #92968C; font-family: 'Consolas', monospace;")

        ed_head.addWidget(self.lbl_item_name)
        ed_head.addSpacing(8)
        ed_head.addWidget(self.lbl_item_details)
        ed_head.addStretch()

        self.lbl_export_spec = QLabel("TARGET SPEC: 512×512 • ≤256 KB • VP9")
        self.lbl_export_spec.setStyleSheet("""
            background-color: #1E211B;
            color: #9EF41A;
            font-size: 7.5pt;
            font-weight: 700;
            font-family: 'Consolas', monospace;
            padding: 3px 8px;
            border: 1px solid #2B3026;
            border-radius: 3px;
        """)
        ed_head.addWidget(self.lbl_export_spec)
        v_right.addLayout(ed_head)

        # Crop Canvas Viewport
        self.crop_widget = InteractiveCropWidget()
        v_right.addWidget(self.crop_widget, 1)

        # Crop Presets Bar
        crop_bar = QHBoxLayout()
        crop_bar.setSpacing(6)
        lbl_crop = QLabel("CROP:")
        lbl_crop.setStyleSheet("color: #92968C; font-size: 8pt; font-weight: 700; font-family: 'Consolas', monospace;")
        crop_bar.addWidget(lbl_crop)

        self.btn_preset_square = QPushButton("1:1 SQUARE")
        self.btn_preset_square.clicked.connect(lambda: self._set_aspect_preset(1.0))
        crop_bar.addWidget(self.btn_preset_square)

        self.btn_preset_free = QPushButton("FREE CROP")
        self.btn_preset_free.clicked.connect(lambda: self._set_aspect_preset(None))
        crop_bar.addWidget(self.btn_preset_free)

        self.btn_preset_4_3 = QPushButton("4:3")
        self.btn_preset_4_3.clicked.connect(lambda: self._set_aspect_preset(4 / 3))
        crop_bar.addWidget(self.btn_preset_4_3)

        self.btn_preset_16_9 = QPushButton("16:9")
        self.btn_preset_16_9.clicked.connect(lambda: self._set_aspect_preset(16 / 9))
        crop_bar.addWidget(self.btn_preset_16_9)

        self.btn_reset_crop = QPushButton("RESET")
        self.btn_reset_crop.clicked.connect(self._reset_crop)
        crop_bar.addWidget(self.btn_reset_crop)

        crop_bar.addStretch()

        self.lbl_target_dim = QLabel("TARGET: 512 × 512 PX")
        self.lbl_target_dim.setStyleSheet("color: #9EF41A; font-weight: 700; font-size: 8pt; font-family: 'Consolas', monospace;")
        crop_bar.addWidget(self.lbl_target_dim)

        v_right.addLayout(crop_bar)

        # Trimming Section (Timeline Slider & Transport)
        self.trim_container = QWidget()
        v_trim = QVBoxLayout(self.trim_container)
        v_trim.setContentsMargins(0, 4, 0, 0)
        v_trim.setSpacing(6)

        self.timeline_slider = TimelineRangeSlider()
        v_trim.addWidget(self.timeline_slider)

        # Transport & Spinboxes Row
        trans_row = QHBoxLayout()
        trans_row.setSpacing(8)

        self.btn_play = QPushButton("PLAY [ ▶ ]")
        self.btn_play.setFixedWidth(100)
        self.btn_play.clicked.connect(self._toggle_playback)
        trans_row.addWidget(self.btn_play)

        lbl_start = QLabel("START:")
        lbl_start.setStyleSheet("color: #92968C; font-size: 8pt; font-family: 'Consolas', monospace;")
        trans_row.addWidget(lbl_start)

        self.spin_start = QDoubleSpinBox()
        self.spin_start.setRange(0.0, 999.0)
        self.spin_start.setSingleStep(0.1)
        self.spin_start.setDecimals(2)
        self.spin_start.setSuffix("s")
        self.spin_start.valueChanged.connect(self._on_spin_start_changed)
        trans_row.addWidget(self.spin_start)

        lbl_end = QLabel("END:")
        lbl_end.setStyleSheet("color: #92968C; font-size: 8pt; font-family: 'Consolas', monospace;")
        trans_row.addWidget(lbl_end)

        self.spin_end = QDoubleSpinBox()
        self.spin_end.setRange(0.0, 999.0)
        self.spin_end.setSingleStep(0.1)
        self.spin_end.setDecimals(2)
        self.spin_end.setSuffix("s")
        self.spin_end.valueChanged.connect(self._on_spin_end_changed)
        trans_row.addWidget(self.spin_end)

        self.btn_fit_3s = QPushButton("FIT [ 3.0s ]")
        self.btn_fit_3s.setToolTip("Clamp trim segment to maximum 3.0s Telegram sticker duration")
        self.btn_fit_3s.clicked.connect(self.timeline_slider.fit_to_three_seconds)
        trans_row.addWidget(self.btn_fit_3s)

        trans_row.addStretch()
        v_trim.addLayout(trans_row)

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

        self.btn_export = QPushButton("EXPORT STICKERS [ EXEC ]")
        self.btn_export.setObjectName("PrimaryBtn")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._on_export_clicked)
        footer.addWidget(self.btn_export)

        main_layout.addLayout(footer)

        # Ensure no buttons ever steal focus from Space play/pause
        for btn in self.findChildren(QPushButton):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._update_export_destination_label()

    def _connect_signals(self):
        self.queue_list.item_selected.connect(self._on_item_selected)
        self.queue_list.item_removed.connect(self._on_item_removed)
        self.queue_list.files_dropped.connect(self._add_file_paths)

        self.queue_mgr.item_added.connect(self._on_queue_item_added)
        self.queue_mgr.item_updated.connect(self._on_queue_item_updated)
        self.queue_mgr.item_finished.connect(self._on_item_finished)
        self.queue_mgr.all_finished.connect(self._on_all_finished)

        self.crop_widget.crop_changed.connect(self._on_crop_changed)
        self.timeline_slider.range_changed.connect(self._on_trim_range_changed)
        self.timeline_slider.playhead_changed.connect(self._on_playhead_changed)

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
        self.lbl_item_name.setText("No file selected")
        self.lbl_item_details.setText("")
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
            self.lbl_item_name.setText("No file selected")
            self.lbl_item_details.setText("")
        self.queue_mgr.remove_item(task_id)
        self.queue_list.remove_queue_item(task_id)
        self.lbl_queue_count.setText(str(len(self.queue_mgr.items)))
        self._update_ui_state()

    def _on_item_selected(self, task_id: str):
        item = self.queue_mgr.items.get(task_id)
        if not item:
            return

        self._stop_playback()
        self.current_item = item

        self.lbl_item_name.setText(item.info.filename)
        self.lbl_item_details.setText(
            f"{item.info.width}×{item.info.height} • "
            f"{item.info.display_duration} • {item.info.display_size}"
        )

        # Show / hide timeline controls for static images
        is_dynamic = item.info.is_video or item.info.is_animated
        self.trim_container.setVisible(is_dynamic)

        # Configure timeline
        if is_dynamic:
            dur = item.info.duration if item.info.duration > 0 else 3.0
            self.timeline_slider.set_duration(dur, default_clamp_3s=True)
            self.spin_start.setRange(0.0, dur)
            self.spin_end.setRange(0.0, dur)

            start = item.settings.trim_start
            end = item.settings.trim_end if item.settings.trim_end > 0 else min(dur, 3.0)
            self.timeline_slider.set_range(start, end)
            self.spin_start.setValue(start)
            self.spin_end.setValue(end)

        # ── Kick off frame cache loading ──
        # GIF/WEBP: synchronous PIL decode (~instant)
        # Video: background ffmpeg extraction (UI stays responsive)
        self.lbl_global_status.setText(f"Loading preview for {item.info.filename}...")
        duration = item.info.duration if item.info.duration > 0 else 1.0
        self.frame_cache.load(
            path=item.info.path,
            duration=duration,
            orig_w=item.info.width,
            orig_h=item.info.height,
            is_animated_image=item.info.is_animated and not item.info.is_video,
        )

        # For GIF/images the frames are already ready (sync load),
        # so show the first frame immediately:
        self._show_cached_frame(item.settings.trim_start)

        # Restore crop
        self.crop_widget.set_crop_rect(item.settings.crop)
        self._update_target_dimensions_display()

    # ════════════════════════════════════════════════════════
    #  Frame Preview & Playback  (ALL from cache, zero ffmpeg)
    # ════════════════════════════════════════════════════════

    def _on_frames_ready(self):
        """Called when background video frame extraction finishes."""
        self.lbl_global_status.setText(
            f"Preview ready ({self.frame_cache.frame_count} frames cached)"
        )
        if self.current_item:
            self._show_cached_frame(self.timeline_slider.current_time)

    def _show_cached_frame(self, timestamp: float):
        """Display a frame from the cache in the crop widget. Instant lookup."""
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
        self.btn_play.setText("PAUSE [ ⏸ ]")
        self.btn_play.setStyleSheet("background-color: #232B1C; border: 1px solid #9EF41A; color: #9EF41A;")
        self.playback_timer.start()

    def _stop_playback(self):
        self.is_playing = False
        self.playback_timer.stop()
        self.btn_play.setText("PLAY [ ▶ ]")
        self.btn_play.setStyleSheet("")

    def _on_playback_step(self):
        """Advance playhead and show the next cached frame. No subprocess."""
        if not self.current_item or self.frame_cache.frame_count == 0:
            self._stop_playback()
            return

        dt = self.playback_timer.interval() / 1000.0
        new_t = self.timeline_slider.current_time + dt
        if new_t > self.timeline_slider.end_time:
            new_t = self.timeline_slider.start_time

        self.timeline_slider.current_time = new_t
        self.timeline_slider.update()
        self._show_cached_frame(new_t)

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

    def _on_trim_range_changed(self, start: float, end: float):
        if self.current_item:
            self.current_item.settings.trim_start = start
            self.current_item.settings.trim_end = end
            if self.current_item.status == TaskStatus.SUCCESS:
                self.current_item.status = TaskStatus.QUEUED
                self.current_item.status_text = "Ready"
                self.queue_list.update_item(self.current_item)
            self.spin_start.blockSignals(True)
            self.spin_end.blockSignals(True)
            self.spin_start.setValue(start)
            self.spin_end.setValue(end)
            self.spin_start.blockSignals(False)
            self.spin_end.blockSignals(False)

    def _on_playhead_changed(self, current_time: float):
        """Debounced scrub: schedule a cache lookup instead of blocking."""
        self._pending_scrub_time = current_time
        if not self._scrub_timer.isActive():
            self._scrub_timer.start()

    def _do_scrub_update(self):
        """Perform the actual frame display for the latest scrub position."""
        self._show_cached_frame(self._pending_scrub_time)

    def _on_spin_start_changed(self, val: float):
        if self.current_item:
            end = max(val + 0.05, self.spin_end.value())
            self.timeline_slider.set_range(val, end)

    def _on_spin_end_changed(self, val: float):
        if self.current_item:
            start = min(val - 0.05, self.spin_start.value())
            self.timeline_slider.set_range(start, val)

    def _update_target_dimensions_display(self):
        if not self.current_item:
            self.lbl_target_dim.setText("Output: 512 × 512 px")
            return
        info = self.current_item.info
        crop = self.current_item.settings.crop
        from .converter import StickerConverter
        calc = StickerConverter(self.config)
        w, h = calc.calculate_target_dims(info.width, info.height, crop)
        self.lbl_target_dim.setText(f"Output: {w} × {h} px (VP9)")

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
            self.lbl_dest_path.setText(folder)
            self.lbl_dest_path.setToolTip(folder)
        else:
            self.lbl_dest_path.setText("First file folder")

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
            self.btn_export.setText("EXPORT STICKERS [ EXEC ]")
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
        self.btn_export.setText("CANCEL CONVERSION [ STOP ]")
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
        self.btn_export.setText("EXPORT STICKERS [ EXEC ]")
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
