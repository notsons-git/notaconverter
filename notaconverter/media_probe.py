import os
import subprocess
import json
import shutil
import functools
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple
from PIL import Image, ImageSequence

SUPPORTED_VIDEO_EXTS = {
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".flv", ".wmv", ".m4v",
    ".ts", ".3gp", ".ogv", ".mpg", ".mpeg"
}
SUPPORTED_IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif",
    ".ico", ".jfif", ".avif"
}
ALL_SUPPORTED_EXTS = SUPPORTED_VIDEO_EXTS | SUPPORTED_IMAGE_EXTS

def is_supported_file(path: str) -> bool:
    return Path(path).suffix.lower() in ALL_SUPPORTED_EXTS and os.path.isfile(path)

@dataclass
class MediaInfo:
    path: str
    filename: str
    ext: str
    is_video: bool
    is_animated: bool
    is_static_image: bool
    width: int
    height: int
    duration: float
    fps: float
    has_alpha: bool
    file_size_bytes: int
    codec: str = ""

    @property
    def display_duration(self) -> str:
        if self.duration <= 0 or self.is_static_image:
            return "Static"
        mins = int(self.duration // 60)
        secs = self.duration % 60
        if mins > 0:
            return f"{mins}:{secs:04.1f}s"
        return f"{secs:.2f}s"

    @property
    def display_size(self) -> str:
        n = self.file_size_bytes
        if n < 1024:
            return f"{n} B"
        if n < 1024 ** 2:
            return f"{n / 1024:.1f} KB"
        return f"{n / 1024 ** 2:.1f} MB"

    @property
    def aspect_ratio(self) -> float:
        if self.height > 0:
            return self.width / self.height
        return 1.0


class MediaProbe:
    _cache = {}

    @classmethod
    def probe(cls, path: str) -> Optional[MediaInfo]:
        if path in cls._cache:
            return cls._cache[path]

        p = Path(path)
        if not p.is_file():
            return None

        ext = p.suffix.lower()
        size_bytes = os.path.getsize(path)
        is_video_ext = ext in SUPPORTED_VIDEO_EXTS

        # Check with Pillow first for image/gif
        if not is_video_ext:
            try:
                with Image.open(path) as im:
                    width, height = im.size
                    is_animated = bool(getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1)
                    has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
                    
                    duration = 0.0
                    fps = 30.0
                    if is_animated:
                        # compute gif / webp duration
                        total_ms = 0
                        frame_count = 0
                        for frame in ImageSequence.Iterator(im):
                            d = frame.info.get("duration", 100)
                            if d <= 0:
                                d = 100
                            total_ms += d
                            frame_count += 1
                            if frame_count > 600:
                                break
                        duration = total_ms / 1000.0
                        fps = round(frame_count / max(0.1, duration), 1) if duration > 0 else 30.0

                    info = MediaInfo(
                        path=path,
                        filename=p.name,
                        ext=ext,
                        is_video=False,
                        is_animated=is_animated,
                        is_static_image=not is_animated,
                        width=width,
                        height=height,
                        duration=duration,
                        fps=fps,
                        has_alpha=has_alpha,
                        file_size_bytes=size_bytes,
                        codec=im.format or ext.replace(".", "").upper()
                    )
                    cls._cache[path] = info
                    return info
            except Exception:
                # If Pillow failed on image, fallback to ffprobe below
                pass

        # Use ffprobe for video or complex files
        info = cls._probe_ffprobe(path, ext, size_bytes)
        if info:
            cls._cache[path] = info
        return info

    @classmethod
    def _probe_ffprobe(cls, path: str, ext: str, size_bytes: int) -> Optional[MediaInfo]:
        if not shutil.which("ffprobe"):
            return None
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,r_frame_rate,duration,pix_fmt,codec_name:format=duration",
            "-select_streams", "v:0",
            "-of", "json",
            path
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            data = json.loads(r.stdout)
            streams = data.get("streams", [])
            fmt = data.get("format", {})
            if not streams:
                return None
            v = streams[0]
            w = int(v.get("width", 512))
            h = int(v.get("height", 512))
            pix_fmt = str(v.get("pix_fmt", "")).lower()
            codec = str(v.get("codec_name", "")).upper()

            # Duration check
            dur_str = v.get("duration") or fmt.get("duration") or "0"
            try:
                duration = float(dur_str)
            except ValueError:
                duration = 0.0

            # FPS check
            r_fps = v.get("r_frame_rate", "30/1")
            try:
                num, den = map(float, r_fps.split("/"))
                fps = round(num / den, 2) if den != 0 else 30.0
            except Exception:
                fps = 30.0

            has_alpha = any(a in pix_fmt for a in ("alpha", "yuva", "rgba", "bgra", "argb", "abgr", "gbra"))
            is_video = duration > 0.05 or ext in SUPPORTED_VIDEO_EXTS
            is_animated = is_video and duration > 0.1

            return MediaInfo(
                path=path,
                filename=Path(path).name,
                ext=ext,
                is_video=is_video,
                is_animated=is_animated,
                is_static_image=not is_animated and not is_video,
                width=w,
                height=h,
                duration=duration,
                fps=fps,
                has_alpha=has_alpha,
                file_size_bytes=size_bytes,
                codec=codec
            )
        except Exception:
            return None

    @classmethod
    def extract_frame(cls, path: str, timestamp: float = 0.0, max_size: Optional[Tuple[int, int]] = None) -> Optional[Image.Image]:
        """Extract a single frame at the given timestamp as a PIL RGBA Image."""
        ext = Path(path).suffix.lower()
        if ext in SUPPORTED_IMAGE_EXTS and ext != ".gif" and ext != ".webp":
            try:
                im = Image.open(path).convert("RGBA")
                if max_size:
                    im.thumbnail(max_size, Image.Resampling.BILINEAR)
                return im
            except Exception:
                pass

        if ext in (".gif", ".webp"):
            try:
                with Image.open(path) as im:
                    if getattr(im, "is_animated", False):
                        # Approximate target frame from timestamp
                        target_ms = timestamp * 1000.0
                        curr_ms = 0
                        best_frame = None
                        for frame in ImageSequence.Iterator(im):
                            d = frame.info.get("duration", 100)
                            if d <= 0:
                                d = 100
                            best_frame = frame.convert("RGBA").copy()
                            if curr_ms + d >= target_ms:
                                break
                            curr_ms += d
                        if best_frame:
                            if max_size:
                                best_frame.thumbnail(max_size, Image.Resampling.BILINEAR)
                            return best_frame
                    else:
                        im = im.convert("RGBA")
                        if max_size:
                            im.thumbnail(max_size, Image.Resampling.BILINEAR)
                        return im
            except Exception:
                pass

        # For video or fallback, use ffmpeg
        if not shutil.which("ffmpeg"):
            return None

        # Build ffmpeg fast frame grab
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{max(0.0, timestamp):.3f}",
            "-i", path,
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "bmp",
            "-"
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if r.returncode == 0 and r.stdout:
                import io
                im = Image.open(io.BytesIO(r.stdout)).convert("RGBA")
                if max_size:
                    im.thumbnail(max_size, Image.Resampling.BILINEAR)
                return im
        except Exception:
            pass
        return None
