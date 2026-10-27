from typing import Optional
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QCursor, QFont
from PyQt6.QtWidgets import QWidget

HANDLE_WIDTH = 12
PLAYHEAD_WIDTH = 4


def format_time(seconds: float) -> str:
    secs = max(0.0, seconds)
    m = int(secs // 60)
    s = secs % 60
    return f"{m:02d}:{s:05.2f}"


class TimelineRangeSlider(QWidget):
    range_changed = pyqtSignal(float, float)   # start_time, end_time
    playhead_changed = pyqtSignal(float)      # current_time

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(54)
        self.setMinimumWidth(240)

        self.total_duration = 3.0  # seconds
        self.start_time = 0.0
        self.end_time = 3.0
        self.current_time = 0.0

        self.dragging = None  # "start", "end", "playhead", "bar"
        self.drag_offset = 0.0

    def set_duration(self, duration: float, default_clamp_3s: bool = True):
        self.total_duration = max(0.1, duration)
        self.start_time = 0.0
        if default_clamp_3s and self.total_duration > 3.0:
            self.end_time = 3.0
        else:
            self.end_time = min(self.total_duration, 3.0)
        self.current_time = self.start_time
        self.update()

    def set_range(self, start: float, end: float):
        self.start_time = max(0.0, min(start, self.total_duration))
        self.end_time = max(self.start_time + 0.05, min(end, self.total_duration))
        self.current_time = max(self.start_time, min(self.current_time, self.end_time))
        self.update()
        self.range_changed.emit(self.start_time, self.end_time)

    def set_playhead(self, timestamp: float):
        self.current_time = max(0.0, min(timestamp, self.total_duration))
        self.update()
        self.playhead_changed.emit(self.current_time)

    def fit_to_three_seconds(self):
        """Clamps the selected range to maximum 3.0s (Telegram requirement) starting from start_time."""
        self.end_time = min(self.total_duration, self.start_time + 3.0)
        if self.end_time - self.start_time < 0.1:
            self.start_time = max(0.0, self.end_time - 3.0)
        self.update()
        self.range_changed.emit(self.start_time, self.end_time)

    @property
    def selected_duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def _track_rect(self) -> QRectF:
        pad_x = 16
        pad_y = 18
        return QRectF(pad_x, pad_y, self.width() - 2 * pad_x, 16)

    def _time_to_x(self, t: float, track: QRectF) -> float:
        if self.total_duration <= 0:
            return track.left()
        ratio = max(0.0, min(1.0, t / self.total_duration))
        return track.left() + ratio * track.width()

    def _x_to_time(self, x: float, track: QRectF) -> float:
        if track.width() <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, (x - track.left()) / track.width()))
        return ratio * self.total_duration

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        track = self._track_rect()
        pos_x = event.position().x()

        sx = self._time_to_x(self.start_time, track)
        ex = self._time_to_x(self.end_time, track)
        px = self._time_to_x(self.current_time, track)

        # Hit test playhead
        if abs(pos_x - px) <= 6:
            self.dragging = "playhead"
            return

        # Hit test start handle
        if abs(pos_x - sx) <= HANDLE_WIDTH:
            self.dragging = "start"
            return

        # Hit test end handle
        if abs(pos_x - ex) <= HANDLE_WIDTH:
            self.dragging = "end"
            return

        # Hit test inside range bar
        if sx < pos_x < ex:
            self.dragging = "playhead"
            self.set_playhead(self._x_to_time(pos_x, track))
            return

        # Click outside range moves playhead or nearest handle
        t = self._x_to_time(pos_x, track)
        if t < sx:
            self.start_time = max(0.0, t)
            self.current_time = self.start_time
            self.dragging = "start"
        elif t > ex:
            self.end_time = min(self.total_duration, t)
            self.current_time = self.end_time
            self.dragging = "end"
        self.update()
        self.range_changed.emit(self.start_time, self.end_time)

    def mouseMoveEvent(self, event):
        track = self._track_rect()
        pos_x = event.position().x()

        if not self.dragging:
            sx = self._time_to_x(self.start_time, track)
            ex = self._time_to_x(self.end_time, track)
            px = self._time_to_x(self.current_time, track)

            if abs(pos_x - sx) <= HANDLE_WIDTH or abs(pos_x - ex) <= HANDLE_WIDTH:
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif abs(pos_x - px) <= 6:
                self.setCursor(QCursor(Qt.CursorShape.SplitHCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            return

        t = self._x_to_time(pos_x, track)

        if self.dragging == "start":
            self.start_time = max(0.0, min(t, self.end_time - 0.05))
            self.current_time = max(self.start_time, min(self.current_time, self.end_time))
            self.range_changed.emit(self.start_time, self.end_time)
            self.playhead_changed.emit(self.current_time)
        elif self.dragging == "end":
            self.end_time = max(self.start_time + 0.05, min(t, self.total_duration))
            self.current_time = max(self.start_time, min(self.current_time, self.end_time))
            self.range_changed.emit(self.start_time, self.end_time)
            self.playhead_changed.emit(self.current_time)
        elif self.dragging == "playhead":
            self.current_time = max(0.0, min(t, self.total_duration))
            self.playhead_changed.emit(self.current_time)

        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = self._track_rect()

        # Background track
        painter.setPen(QPen(QColor("#2B3026"), 1))
        painter.setBrush(QColor("#181B16"))
        painter.drawRoundedRect(track, 3, 3)

        sx = self._time_to_x(self.start_time, track)
        ex = self._time_to_x(self.end_time, track)
        px = self._time_to_x(self.current_time, track)

        # Active range bar
        sel_dur = self.selected_duration
        is_over_limit = sel_dur > 3.01
        range_color = QColor("#FF4D4D") if is_over_limit else QColor("#9EF41A")

        active_rect = QRectF(sx, track.top(), max(2, ex - sx), track.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(range_color)
        painter.drawRoundedRect(active_rect, 2, 2)

        # Start Handle
        painter.setBrush(QColor("#1E211B"))
        painter.setPen(QPen(range_color, 1.5))
        start_rect = QRectF(sx - HANDLE_WIDTH / 2, track.top() - 3, HANDLE_WIDTH, track.height() + 6)
        painter.drawRoundedRect(start_rect, 2, 2)

        # End Handle
        end_rect = QRectF(ex - HANDLE_WIDTH / 2, track.top() - 3, HANDLE_WIDTH, track.height() + 6)
        painter.drawRoundedRect(end_rect, 2, 2)

        # Playhead scrubber
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        playhead_rect = QRectF(px - PLAYHEAD_WIDTH / 2, track.top() - 6, PLAYHEAD_WIDTH, track.height() + 12)
        painter.drawRoundedRect(playhead_rect, 1, 1)

        # Top Time labels
        painter.setFont(QFont("Consolas", 8))
        painter.setPen(QColor("#92968C"))

        start_lbl = format_time(self.start_time)
        end_lbl = format_time(self.end_time)
        dur_lbl = f"DUR: {sel_dur:.2f}s"
        if is_over_limit:
            dur_lbl += " [MAX 3.0s]"

        painter.drawText(QRectF(track.left(), 0, 100, 15), Qt.AlignmentFlag.AlignLeft, start_lbl)
        painter.drawText(QRectF(track.right() - 100, 0, 100, 15), Qt.AlignmentFlag.AlignRight, end_lbl)

        # Center duration badge
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        painter.setPen(range_color)
        painter.drawText(QRectF(track.left(), 0, track.width(), 15), Qt.AlignmentFlag.AlignCenter, dur_lbl)
