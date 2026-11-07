import math
from typing import Optional, Tuple
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QImage, QPixmap, QCursor, QFont
from PyQt6.QtWidgets import QWidget

from ..converter import CropRect
from .tactical_icons import get_pixmap

HANDLE_SIZE = 10
HANDLE_HALF = HANDLE_SIZE / 2


class InteractiveCropWidget(QWidget):
    crop_changed = pyqtSignal(CropRect)
    view_mode_changed = pyqtSignal(str)  # "preview" or "crop"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(280, 240)

        self.source_pixmap: Optional[QPixmap] = None
        self.orig_width = 1
        self.orig_height = 1

        # View mode: "preview" (Live Output Sticker) or "crop" (Source with Crop Box)
        self.view_mode: str = "preview"

        # Normalized crop coordinates in range [0.0, 1.0]
        self.norm_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self.aspect_ratio: Optional[float] = None  # None = Free, 1.0 = Square, etc.

        # Output resolution parameters (stretching & custom dimensions)
        self.target_width: int = 512
        self.target_height: int = 512
        self.is_aspect_locked: bool = True

        self.dragging = False
        self.active_handle = None
        self.drag_start_pos = QPointF()
        self.drag_start_rect = QRectF()

    def set_view_mode(self, mode: str):
        if mode in ("preview", "crop") and self.view_mode != mode:
            self.view_mode = mode
            self.update()
            self.view_mode_changed.emit(self.view_mode)

    def set_image(self, pixmap: Optional[QPixmap], orig_w: int, orig_h: int):
        self.source_pixmap = pixmap
        self.orig_width = max(1, orig_w)
        self.orig_height = max(1, orig_h)
        self.update()

    def set_target_dimensions(self, target_w: Optional[int], target_h: Optional[int], is_locked: bool = True):
        self.target_width = target_w or 512
        self.target_height = target_h or 512
        self.is_aspect_locked = is_locked
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
        """Sets fixed aspect ratio and adjusts crop box."""
        self.aspect_ratio = ratio
        if ratio is not None:
            img_ratio = self.orig_width / self.orig_height
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
        """Returns the scaled image rectangle within widget area for CROP mode."""
        vw = self.width() - 24
        vh = self.height() - 24
        if vw <= 0 or vh <= 0 or not self.source_pixmap:
            return QRectF(12, 12, max(10, self.width() - 24), max(10, self.height() - 24))

        img_w = self.source_pixmap.width()
        img_h = self.source_pixmap.height()
        scale = min(vw / img_w, vh / img_h)

        dw = img_w * scale
        dh = img_h * scale
        dx = (self.width() - dw) / 2
        dy = (self.height() - dh) / 2
        return QRectF(dx, dy, dw, dh)

    def _get_preview_stage_rect(self) -> QRectF:
        """Returns the scaled sticker stage rect matching the exact output aspect ratio."""
        vw = self.width() - 32
        vh = self.height() - 36
        if vw <= 0 or vh <= 0:
            return QRectF(16, 18, 100, 100)

        target_aspect = self.target_width / max(1, self.target_height)
        if vw / vh > target_aspect:
            sh = vh
            sw = sh * target_aspect
        else:
            sw = vw
            sh = sw / target_aspect

        sx = (self.width() - sw) / 2
        sy = (self.height() - sh) / 2
        return QRectF(sx, sy, sw, sh)

    def _get_pill_rects(self) -> Tuple[QRectF, QRectF, QRectF]:
        """Returns (container_rect, preview_btn_rect, crop_btn_rect) for the mode switcher."""
        w_btn = 92
        h_btn = 22
        tot_w = w_btn * 2 + 2
        rx = (self.width() - tot_w) / 2
        ry = 8
        cont = QRectF(rx, ry, tot_w, h_btn)
        r_prev = QRectF(rx, ry, w_btn, h_btn)
        r_crop = QRectF(rx + w_btn + 2, ry, w_btn, h_btn)
        return cont, r_prev, r_crop

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
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # 1. Check click on top mode switcher pill
        cont, r_prev, r_crop = self._get_pill_rects()
        pos = event.position()
        if r_prev.contains(pos):
            self.set_view_mode("preview")
            return
        elif r_crop.contains(pos):
            self.set_view_mode("crop")
            return

        # 2. In PREVIEW mode: clicking stage allows double-click toggle or inspect
        if self.view_mode == "preview":
            return

        # 3. In CROP mode: interact with crop handles or move box
        if not self.source_pixmap:
            return

        disp = self._get_display_rect()
        sc = self._norm_to_screen(self.norm_rect, disp)
        handles = self._get_handle_rects(sc)

        for h_name, h_rect in handles.items():
            if h_rect.contains(pos):
                self.dragging = True
                self.active_handle = h_name
                self.drag_start_pos = pos
                self.drag_start_rect = QRectF(self.norm_rect)
                return

        if sc.contains(pos):
            self.dragging = True
            self.active_handle = "move"
            self.drag_start_pos = pos
            self.drag_start_rect = QRectF(self.norm_rect)

    def mouseDoubleClickEvent(self, event):
        # Double click toggles between preview and crop modes seamlessly
        if self.view_mode == "preview":
            self.set_view_mode("crop")
        else:
            self.set_view_mode("preview")

    def mouseMoveEvent(self, event):
        if self.view_mode != "crop" or not self.source_pixmap:
            cont, r_prev, r_crop = self._get_pill_rects()
            pos = event.position()
            if r_prev.contains(pos) or r_crop.contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            return

        disp = self._get_display_rect()
        sc = self._norm_to_screen(self.norm_rect, disp)
        pos = event.position()

        if not self.dragging:
            cont, r_prev, r_crop = self._get_pill_rects()
            if r_prev.contains(pos) or r_crop.contains(pos):
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                return

            handles = self._get_handle_rects(sc)
            cursor = Qt.CursorShape.ArrowCursor
            if handles["tl"].contains(pos) or handles["br"].contains(pos):
                cursor = Qt.CursorShape.SizeFDiagCursor
            elif handles["tr"].contains(pos) or handles["bl"].contains(pos):
                cursor = Qt.CursorShape.SizeBDiagCursor
            elif handles["t"].contains(pos) or handles["b"].contains(pos):
                cursor = Qt.CursorShape.SizeVerCursor
            elif handles["l"].contains(pos) or handles["r"].contains(pos):
                cursor = Qt.CursorShape.SizeHorCursor
            elif sc.contains(pos):
                cursor = Qt.CursorShape.SizeAllCursor
            self.setCursor(QCursor(cursor))
            return

        # Dragging active handle in normalized coordinates
        dx = (pos.x() - self.drag_start_pos.x()) / max(1.0, disp.width())
        dy = (pos.y() - self.drag_start_pos.y()) / max(1.0, disp.height())

        sr = self.drag_start_rect
        nx, ny, nw, nh = sr.x(), sr.y(), sr.width(), sr.height()

        if self.active_handle == "move":
            nx = max(0.0, min(1.0 - nw, nx + dx))
            ny = max(0.0, min(1.0 - nh, ny + dy))
        else:
            if "l" in self.active_handle:
                new_x = max(0.0, min(nx + nw - 0.05, nx + dx))
                nw = nw + (nx - new_x)
                nx = new_x
            if "r" in self.active_handle:
                nw = max(0.05, min(1.0 - nx, nw + dx))
            if "t" in self.active_handle:
                new_y = max(0.0, min(ny + nh - 0.05, ny + dy))
                nh = nh + (ny - new_y)
                ny = new_y
            if "b" in self.active_handle:
                nh = max(0.05, min(1.0 - ny, nh + dy))

            # Maintain aspect ratio if set
            if self.aspect_ratio:
                img_ratio = self.orig_width / self.orig_height
                target_norm_ratio = self.aspect_ratio / img_ratio
                if self.active_handle in ("l", "r"):
                    nh = nw / target_norm_ratio
                else:
                    nw = nh * target_norm_ratio

        nx = max(0.0, min(1.0 - nw, nx))
        ny = max(0.0, min(1.0 - nh, ny))
        self.norm_rect = QRectF(nx, ny, nw, nh)
        self._emit_crop()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.active_handle = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Deep Obsidian canvas background
        painter.fillRect(self.rect(), QColor("#0A0B0A"))

        if not self.source_pixmap or self.source_pixmap.isNull():
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            pm = get_pixmap("film", color="#2B3026", size=48)
            painter.drawPixmap(int(cx - 24), int(cy - 36), pm)
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
            painter.setPen(QColor("#555B4F"))
            painter.drawText(QRectF(0, cy + 24, float(self.width()), 24.0), Qt.AlignmentFlag.AlignCenter, "No media loaded")
            return

        if self.view_mode == "preview":
            self._paint_preview_mode(painter)
        else:
            self._paint_crop_mode(painter)

    def _paint_preview_mode(self, painter: QPainter):
        """Renders the EXACT live output sticker scaled and stretched in real time."""
        stage = self._get_preview_stage_rect()

        # Checkerboard background for transparency
        self._draw_transparency_grid(painter, stage)

        # Extract cropped portion
        cx = int(round(self.norm_rect.x() * self.source_pixmap.width()))
        cy = int(round(self.norm_rect.y() * self.source_pixmap.height()))
        cw = max(1, int(round(self.norm_rect.width() * self.source_pixmap.width())))
        ch = max(1, int(round(self.norm_rect.height() * self.source_pixmap.height())))
        sub_pix = self.source_pixmap.copy(cx, cy, cw, ch)

        if not sub_pix.isNull():
            # Scale to stage: IgnoreAspectRatio applies the EXACT user stretch/squash!
            scaled_sub = sub_pix.scaled(
                int(round(stage.width())),
                int(round(stage.height())),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(int(round(stage.left())), int(round(stage.top())), scaled_sub)

        # Crisp stage outline
        painter.setPen(QPen(QColor("#2B3026"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(stage)

        # Bottom corner resolution indicator (minimalist, no redundant badges)
        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.setPen(QColor("#9EF41A" if self.is_aspect_locked else "#FFB830"))
        res_text = f"{self.target_width} × {self.target_height} PX"
        painter.drawText(
            QRectF(stage.left(), stage.bottom() + 4, stage.width(), 14),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            res_text
        )

    def _paint_crop_mode(self, painter: QPainter):
        """Renders the full source frame with draggable 8-point crop box."""
        disp = self._get_display_rect()

        # Checkerboard under display rect
        self._draw_transparency_grid(painter, disp)

        # Source pixmap
        scaled_src = self.source_pixmap.scaled(
            int(round(disp.width())), int(round(disp.height())),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(int(round(disp.left())), int(round(disp.top())), scaled_src)

        sc = self._norm_to_screen(self.norm_rect, disp)

        # Darken outside crop
        dim_color = QColor(10, 12, 10, 190)
        painter.fillRect(QRectF(disp.left(), disp.top(), disp.width(), sc.top() - disp.top()), dim_color)
        painter.fillRect(QRectF(disp.left(), sc.bottom(), disp.width(), disp.bottom() - sc.bottom()), dim_color)
        painter.fillRect(QRectF(disp.left(), sc.top(), sc.left() - disp.left(), sc.height()), dim_color)
        painter.fillRect(QRectF(sc.right(), sc.top(), disp.right() - sc.right(), sc.height()), dim_color)

        # Rule-of-thirds grid
        pen_grid = QPen(QColor(158, 244, 26, 60), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        x1 = sc.left() + sc.width() / 3
        x2 = sc.left() + 2 * sc.width() / 3
        y1 = sc.top() + sc.height() / 3
        y2 = sc.top() + 2 * sc.height() / 3
        painter.drawLine(QPointF(x1, sc.top()), QPointF(x1, sc.bottom()))
        painter.drawLine(QPointF(x2, sc.top()), QPointF(x2, sc.bottom()))
        painter.drawLine(QPointF(sc.left(), y1), QPointF(sc.right(), y1))
        painter.drawLine(QPointF(sc.left(), y2), QPointF(sc.right(), y2))

        # Crop Box Border
        painter.setPen(QPen(QColor("#9EF41A"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(sc)

        # Handles
        handles = self._get_handle_rects(sc)
        painter.setPen(QPen(QColor("#121411"), 1.5))
        painter.setBrush(QBrush(QColor("#9EF41A")))
        for _, h_rect in handles.items():
            painter.drawRoundedRect(h_rect, 1.5, 1.5)

        # Corner thumbnail in crop mode
        self._paint_corner_thumbnail(painter)

    def _paint_corner_thumbnail(self, painter: QPainter):
        pv_w = 90
        pv_h = 90
        pv_rect = QRectF(self.width() - pv_w - 12, 34, pv_w, pv_h)
        painter.setPen(QPen(QColor("#2B3026"), 1))
        painter.setBrush(QColor(18, 20, 17, 240))
        painter.drawRoundedRect(pv_rect, 3, 3)

        inner_rect = QRectF(pv_rect.left() + 4, pv_rect.top() + 4, pv_w - 8, pv_h - 8)
        self._draw_transparency_grid(painter, inner_rect)

        cx = int(round(self.norm_rect.x() * self.source_pixmap.width()))
        cy = int(round(self.norm_rect.y() * self.source_pixmap.height()))
        cw = max(1, int(round(self.norm_rect.width() * self.source_pixmap.width())))
        ch = max(1, int(round(self.norm_rect.height() * self.source_pixmap.height())))
        sub_pix = self.source_pixmap.copy(cx, cy, cw, ch)

        if not sub_pix.isNull():
            target_aspect = self.target_width / max(1, self.target_height)
            avail_w = inner_rect.width()
            avail_h = inner_rect.height()
            if avail_w / max(1.0, avail_h) > target_aspect:
                draw_h = avail_h
                draw_w = draw_h * target_aspect
            else:
                draw_w = avail_w
                draw_h = draw_w / target_aspect
            draw_x = inner_rect.left() + (avail_w - draw_w) / 2
            draw_y = inner_rect.top() + (avail_h - draw_h) / 2

            scaled_sub = sub_pix.scaled(
                int(round(draw_w)), int(round(draw_h)),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(int(round(draw_x)), int(round(draw_y)), scaled_sub)

    def _draw_mode_pill(self, painter: QPainter):
        """Draws the top minimalist segmented toggle [ СТИКЕР | КАДРИРОВАНИЕ ]."""
        cont, r_prev, r_crop = self._get_pill_rects()

        # Pill background
        painter.setPen(QPen(QColor("#2B3026"), 1))
        painter.setBrush(QColor(18, 20, 17, 230))
        painter.drawRoundedRect(cont, 3, 3)

        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))

        # Preview tab
        is_prev = (self.view_mode == "preview")
        if is_prev:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#242D1C"))
            painter.drawRoundedRect(r_prev.adjusted(1, 1, -1, -1), 2, 2)
            painter.setPen(QColor("#9EF41A"))
        else:
            painter.setPen(QColor("#92968C"))
        painter.drawText(r_prev, Qt.AlignmentFlag.AlignCenter, "СТИКЕР")

        # Crop tab
        if not is_prev:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#242D1C"))
            painter.drawRoundedRect(r_crop.adjusted(1, 1, -1, -1), 2, 2)
            painter.setPen(QColor("#9EF41A"))
        else:
            painter.setPen(QColor("#92968C"))
        painter.drawText(r_crop, Qt.AlignmentFlag.AlignCenter, "КАДРИРОВАНИЕ")

    def _draw_transparency_grid(self, painter: QPainter, rect: QRectF):
        cell_size = 10
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
