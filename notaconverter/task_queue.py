import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Callable
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool

from .config import AppConfig
from .media_probe import MediaInfo, MediaProbe
from .converter import StickerConverter, ItemSettings, ConversionError


class TaskStatus(Enum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    SUCCESS = "Success"
    ERROR = "Error"
    CANCELLED = "Cancelled"


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip(" .")
    return cleaned or "sticker"


@dataclass
class QueueItem:
    id: str
    info: MediaInfo
    settings: ItemSettings = field(default_factory=ItemSettings)
    status: TaskStatus = TaskStatus.QUEUED
    progress: float = 0.0
    status_text: str = "Ready"
    output_path: str = ""
    output_size: int = 0
    output_duration: float = 0.0
    error_message: str = ""
    converter: Optional[StickerConverter] = None


class WorkerSignals(QObject):
    progress = pyqtSignal(str, float, str)   # task_id, percent, text
    completed = pyqtSignal(str, str, int, float) # task_id, out_path, size, duration
    failed = pyqtSignal(str, str)            # task_id, error_text


class ConvertRunnable(QRunnable):
    def __init__(self, item: QueueItem, config: AppConfig, signals: WorkerSignals):
        super().__init__()
        self.item = item
        self.config = config
        self.signals = signals
        self.converter = StickerConverter(config)
        self.item.converter = self.converter

    def run(self):
        try:
            self.signals.progress.emit(self.item.id, 5.0, "Starting...")
            out_path, size, duration = self.converter.convert(
                info=self.item.info,
                output_path=self.item.output_path,
                item_settings=self.item.settings,
                progress_cb=lambda pct, txt: self.signals.progress.emit(self.item.id, pct, txt)
            )
            self.signals.completed.emit(self.item.id, out_path, size, duration)
        except Exception as e:
            self.signals.failed.emit(self.item.id, str(e))


class QueueManager(QObject):
    item_added = pyqtSignal(QueueItem)
    item_updated = pyqtSignal(QueueItem)
    item_finished = pyqtSignal(QueueItem)
    item_removed = pyqtSignal(str)
    all_finished = pyqtSignal()
    queue_cleared = pyqtSignal()

    def __init__(self, config: Optional[AppConfig] = None):
        super().__init__()
        self.config = config or AppConfig.load()
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(max(1, min(self.config.concurrency, 4)))
        self.items: Dict[str, QueueItem] = {}
        self.signals = WorkerSignals()
        self.signals.progress.connect(self._on_progress)
        self.signals.completed.connect(self._on_completed)
        self.signals.failed.connect(self._on_failed)
        self.is_running = False

    def add_file(self, path: str) -> Optional[QueueItem]:
        info = MediaProbe.probe(path)
        if not info:
            return None

        task_id = f"{len(self.items) + 1}_{Path(path).stem}"
        settings = ItemSettings()
        # Auto-trim end to 3.0s if longer than 3.0s
        if info.duration > 3.0:
            settings.trim_end = 3.0

        item = QueueItem(
            id=task_id,
            info=info,
            settings=settings,
            status=TaskStatus.QUEUED,
            status_text="Queued"
        )
        self.items[task_id] = item
        self.item_added.emit(item)
        return item

    def remove_item(self, task_id: str):
        if task_id in self.items:
            item = self.items[task_id]
            if item.converter:
                item.converter.cancel()
            del self.items[task_id]
            self.item_removed.emit(task_id)

    def clear(self):
        self.cancel_all()
        self.items.clear()
        self.queue_cleared.emit()

    def cancel_all(self):
        for item in self.items.values():
            if item.status == TaskStatus.PROCESSING and item.converter:
                item.converter.cancel()
                item.status = TaskStatus.CANCELLED
                item.status_text = "Cancelled"
                self.item_updated.emit(item)
        self.is_running = False

    def resolve_output_path(self, item: QueueItem, export_dir: str) -> str:
        os.makedirs(export_dir, exist_ok=True)
        raw = item.settings.custom_name.strip() if item.settings.custom_name else Path(item.info.path).stem
        if raw.lower().endswith(".webm"):
            raw = raw[:-5]
        base = sanitize_filename(raw)
        candidate = os.path.join(export_dir, f"{base}.webm")

        # Duplicate numbering: file (1).webm, file (2).webm...
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(export_dir, f"{base} ({counter}).webm")
            counter += 1

        return candidate

    def start_processing(self, export_dir: str):
        self.is_running = True
        self.thread_pool.setMaxThreadCount(max(1, min(self.config.concurrency, 4)))

        queued_items = [
            item for item in self.items.values()
            if item.status in (TaskStatus.QUEUED, TaskStatus.ERROR, TaskStatus.CANCELLED)
        ]

        # If everything in queue is already SUCCESS, re-export all
        if not queued_items:
            queued_items = list(self.items.values())

        if not queued_items:
            self.all_finished.emit()
            return

        for item in queued_items:
            item.output_path = self.resolve_output_path(item, export_dir)
            item.status = TaskStatus.PROCESSING
            item.progress = 0.0
            item.status_text = "Queued for worker..."
            self.item_updated.emit(item)

            runnable = ConvertRunnable(item, self.config, self.signals)
            self.thread_pool.start(runnable)

    def _on_progress(self, task_id: str, percent: float, text: str):
        if task_id in self.items:
            item = self.items[task_id]
            item.progress = percent
            item.status_text = text
            self.item_updated.emit(item)

    def _on_completed(self, task_id: str, out_path: str, size: int, duration: float):
        if task_id in self.items:
            item = self.items[task_id]
            item.status = TaskStatus.SUCCESS
            item.progress = 100.0
            item.output_path = out_path
            item.output_size = size
            item.output_duration = duration
            item.status_text = f"✓ {size // 1024} KB • {duration:.2f}s"
            self.item_updated.emit(item)
            self.item_finished.emit(item)
            self._check_all_finished()

    def _on_failed(self, task_id: str, error_text: str):
        if task_id in self.items:
            item = self.items[task_id]
            item.status = TaskStatus.ERROR
            item.status_text = f"Error: {error_text}"
            item.error_message = error_text
            self.item_updated.emit(item)
            self._check_all_finished()

    def _check_all_finished(self):
        all_done = all(
            item.status in (TaskStatus.SUCCESS, TaskStatus.ERROR, TaskStatus.CANCELLED)
            for item in self.items.values()
        )
        if all_done:
            self.is_running = False
            self.all_finished.emit()
