import math
from typing import Optional, Tuple
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QImage, QPixmap, QCursor
from PyQt6.QtWidgets import QWidget

from ..converter import CropRect

HANDLE_SIZE = 10
HANDLE_HALF = HANDLE_SIZE / 2


class InteractiveCropWidget(QWidget):
    crop_changed = pyqtSignal(CropRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(280, 240)

        self.source_pixmap: Optional[QPixmap] = None
        self.orig_width = 1
        self.orig_height = 1

        # Normalized crop coordinates in range [0.0, 1.0]
        self.norm_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self.aspect_ratio: Optional[float] = None  # None = Free, 1.0 = Square, etc.

        self.dragging = False
        self.active_handle = None
        self.drag_start_pos = QPointF()
        self.drag_start_rect = QRectF()

    def set_image(self, pixmap: Optional[QPixmap], orig_w: int, orig_h: int):
        self.source_pixmap = pixmap
        self.orig_width = max(1, orig_w)
        self.orig_height = max(1, orig_h)
        self.update()

    def set_crop_rect(self, crop: Optional[CropRect]):
        if crop and crop.is_valid:
            nx = max(0.0, min(1.0, crop.x / self.orig_width))
            ny = max(0.0, min(1.0, crop.y / self.orig_height))
            nw = max(0.05, min(1.0 - nx, crop.width / self.orig_width))
            nh = max(0.05, min(1.0 - ny, crop.height / self.orig_height))
            self.norm_rect = QRectF(nx, ny, nw, nh)
        else:
            self.norm_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self.update()

    def set_aspect_ratio(self, ratio: Optional[float]):
        """Sets fixed aspect ratio (e.g. 1.0 for square, None for free) and adjusts crop box."""
        self.aspect_ratio = ratio
        if ratio is not None:
            # Fit centered ratio box into current norm_rect
            img_ratio = self.orig_width / self.orig_height
            # Target width / height in normalized units
            target_norm_ratio = ratio / img_ratio
            cx = self.norm_rect.center().x()
            cy = self.norm_rect.center().y()

            w = self.norm_rect.width()
            h = w / target_norm_ratio
            if h > 1.0:
                h = 1.0
                w = h * target_norm_ratio
            if w > 1.0:
                w = 1.0
                h = w / target_norm_ratio

            x = max(0.0, min(1.0 - w, cx - w / 2))
            y = max(0.0, min(1.0 - h, cy - h / 2))
            self.norm_rect = QRectF(x, y, w, h)
            self._emit_crop()
        self.update()

    def reset_crop(self):
        self.norm_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self.aspect_ratio = None
        self._emit_crop()
        self.update()

    def _get_display_rect(self) -> QRectF:
        """Returns the scaled image rectangle within widget area."""
        vw = self.width() - 20
        vh = self.height() - 20
        if vw <= 0 or vh <= 0 or not self.source_pixmap:
            return QRectF(10, 10, max(10, self.width() - 20), max(10, self.height() - 20))

        img_w = self.source_pixmap.width()
        img_h = self.source_pixmap.height()
        scale = min(vw / img_w, vh / img_h)

        dw = img_w * scale
        dh = img_h * scale
        dx = (self.width() - dw) / 2
        dy = (self.height() - dh) / 2
        return QRectF(dx, dy, dw, dh)

    def _norm_to_screen(self, nr: QRectF, disp: QRectF) -> QRectF:
        return QRectF(
            disp.x() + nr.x() * disp.width(),
            disp.y() + nr.y() * disp.height(),
            nr.width() * disp.width(),
            nr.height() * disp.height()
        )

    def _screen_to_norm(self, sr: QRectF, disp: QRectF) -> QRectF:
        if disp.width() <= 0 or disp.height() <= 0:
            return QRectF(0, 0, 1, 1)
        return QRectF(
            (sr.x() - disp.x()) / disp.width(),
            (sr.y() - disp.y()) / disp.height(),
            sr.width() / disp.width(),
            sr.height() / disp.height()
        )

    def _emit_crop(self):
        cx = int(round(self.norm_rect.x() * self.orig_width))
        cy = int(round(self.norm_rect.y() * self.orig_height))
        cw = int(round(self.norm_rect.width() * self.orig_width))
        ch = int(round(self.norm_rect.height() * self.orig_height))

        # Clamp and make even
        cx = max(0, min(cx, self.orig_width - 2))
        cy = max(0, min(cy, self.orig_height - 2))
        cw = max(2, min(cw, self.orig_width - cx))
        ch = max(2, min(ch, self.orig_height - cy))

        self.crop_changed.emit(CropRect(cx, cy, cw, ch))

    def _get_handle_rects(self, screen_crop: QRectF):
        x, y, w, h = screen_crop.x(), screen_crop.y(), screen_crop.width(), screen_crop.height()
        return {
            "tl": QRectF(x - HANDLE_HALF, y - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE),
            "tr": QRectF(x + w - HANDLE_HALF, y - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE),
            "bl": QRectF(x - HANDLE_HALF, y + h - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE),
            "br": QRectF(x + w - HANDLE_HALF, y + h - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE),
            "t":  QRectF(x + w / 2 - HANDLE_HALF, y - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE),
            "b":  QRectF(x + w / 2 - HANDLE_HALF, y + h - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE),
            "l":  QRectF(x - HANDLE_HALF, y + h / 2 - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE),
            "r":  QRectF(x + w - HANDLE_HALF, y + h / 2 - HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE),
        }

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.source_pixmap:
            return

        disp = self._get_display_rect()
        sc = self._norm_to_screen(self.norm_rect, disp)
        handles = self._get_handle_rects(sc)
        pos = event.position()

        # Check handles
        for handle_name, rect in handles.items():
            if rect.contains(pos):
                self.dragging = True
                self.active_handle = handle_name
                self.drag_start_pos = pos
                self.drag_start_rect = QRectF(sc)
                return

        # Check body drag
        if sc.contains(pos):
            self.dragging = True
            self.active_handle = "body"
            self.drag_start_pos = pos
            self.drag_start_rect = QRectF(sc)
            return

        # Click outside to initiate new crop
        if disp.contains(pos):
            self.dragging = True
            self.active_handle = "br"
            self.drag_start_pos = pos
            self.drag_start_rect = QRectF(pos.x(), pos.y(), 10, 10)
            self.norm_rect = self._screen_to_norm(self.drag_start_rect, disp)
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        disp = self._get_display_rect()
        sc = self._norm_to_screen(self.norm_rect, disp)

        if not self.dragging:
            # Update cursor shape based on hover
            handles = self._get_handle_rects(sc)
            if handles["tl"].contains(pos) or handles["br"].contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
            elif handles["tr"].contains(pos) or handles["bl"].contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
            elif handles["t"].contains(pos) or handles["b"].contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
            elif handles["l"].contains(pos) or handles["r"].contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif sc.contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            return

        # Perform drag resize / move
        dx = pos.x() - self.drag_start_pos.x()
        dy = pos.y() - self.drag_start_pos.y()
        sr = QRectF(self.drag_start_rect)

        if self.active_handle == "body":
            new_x = max(disp.left(), min(disp.right() - sr.width(), sr.left() + dx))
            new_y = max(disp.top(), min(disp.bottom() - sr.height(), sr.top() + dy))
            new_sc = QRectF(new_x, new_y, sr.width(), sr.height())
        else:
            left, top, right, bottom = sr.left(), sr.top(), sr.right(), sr.bottom()
            h = self.active_handle

            if "l" in h:
                left = min(sr.right() - 20, max(disp.left(), sr.left() + dx))
            if "r" in h:
                right = max(sr.left() + 20, min(disp.right(), sr.right() + dx))
            if "t" in h:
                top = min(sr.bottom() - 20, max(disp.top(), sr.top() + dy))
            if "b" in h:
                bottom = max(sr.top() + 20, min(disp.bottom(), sr.bottom() + dy))

            new_w = right - left
            new_h = bottom - top

            if self.aspect_ratio is not None and self.aspect_ratio > 0:
                # Maintain aspect ratio
                target_ratio = self.aspect_ratio
                if "l" in h or "r" in h:
                    new_h = new_w / target_ratio
                else:
                    new_w = new_h * target_ratio

                if "t" in h:
                    top = bottom - new_h
                else:
                    bottom = top + new_h

                if "l" in h:
                    left = right - new_w
                else:
                    right = left + new_w

            new_sc = QRectF(left, top, max(20, new_w), max(20, new_h))

        norm = self._screen_to_norm(new_sc, disp)
        # Clamp to [0.0, 1.0]
        nx = max(0.0, min(0.95, norm.x()))
        ny = max(0.0, min(0.95, norm.y()))
        nw = max(0.05, min(1.0 - nx, norm.width()))
        nh = max(0.05, min(1.0 - ny, norm.height()))
        self.norm_rect = QRectF(nx, ny, nw, nh)
        self._emit_crop()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.active_handle = None
            self._emit_crop()
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background canvas
        painter.fillRect(self.rect(), QColor("#080b10"))

        disp = self._get_display_rect()

        # Checkerboard background for alpha transparency
        self._draw_transparency_grid(painter, disp)

        # Draw source image
        if self.source_pixmap and not self.source_pixmap.isNull():
            painter.drawPixmap(disp.toRect(), self.source_pixmap)
        else:
            painter.setPen(QColor("#92968C"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "NO MEDIA LOADED")
            return

        # Dimmed mask outside crop area
        sc = self._norm_to_screen(self.norm_rect, disp)
        mask_color = QColor(18, 20, 17, 190)

        # Top
        painter.fillRect(QRectF(disp.left(), disp.top(), disp.width(), sc.top() - disp.top()), mask_color)
        # Bottom
        painter.fillRect(QRectF(disp.left(), sc.bottom(), disp.width(), disp.bottom() - sc.bottom()), mask_color)
        # Left
        painter.fillRect(QRectF(disp.left(), sc.top(), sc.left() - disp.left(), sc.height()), mask_color)
        # Right
        painter.fillRect(QRectF(sc.right(), sc.top(), disp.right() - sc.right(), sc.height()), mask_color)

        # Rule of thirds guidelines inside crop box
        pen_grid = QPen(QColor(158, 244, 26, 40), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        x1 = sc.left() + sc.width() / 3
        x2 = sc.left() + 2 * sc.width() / 3
        y1 = sc.top() + sc.height() / 3
        y2 = sc.top() + 2 * sc.height() / 3
        painter.drawLine(QPointF(x1, sc.top()), QPointF(x1, sc.bottom()))
        painter.drawLine(QPointF(x2, sc.top()), QPointF(x2, sc.bottom()))
        painter.drawLine(QPointF(sc.left(), y1), QPointF(sc.right(), y1))
        painter.drawLine(QPointF(sc.left(), y2), QPointF(sc.right(), y2))

        # Precision Accent Border for Crop Box
        pen_border = QPen(QColor("#9EF41A"), 1.5)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(sc)

        # Handles
        handles = self._get_handle_rects(sc)
        painter.setPen(QPen(QColor("#121411"), 1.5))
        painter.setBrush(QBrush(QColor("#9EF41A")))
        for h_name, h_rect in handles.items():
            painter.drawRoundedRect(h_rect, 1.5, 1.5)

        # Dimensions badge
        crop_w = int(round(self.norm_rect.width() * self.orig_width))
        crop_h = int(round(self.norm_rect.height() * self.orig_height))
        badge_text = f"{crop_w} × {crop_h} PX"
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        badge_rect = QRectF(sc.left() + 6, sc.top() + 6, 116, 22)
        painter.setPen(QPen(QColor("#2B3026"), 1))
        painter.setBrush(QColor(18, 20, 17, 235))
        painter.drawRoundedRect(badge_rect, 3, 3)
        painter.setPen(QColor("#E8EBE4"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    def _draw_transparency_grid(self, painter: QPainter, rect: QRectF):
        cell_size = 12
        c1 = QColor("#121411")
        c2 = QColor("#181B16")
        cols = int(rect.width() // cell_size) + 1
        rows = int(rect.height() // cell_size) + 1

        painter.save()
        painter.setClipRect(rect)
        for r in range(rows):
            for c in range(cols):
                color = c1 if (r + c) % 2 == 0 else c2
                painter.fillRect(
                    QRectF(rect.left() + c * cell_size, rect.top() + r * cell_size, cell_size, cell_size),
                    color
                )
        painter.restore()
