from pathlib import Path
from typing import Optional, Dict
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QFrame, QLineEdit
)

from ..task_queue import QueueItem, TaskStatus


class EditableNameField(QLineEdit):
    focused = pyqtSignal()

    def focusInEvent(self, event):
        self.focused.emit()
        super().focusInEvent(event)


FORMAT_BADGE_STYLE = """
    QLabel {
        background-color: #1E221B;
        color: #9EF41A;
        font-family: "Consolas", "Courier New", monospace;
        font-weight: 700;
        font-size: 7.5pt;
        border: 1px solid #2B3026;
        border-radius: 3px;
        padding: 2px 5px;
    }
"""


class FileCardWidget(QFrame):
    remove_requested = pyqtSignal(str)
    select_requested = pyqtSignal(str)

    def __init__(self, item: QueueItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("FileCard")
        self.setStyleSheet("""
            QFrame#FileCard {
                background-color: #181B16;
                border: 1px solid #2B3026;
                border-radius: 4px;
            }
            QFrame#FileCard:hover {
                border: 1px solid #363E30;
                background-color: #20241E;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        # Top row: Format badge + Editable Filename + Remove button
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Badge
        ext = item.info.ext.lower()
        self.format_badge = QLabel(ext.replace(".", "").upper())
        self.format_badge.setStyleSheet(FORMAT_BADGE_STYLE)
        top_row.addWidget(self.format_badge)

        # Filename (Editable)
        initial_name = item.settings.custom_name or Path(item.info.path).stem
        self.name_edit = EditableNameField(initial_name)
        self.name_edit.setToolTip("Click to rename export file (without .webm)")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #E8EBE4;
                font-weight: 600;
                font-size: 8.5pt;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 1px 4px;
            }
            QLineEdit:hover {
                background-color: #22271F;
                border: 1px solid #363E30;
            }
            QLineEdit:focus {
                background-color: #121411;
                border: 1px solid #9EF41A;
                color: #FFFFFF;
            }
        """)
        self.name_edit.textChanged.connect(self._on_name_changed)
        self.name_edit.focused.connect(lambda: self.select_requested.emit(self.item.id))
        top_row.addWidget(self.name_edit, 1)

        # Remove button
        self.btn_remove = QPushButton("×")
        self.btn_remove.setFixedSize(20, 20)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #92968C;
                border: none;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                color: #FF4D4D;
                background-color: #2A1F1F;
                border-radius: 3px;
            }
        """)
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self.item.id))
        top_row.addWidget(self.btn_remove)

        layout.addLayout(top_row)

        # Middle row: Metadata info (Resolution, Duration, Original Size)
        info_parts = [
            f"{item.info.width}×{item.info.height}",
            item.info.display_duration,
            item.info.display_size
        ]
        if item.info.has_alpha:
            info_parts.append("ALPHA")
        self.meta_label = QLabel(" • ".join(info_parts))
        self.meta_label.setStyleSheet("color: #92968C; font-size: 8pt; font-family: 'Consolas', monospace;")
        layout.addWidget(self.meta_label)

        # Bottom row: Progress bar + Status text
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #121411;
                border: none;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background-color: #9EF41A;
                border-radius: 1px;
            }
        """)
        self.progress_bar.setValue(int(item.progress))
        bottom_row.addWidget(self.progress_bar, 1)

        self.status_label = QLabel(item.status_text)
        self.status_label.setStyleSheet("color: #92968C; font-size: 8pt; font-family: 'Consolas', monospace;")
        bottom_row.addWidget(self.status_label)

        layout.addLayout(bottom_row)

    def mousePressEvent(self, event):
        self.select_requested.emit(self.item.id)
        super().mousePressEvent(event)

    def _on_name_changed(self, text: str):
        clean = text.strip()
        if clean.lower().endswith(".webm"):
            clean = clean[:-5]
        self.item.settings.custom_name = clean
        if self.item.status == TaskStatus.SUCCESS:
            self.item.status = TaskStatus.QUEUED
            self.item.status_text = "Ready"
            self.update_item_state(self.item)

    def set_selected(self, selected: bool):
        if selected:
            self.setStyleSheet("""
                QFrame#FileCard {
                    background-color: #1E251A;
                    border: 1px solid #9EF41A;
                    border-radius: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#FileCard {
                    background-color: #181B16;
                    border: 1px solid #2B3026;
                    border-radius: 4px;
                }
                QFrame#FileCard:hover {
                    border: 1px solid #363E30;
                    background-color: #20241E;
                }
            """)

    def update_item_state(self, item: QueueItem):
        self.item = item
        self.progress_bar.setValue(int(item.progress))
        self.status_label.setText(item.status_text)

        if item.status == TaskStatus.SUCCESS:
            self.status_label.setStyleSheet("color: #9EF41A; font-weight: bold; font-size: 8pt;")
            self.progress_bar.setStyleSheet("""
                QProgressBar { background-color: #121411; border: none; border-radius: 1px; }
                QProgressBar::chunk { background-color: #9EF41A; border-radius: 1px; }
            """)
        elif item.status == TaskStatus.ERROR:
            self.status_label.setStyleSheet("color: #FF4D4D; font-weight: bold; font-size: 8pt;")
            self.progress_bar.setStyleSheet("""
                QProgressBar { background-color: #121411; border: none; border-radius: 1px; }
                QProgressBar::chunk { background-color: #FF4D4D; border-radius: 1px; }
            """)
        elif item.status == TaskStatus.PROCESSING:
            self.status_label.setStyleSheet("color: #9EF41A; font-weight: bold; font-size: 8pt;")
        else:
            self.status_label.setStyleSheet("color: #92968C; font-size: 8pt;")


class FileQueueList(QListWidget):
    item_selected = pyqtSignal(str) # task_id
    item_removed = pyqtSignal(str)  # task_id
    files_dropped = pyqtSignal(list) # list of paths

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(4)
        self.setStyleSheet("""
            QListWidget {
                background-color: #141712;
                border: 1px solid #23271E;
                border-radius: 4px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QListWidget::item:selected {
                background: transparent;
                border: none;
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

        self.cards: Dict[str, FileCardWidget] = {}
        self.item_by_task_id: Dict[str, QListWidgetItem] = {}

        self.itemSelectionChanged.connect(self._on_selection_changed)

    def add_queue_item(self, item: QueueItem):
        list_item = QListWidgetItem(self)
        list_item.setData(Qt.ItemDataRole.UserRole, item.id)
        card = FileCardWidget(item)
        card.remove_requested.connect(self.item_removed.emit)
        card.select_requested.connect(self.select_item_by_id)

        list_item.setSizeHint(card.sizeHint())
        self.addItem(list_item)
        self.setItemWidget(list_item, card)

        self.cards[item.id] = card
        self.item_by_task_id[item.id] = list_item

        # Auto-select if first item
        if self.count() == 1:
            self.setCurrentItem(list_item)

    def remove_queue_item(self, task_id: str):
        if task_id in self.item_by_task_id:
            list_item = self.item_by_task_id[task_id]
            row = self.row(list_item)
            self.takeItem(row)
            if task_id in self.cards:
                del self.cards[task_id]
            del self.item_by_task_id[task_id]

    def clear_all(self):
        self.clear()
        self.cards.clear()
        self.item_by_task_id.clear()

    def update_item(self, item: QueueItem):
        if item.id in self.cards:
            self.cards[item.id].update_item_state(item)

    def select_item_by_id(self, task_id: str):
        if task_id in self.item_by_task_id:
            self.setCurrentItem(self.item_by_task_id[task_id])

    def _on_selection_changed(self):
        curr = self.currentItem()
        selected_id = curr.data(Qt.ItemDataRole.UserRole) if curr else None

        for tid, card in self.cards.items():
            card.set_selected(tid == selected_id)

        if selected_id:
            self.item_selected.emit(selected_id)

    # Drag and Drop handling
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
