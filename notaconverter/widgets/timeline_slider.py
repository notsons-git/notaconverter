import math
from typing import Optional
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QCursor, QFont, QPolygonF
from PyQt6.QtWidgets import QWidget

HANDLE_WIDTH = 12
PLAYHEAD_WIDTH = 3
DRAG_THRESHOLD = 4.0


def format_time(seconds: float) -> str:
    secs = max(0.0, seconds)
    m = int(secs // 60)
    s = secs % 60
    return f"{m:02d}:{s:05.2f}"


class TimelineRangeSlider(QWidget):
    """
    Timeline Range Slider operating in EFFECTIVE OUTPUT TIME coordinates.
    Formula: Output Duration = Source Duration / Speed.
    3.0s on the timeline always represents a 3.0s output sticker.
    """
    range_changed = pyqtSignal(float, float)     # start_out, end_out (in output seconds)
    playhead_changed = pyqtSignal(float)        # current_out (in output seconds)
    interaction_started = pyqtSignal()          # emitted on mouse press to immediately pause playback

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(54)
        self.setMinimumWidth(260)

        self.total_duration: float = 3.0  # effective output duration in seconds
        self.start_time: float = 0.0      # output start time
        self.end_time: float = 3.0        # output end time
        self.current_time: float = 0.0    # output playhead time
        self.speed: float = 1.0           # current speed multiplier

        # Interaction state
        self._press_pos: Optional[QPointF] = None
        self._press_target: Optional[str] = None  # "start", "end", "playhead", "range_body", "track_empty"
        self._is_dragging: bool = False
        self._drag_initial_start: float = 0.0
        self._drag_initial_end: float = 3.0
        self._drag_initial_dur: float = 3.0
        self._drag_press_time: float = 0.0
        self._drag_time_offset: float = 0.0

    def set_speed(self, speed: float):
        self.speed = max(0.1, float(speed))
        self.update()

    def set_duration(self, duration: float, default_clamp_3s: bool = True):
        """Sets total effective output duration."""
        self.total_duration = max(0.1, duration)
        self.start_time = 0.0
        if default_clamp_3s and self.total_duration > 3.0:
            self.end_time = 3.0
        else:
            self.end_time = min(self.total_duration, 3.0)
        self.current_time = self.start_time
        self.update()

    def set_range(self, start: float, end: float):
        """Sets selected output range."""
        self.start_time = max(0.0, min(start, self.total_duration))
        self.end_time = max(self.start_time + 0.05, min(end, self.total_duration))
        self.current_time = max(self.start_time, min(self.current_time, self.end_time))
        self.update()
        self.range_changed.emit(self.start_time, self.end_time)

    def set_playhead(self, timestamp: float):
        """Sets playhead position in output time."""
        self.current_time = max(0.0, min(timestamp, self.total_duration))
        self.update()
        self.playhead_changed.emit(self.current_time)

    def fit_to_three_seconds(self):
        """Clamps the selected range to maximum 3.0s (Telegram requirement) starting from start_time."""
        self.end_time = min(self.total_duration, self.start_time + 3.0)
        if self.end_time - self.start_time < 0.1:
            self.start_time = max(0.0, self.end_time - 3.0)
        self.current_time = max(self.start_time, min(self.current_time, self.end_time))
        self.update()
        self.range_changed.emit(self.start_time, self.end_time)

    @property
    def selected_duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def _track_rect(self) -> QRectF:
        pad_x = 16
        pad_y = 18
        return QRectF(pad_x, pad_y, self.width() - 2 * pad_x, 18)

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

    def _hit_test(self, pos_x: float, track: QRectF) -> str:
        sx = self._time_to_x(self.start_time, track)
        ex = self._time_to_x(self.end_time, track)
        px = self._time_to_x(self.current_time, track)

        if abs(pos_x - px) <= 6:
            return "playhead"
        if abs(pos_x - sx) <= HANDLE_WIDTH / 2 + 3:
            return "start"
        if abs(pos_x - ex) <= HANDLE_WIDTH / 2 + 3:
            return "end"
        if sx < pos_x < ex:
            return "range_body"
        return "track_empty"

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        self.interaction_started.emit()

        track = self._track_rect()
        pos_x = event.position().x()

        self._press_pos = event.position()
        self._press_target = self._hit_test(pos_x, track)
        self._is_dragging = False

        self._drag_initial_start = self.start_time
        self._drag_initial_end = self.end_time
        self._drag_initial_dur = self.end_time - self.start_time
        self._drag_press_time = self._x_to_time(pos_x, track)
        self._drag_time_offset = self._drag_press_time - self.start_time

        if self._press_target == "track_empty":
            t = self._x_to_time(pos_x, track)
            self.set_playhead(t)

    def mouseMoveEvent(self, event):
        track = self._track_rect()
        pos_x = event.position().x()

        if self._press_pos is None:
            self._update_hover_cursor(pos_x, track)
            return

        dx = event.position().x() - self._press_pos.x()
        dy = event.position().y() - self._press_pos.y()
        dist = math.hypot(dx, dy)

        if not self._is_dragging and dist >= DRAG_THRESHOLD:
            self._is_dragging = True
            if self._press_target == "range_body":
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            elif self._press_target in ("start", "end"):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif self._press_target in ("playhead", "track_empty"):
                self.setCursor(QCursor(Qt.CursorShape.SplitHCursor))

        if self._is_dragging:
            t = self._x_to_time(pos_x, track)

            if self._press_target == "range_body":
                dur = self._drag_initial_dur
                target_start = t - self._drag_time_offset
                if target_start < 0.0:
                    target_start = 0.0
                if target_start + dur > self.total_duration:
                    target_start = max(0.0, self.total_duration - dur)
                target_end = min(self.total_duration, target_start + dur)

                self.start_time = target_start
                self.end_time = target_end
                self.current_time = max(self.start_time, min(self.current_time, self.end_time))

                self.range_changed.emit(self.start_time, self.end_time)
                self.playhead_changed.emit(self.current_time)
                self.update()

            elif self._press_target == "start":
                self.start_time = max(0.0, min(t, self.end_time - 0.05))
                self.current_time = max(self.start_time, min(self.current_time, self.end_time))
                self.range_changed.emit(self.start_time, self.end_time)
                self.playhead_changed.emit(self.current_time)
                self.update()

            elif self._press_target == "end":
                self.end_time = max(self.start_time + 0.05, min(t, self.total_duration))
                self.current_time = max(self.start_time, min(self.current_time, self.end_time))
                self.range_changed.emit(self.start_time, self.end_time)
                self.playhead_changed.emit(self.current_time)
                self.update()

            elif self._press_target in ("playhead", "track_empty"):
                self.set_playhead(t)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            track = self._track_rect()
            pos_x = event.position().x()

            if not self._is_dragging:
                t = self._x_to_time(pos_x, track)
                self.set_playhead(t)

            self._press_pos = None
            self._press_target = None
            self._is_dragging = False
            self._update_hover_cursor(pos_x, track)
            self.update()

    def _update_hover_cursor(self, pos_x: float, track: QRectF):
        target = self._hit_test(pos_x, track)
        if target in ("start", "end"):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif target == "playhead":
            self.setCursor(QCursor(Qt.CursorShape.SplitHCursor))
        elif target == "range_body":
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        elif target == "track_empty":
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = self._track_rect()

        # 1. Track background container
        painter.setPen(QPen(QColor("#2B3026"), 1))
        painter.setBrush(QColor("#141712"))
        painter.drawRoundedRect(track, 3, 3)

        # 2. Subtle tick marks along the duration
        painter.setPen(QPen(QColor("#22271D"), 1))
        num_ticks = 10
        for i in range(1, num_ticks):
            tx = track.left() + (i / num_ticks) * track.width()
            painter.drawLine(QPointF(tx, track.top() + 4), QPointF(tx, track.bottom() - 4))

        sx = self._time_to_x(self.start_time, track)
        ex = self._time_to_x(self.end_time, track)
        px = self._time_to_x(self.current_time, track)

        sel_dur = self.selected_duration
        is_over_limit = sel_dur > 3.01
        accent_color = QColor("#FF4D4D") if is_over_limit else QColor("#9EF41A")

        # 3. Active selection range band
        rw = max(2.0, ex - sx)
        range_rect = QRectF(sx, track.top() + 1, rw, track.height() - 2)

        # Semi-transparent range fill
        range_fill = QColor(255, 77, 77, 45) if is_over_limit else QColor(158, 244, 26, 40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(range_fill)
        painter.drawRect(range_rect)

        # Range top & bottom borders
        painter.setPen(QPen(accent_color, 1.5))
        painter.drawLine(QPointF(sx, track.top() + 1), QPointF(ex, track.top() + 1))
        painter.drawLine(QPointF(sx, track.bottom() - 1), QPointF(ex, track.bottom() - 1))

        # 3.1 Compact Speed Badge directly inside the selected range!
        if rw >= 24:
            spd_text = f"{self.speed:.1f}×" if self.speed != int(self.speed) else f"{int(self.speed)}×"
            painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
            painter.setPen(QColor("#9EF41A"))
            badge_r = QRectF(sx, track.top() + 1, rw, track.height() - 2)
            painter.drawText(badge_r, Qt.AlignmentFlag.AlignCenter, spd_text)

        # 4. IN Handle (Left bracket marker)
        in_rect = QRectF(sx - HANDLE_WIDTH / 2, track.top() - 2, HANDLE_WIDTH, track.height() + 4)
        painter.setPen(QPen(accent_color, 1.5))
        painter.setBrush(QColor("#1E221B"))
        painter.drawRoundedRect(in_rect, 2, 2)
        painter.setPen(QPen(accent_color, 1))
        painter.drawLine(QPointF(sx, track.top() + 3), QPointF(sx, track.bottom() - 3))

        # 5. OUT Handle (Right bracket marker)
        out_rect = QRectF(ex - HANDLE_WIDTH / 2, track.top() - 2, HANDLE_WIDTH, track.height() + 4)
        painter.setPen(QPen(accent_color, 1.5))
        painter.setBrush(QColor("#1E221B"))
        painter.drawRoundedRect(out_rect, 2, 2)
        painter.setPen(QPen(accent_color, 1))
        painter.drawLine(QPointF(ex, track.top() + 3), QPointF(ex, track.bottom() - 3))

        # 6. Playhead Scrubber (White crisp needle with diamond cap)
        painter.setPen(QPen(QColor("#FFFFFF"), PLAYHEAD_WIDTH))
        painter.drawLine(QPointF(px, track.top() - 3), QPointF(px, track.bottom() + 3))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        top_diamond = QPolygonF([
            QPointF(px, track.top() - 6),
            QPointF(px + 4, track.top() - 2),
            QPointF(px, track.top() + 2),
            QPointF(px - 4, track.top() - 2),
        ])
        painter.drawPolygon(top_diamond)

        # 7. Time Header Labels (Single place of truth, aligned)
        painter.setFont(QFont("Consolas", 8))
        painter.setPen(QColor("#92968C"))

        start_lbl = format_time(self.start_time)
        end_lbl = format_time(self.total_duration)
        dur_lbl = f"{sel_dur:.2f}s"
        if is_over_limit:
            dur_lbl += " [>3.0s!]"

        painter.drawText(QRectF(track.left(), 2, 80, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, start_lbl)
        painter.drawText(QRectF(track.right() - 80, 2, 80, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, end_lbl)

        # Center duration
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        painter.setPen(accent_color)
        painter.drawText(QRectF(track.left(), 2, track.width(), 14), Qt.AlignmentFlag.AlignCenter, dur_lbl)
