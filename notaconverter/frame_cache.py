import os
import io
import subprocess
import threading
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from PIL import Image, ImageSequence

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage


def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Convert PIL RGBA image to QImage safely without shared buffer issues."""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, 4 * pil_img.width,
                  QImage.Format.Format_RGBA8888)
    return qimg.copy()


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Convert PIL RGBA image to QPixmap (call on GUI thread)."""
    return QPixmap.fromImage(pil_to_qimage(pil_img))


class FrameCache(QObject):
    """
    Efficient frame caching for video/GIF preview.

    - GIF/WEBP: decodes ALL frames via PIL at load time (very fast, no ffmpeg).
    - Video (MP4/MOV/etc.): extracts N evenly-spaced frames in one ffmpeg call
      using a background thread, so the UI never blocks.

    Playback and scrubbing always read from the cache — zero per-frame subprocess calls.
    """

    frames_ready = pyqtSignal()          # emitted when background extraction finishes
    frame_extracted = pyqtSignal(float)   # emitted per-frame during extraction (progress)
    _worker_finished = pyqtSignal(list, list)  # internal signal to marshal frames to GUI thread

    # Max frames to cache per file
    MAX_VIDEO_CACHE_FRAMES = 90  # 3s × 30fps

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames: List[Tuple[float, QPixmap]] = []  # [(timestamp, pixmap), ...]
        self._pil_frames: List[Tuple[float, Image.Image]] = []  # raw PIL backup for crop widget
        self._duration: float = 0.0
        self._source_path: str = ""
        self._orig_w: int = 1
        self._orig_h: int = 1
        self._loading = False
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._worker_finished.connect(self._on_worker_finished)

    @property
    def is_loading(self) -> bool:
        return self._loading

    @property
    def frame_count(self) -> int:
        with self._lock:
            return len(self._frames)

    @property
    def duration(self) -> float:
        return self._duration

    def cancel(self):
        """Cancel any ongoing background extraction."""
        self._cancel.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def clear(self):
        self.cancel()
        with self._lock:
            self._frames.clear()
            self._pil_frames.clear()
        self._source_path = ""
        self._duration = 0.0

    def load(self, path: str, duration: float, orig_w: int, orig_h: int,
             is_animated_image: bool, max_preview_size: Tuple[int, int] = (480, 480)):
        """
        Start loading frames for the given file.
        For GIF/WEBP — synchronous PIL decode (typically < 50ms).
        For video — background ffmpeg extraction.
        """
        self.cancel()
        with self._lock:
            self._frames.clear()
            self._pil_frames.clear()

        self._source_path = path
        self._duration = max(0.1, duration)
        self._orig_w = orig_w
        self._orig_h = orig_h
        self._cancel.clear()

        ext = Path(path).suffix.lower()

        if is_animated_image and ext in (".gif", ".webp"):
            self._load_animated_image_sync(path, max_preview_size)
            self.frames_ready.emit()
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".ico", ".jfif", ".avif"):
            self._load_static_image_sync(path, max_preview_size)
            self.frames_ready.emit()
        else:
            # Video: extract in background thread
            self._loading = True
            self._thread = threading.Thread(
                target=self._extract_video_frames_bg,
                args=(path, duration, max_preview_size),
                daemon=True
            )
            self._thread.start()

    def get_frame_at(self, timestamp: float) -> Optional[QPixmap]:
        """Get the nearest cached QPixmap for the given timestamp. O(1)-ish via bisect."""
        with self._lock:
            if not self._frames:
                return None
            # Binary search for nearest frame
            lo, hi = 0, len(self._frames) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if self._frames[mid][0] < timestamp:
                    lo = mid + 1
                else:
                    hi = mid
            # Check if previous frame is closer
            best = lo
            if best > 0:
                if abs(self._frames[best - 1][0] - timestamp) < abs(self._frames[best][0] - timestamp):
                    best = best - 1
            return self._frames[best][1]

    def get_pil_frame_at(self, timestamp: float) -> Optional[Image.Image]:
        """Get the nearest cached PIL Image for the given timestamp."""
        with self._lock:
            if not self._pil_frames:
                return None
            lo, hi = 0, len(self._pil_frames) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if self._pil_frames[mid][0] < timestamp:
                    lo = mid + 1
                else:
                    hi = mid
            best = lo
            if best > 0:
                if abs(self._pil_frames[best - 1][0] - timestamp) < abs(self._pil_frames[best][0] - timestamp):
                    best = best - 1
            return self._pil_frames[best][1]

    # ──── Animated GIF / WEBP (synchronous, fast) ────

    def _load_animated_image_sync(self, path: str, max_size: Tuple[int, int]):
        """Decode all GIF/WEBP frames using PIL. Typically < 100ms for small GIFs."""
        try:
            with Image.open(path) as im:
                current_ms = 0.0
                frames = []
                pil_frames = []
                for i, frame in enumerate(ImageSequence.Iterator(im)):
                    if self._cancel.is_set():
                        return
                    d = frame.info.get("duration", 100)
                    if d <= 0:
                        d = 100
                    timestamp = current_ms / 1000.0

                    rgba = frame.convert("RGBA").copy()
                    pil_frames.append((timestamp, rgba))

                    thumb = rgba.copy()
                    thumb.thumbnail(max_size, Image.Resampling.BILINEAR)
                    pix = pil_to_qpixmap(thumb)
                    frames.append((timestamp, pix))

                    current_ms += d
                    if len(frames) >= 300:  # safety cap
                        break

                with self._lock:
                    self._frames = frames
                    self._pil_frames = pil_frames
                    if frames:
                        self._duration = frames[-1][0] + (d / 1000.0)
        except Exception:
            pass

    # ──── Static image (synchronous) ────

    def _load_static_image_sync(self, path: str, max_size: Tuple[int, int]):
        try:
            im = Image.open(path).convert("RGBA")
            pil_copy = im.copy()

            thumb = im.copy()
            thumb.thumbnail(max_size, Image.Resampling.BILINEAR)
            pix = pil_to_qpixmap(thumb)

            with self._lock:
                self._frames = [(0.0, pix)]
                self._pil_frames = [(0.0, pil_copy)]
                self._duration = 1.0
        except Exception:
            pass

    # ──── Video extraction (background thread, one ffmpeg call) ────

    def _extract_video_frames_bg(self, path: str, duration: float, max_size: Tuple[int, int]):
        """
        Extract evenly-spaced frames from a video using ONE ffmpeg process.
        Reads raw RGB frames via pipe — no temp files, no repeated subprocess spawns.
        """
        try:
            num_frames = min(self.MAX_VIDEO_CACHE_FRAMES, max(10, int(duration * 15)))
            # Thumbnail size for preview
            tw, th = max_size

            # Scale filter to fit within max_size keeping aspect ratio
            scale_filter = (
                f"scale='if(gt(iw,ih),min({tw},iw),-2)':'if(gt(iw,ih),-2,min({th},ih))'"
                f":flags=fast_bilinear"
            )
            # FPS filter to extract exactly num_frames over the duration
            target_fps = num_frames / max(0.1, duration)
            target_fps = min(30.0, max(1.0, target_fps))

            vf = f"fps={target_fps:.4f},{scale_filter}"

            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", path,
                "-vf", vf,
                "-pix_fmt", "rgba",
                "-f", "rawvideo",
                "-"
            ]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )

            # We need to know the output frame dimensions.
            # First, probe the output size after scaling.
            out_w, out_h = self._probe_scaled_size(path, vf)
            if out_w <= 0 or out_h <= 0:
                # Fallback: use original dimensions clamped
                from .media_probe import MediaProbe
                info = MediaProbe.probe(path)
                if info:
                    out_w, out_h = info.width, info.height
                else:
                    out_w, out_h = 512, 512
                # Apply scale logic manually
                if out_w > out_h:
                    if out_w > tw:
                        out_h = int(out_h * tw / out_w)
                        out_w = tw
                else:
                    if out_h > th:
                        out_w = int(out_w * th / out_h)
                        out_h = th
                out_w = max(2, (out_w // 2) * 2)
                out_h = max(2, (out_h // 2) * 2)

            frame_bytes = out_w * out_h * 4  # RGBA
            frame_index = 0
            qimages = []
            pil_frames = []

            while not self._cancel.is_set():
                raw = b""
                while len(raw) < frame_bytes:
                    chunk = proc.stdout.read(frame_bytes - len(raw))
                    if not chunk:
                        break
                    raw += chunk

                if len(raw) < frame_bytes:
                    break  # End of stream

                timestamp = frame_index / max(0.01, target_fps)

                try:
                    pil_img = Image.frombytes("RGBA", (out_w, out_h), raw)
                    pil_frames.append((timestamp, pil_img.copy()))
                    qimg = pil_to_qimage(pil_img)
                    qimages.append((timestamp, qimg))
                except Exception:
                    pass

                frame_index += 1

            proc.stdout.close()
            proc.wait(timeout=3)

        except Exception:
            pass
        finally:
            if not self._cancel.is_set():
                self._worker_finished.emit(qimages, pil_frames)
            else:
                self._loading = False

    def _on_worker_finished(self, qimages: List[Tuple[float, QImage]], pil_frames: List[Tuple[float, Image.Image]]):
        """Called on GUI thread via Qt signal when video extraction finishes."""
        if self._cancel.is_set():
            self._loading = False
            return
        pix_frames = []
        for t, qimg in qimages:
            pix_frames.append((t, QPixmap.fromImage(qimg)))
        with self._lock:
            self._frames = pix_frames
            self._pil_frames = pil_frames
        self._loading = False
        self.frames_ready.emit()

    def _probe_scaled_size(self, path: str, vf: str) -> Tuple[int, int]:
        """Determine scaled preview dimensions using ffprobe."""
        cmd2 = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            path
        ]
        try:
            r2 = subprocess.run(
                cmd2, capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            parts = r2.stdout.strip().split("x")
            if len(parts) == 2:
                ow, oh = int(parts[0]), int(parts[1])
                tw, th = 480, 480
                if ow > oh:
                    if ow > tw:
                        oh = int(oh * tw / ow)
                        ow = tw
                else:
                    if oh > th:
                        ow = int(ow * th / oh)
                        oh = th
                ow = max(2, (ow // 2) * 2)
                oh = max(2, (oh // 2) * 2)
                return ow, oh
        except Exception:
            pass

        return 0, 0
