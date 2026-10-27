import os
import subprocess
import shutil
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable, Tuple

from .config import (
    TELEGRAM_MAX_SIDE,
    TELEGRAM_MAX_DURATION,
    TELEGRAM_MAX_BYTES,
    TELEGRAM_SAFETY_BYTES,
    TELEGRAM_MAX_FPS,
    AppConfig,
)
from .media_probe import MediaInfo, MediaProbe


@dataclass
class CropRect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0


@dataclass
class ItemSettings:
    trim_start: float = 0.0
    trim_end: float = 0.0  # 0.0 means use full/auto clamped
    crop: Optional[CropRect] = None
    fps: int = 30
    enable_unsharp: bool = True
    custom_name: str = ""


class ConversionError(Exception):
    pass


class StickerConverter:
    """
    High-performance, ultra-quality Telegram video sticker encoder.
    Optimizes VP9 / WebM to maximize sharpness and visual fidelity while strictly
    conforming to Telegram's 512px, 3.0s, and 256KB limits.
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig.load()
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def calculate_target_dims(self, orig_w: int, orig_h: int, crop: Optional[CropRect] = None) -> Tuple[int, int]:
        """
        Calculate sticker dimensions so one side is exactly 512 and the other <= 512.
        Both dimensions are even numbers (required by VP9).
        """
        cw = crop.width if (crop and crop.is_valid) else orig_w
        ch = crop.height if (crop and crop.is_valid) else orig_h
        cw = max(2, cw)
        ch = max(2, ch)

        if cw >= ch:
            out_w = TELEGRAM_MAX_SIDE
            scale = TELEGRAM_MAX_SIDE / cw
            out_h = int(round(ch * scale))
            out_h = max(2, min(TELEGRAM_MAX_SIDE, (out_h // 2) * 2))
        else:
            out_h = TELEGRAM_MAX_SIDE
            scale = TELEGRAM_MAX_SIDE / ch
            out_w = int(round(cw * scale))
            out_w = max(2, min(TELEGRAM_MAX_SIDE, (out_w // 2) * 2))

        return out_w, out_h

    def build_video_filter(
        self,
        info: MediaInfo,
        item_settings: ItemSettings,
        target_w: int,
        target_h: int
    ) -> str:
        filters = []

        # 1. Crop if specified
        crop = item_settings.crop
        if crop and crop.is_valid:
            cx = max(0, min(crop.x, info.width - 2))
            cy = max(0, min(crop.y, info.height - 2))
            cw = max(2, min(crop.width, info.width - cx))
            ch = max(2, min(crop.height, info.height - cy))
            # Even coordinates
            cw = (cw // 2) * 2
            ch = (ch // 2) * 2
            filters.append(f"crop={cw}:{ch}:{cx}:{cy}")

        # 2. FPS limit
        target_fps = min(item_settings.fps or self.config.fps, TELEGRAM_MAX_FPS)
        if info.fps > target_fps or info.is_static_image:
            filters.append(f"fps={target_fps}")

        # 3. Lanczos downscaling to exact Telegram sticker dimensions
        filters.append(f"scale={target_w}:{target_h}:flags=lanczos")

        # 4. Sharpening filter to restore micro-contrast and crisp edges for stickers
        if item_settings.enable_unsharp and self.config.enable_unsharp:
            filters.append("unsharp=lx=3:ly=3:la=0.35:cx=3:cy=3:ca=0.0")

        # 5. Set SAR
        filters.append("setsar=1")

        return ",".join(filters)

    def _run_ffmpeg_encode(
        self,
        src: str,
        dest_temp: str,
        vf: str,
        start_time: float,
        duration: float,
        pix_fmt: str,
        crf: Optional[int] = None,
        bitrate_bps: Optional[int] = None,
        two_pass: int = 0,
        passlog_prefix: Optional[str] = None,
        is_static: bool = False,
        cpu_used: int = 1
    ) -> bool:
        if self.is_cancelled:
            return False

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]

        # Loop static image input
        if is_static:
            fps = min(self.config.fps, TELEGRAM_MAX_FPS)
            cmd += ["-loop", "1", "-framerate", str(fps)]

        # Time seek
        if start_time > 0 and not is_static:
            cmd += ["-ss", f"{start_time:.3f}"]

        cmd += ["-i", src]
        cmd += ["-t", f"{duration:.3f}", "-vf", vf, "-c:v", "libvpx-vp9"]

        if crf is not None:
            cmd += ["-crf", str(crf), "-b:v", "0"]
        elif bitrate_bps is not None:
            cmd += [
                "-b:v", str(bitrate_bps),
                "-maxrate", str(int(bitrate_bps * 1.15)),
                "-bufsize", str(int(bitrate_bps * 1.5))
            ]

        # VP9 quality and multithreading settings
        cmd += [
            "-pix_fmt", pix_fmt,
            "-deadline", "good",
            "-cpu-used", str(cpu_used),
            "-row-mt", "1",
            "-tile-columns", "2",
            "-an"  # Must strip audio completely for Telegram stickers!
        ]

        if pix_fmt == "yuva420p":
            cmd += ["-auto-alt-ref", "0"]

        if two_pass == 1:
            cmd += ["-pass", "1", "-passlogfile", passlog_prefix, "-f", "null", "NUL" if os.name == "nt" else "/dev/null"]
        elif two_pass == 2:
            cmd += ["-pass", "2", "-passlogfile", passlog_prefix, "-f", "webm", dest_temp]
        else:
            cmd += ["-f", "webm", dest_temp]

        try:
            if os.path.exists(dest_temp) and two_pass != 1:
                try:
                    os.remove(dest_temp)
                except OSError:
                    pass

            r = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            return r.returncode == 0
        except Exception:
            return False

    def convert(
        self,
        info: MediaInfo,
        output_path: str,
        item_settings: Optional[ItemSettings] = None,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[str, int, float]:
        """
        Converts media into a compliant Telegram WebM video sticker.
        Returns: (output_path, final_size_bytes, final_duration)
        """
        if item_settings is None:
            item_settings = ItemSettings()

        # Calculate duration
        start_time = max(0.0, item_settings.trim_start)
        if info.is_static_image:
            duration = 1.0  # 1s static loop is lightweight and compliant
        else:
            if item_settings.trim_end > start_time:
                duration = item_settings.trim_end - start_time
            elif info.duration > 0:
                duration = info.duration - start_time
            else:
                duration = TELEGRAM_MAX_DURATION

            # Clamp to max Telegram duration (3.0s)
            duration = min(duration, TELEGRAM_MAX_DURATION)
            duration = max(0.1, duration)

        target_w, target_h = self.calculate_target_dims(info.width, info.height, item_settings.crop)
        vf = self.build_video_filter(info, item_settings, target_w, target_h)
        pix_fmt = "yuva420p" if info.has_alpha else "yuv420p"

        temp_output = output_path + ".tmp.webm"
        size_ceiling = min(TELEGRAM_MAX_BYTES, int(self.config.max_size_kb * 1024))
        safety_ceiling = min(TELEGRAM_SAFETY_BYTES, size_ceiling)

        if progress_cb:
            progress_cb(10.0, "Analyzing quality parameters...")

        # Binary search for optimal CRF to squeeze maximum clarity
        # Lower CRF = higher quality. 16 is near-lossless.
        min_crf, max_crf = 16, 50
        best_crf = None
        best_size = 0

        # Quick test at CRF 18 (near-lossless)
        if progress_cb:
            progress_cb(20.0, "Testing high-clarity pass (CRF 18)...")

        ok = self._run_ffmpeg_encode(
            src=info.path,
            dest_temp=temp_output,
            vf=vf,
            start_time=start_time,
            duration=duration,
            pix_fmt=pix_fmt,
            crf=18,
            is_static=info.is_static_image,
            cpu_used=2
        )

        if self.is_cancelled:
            raise ConversionError("Cancelled by user")

        if ok and os.path.exists(temp_output):
            size = os.path.getsize(temp_output)
            if size <= safety_ceiling:
                # CRF 18 fits! We achieved top visual quality.
                best_crf = 18
                best_size = size
            else:
                min_crf = 19

        # If CRF 18 did not fit, binary search CRF
        if best_crf is None:
            low, high = min_crf, max_crf
            passes = 0
            while low <= high and passes < 5:
                if self.is_cancelled:
                    raise ConversionError("Cancelled by user")
                mid = (low + high) // 2
                passes += 1
                if progress_cb:
                    progress_cb(20.0 + passes * 12.0, f"Optimizing CRF ({mid})...")

                ok = self._run_ffmpeg_encode(
                    src=info.path,
                    dest_temp=temp_output,
                    vf=vf,
                    start_time=start_time,
                    duration=duration,
                    pix_fmt=pix_fmt,
                    crf=mid,
                    is_static=info.is_static_image,
                    cpu_used=2
                )
                if not ok or not os.path.exists(temp_output):
                    low = mid + 1
                    continue

                sz = os.path.getsize(temp_output)
                if sz <= safety_ceiling:
                    best_crf = mid
                    best_size = sz
                    high = mid - 1  # Try for even higher quality (lower CRF)
                else:
                    low = mid + 1  # Too big, need higher compression (higher CRF)

        # If CRF search succeeded, re-encode final with cpu-used=1 for peak compression/clarity if needed
        if best_crf is not None:
            if best_crf != 18 or not os.path.exists(temp_output):
                if progress_cb:
                    progress_cb(85.0, f"Encoding crisp master (CRF {best_crf})...")
                self._run_ffmpeg_encode(
                    src=info.path,
                    dest_temp=temp_output,
                    vf=vf,
                    start_time=start_time,
                    duration=duration,
                    pix_fmt=pix_fmt,
                    crf=best_crf,
                    is_static=info.is_static_image,
                    cpu_used=1
                )
        else:
            # Fallback: Constrained 2-pass bitrate allocation to ensure it fits under 256KB
            if progress_cb:
                progress_cb(50.0, "Two-pass bitrate budget pass 1...")
            # Calculate target bitrate to fill ~90% of safety ceiling
            target_bps = int((safety_ceiling * 8 / duration) * 0.88)
            target_bps = max(15000, target_bps)
            passlog = temp_output + ".passlog"

            ok1 = self._run_ffmpeg_encode(
                src=info.path,
                dest_temp=temp_output,
                vf=vf,
                start_time=start_time,
                duration=duration,
                pix_fmt=pix_fmt,
                bitrate_bps=target_bps,
                two_pass=1,
                passlog_prefix=passlog,
                is_static=info.is_static_image,
                cpu_used=2
            )
            if progress_cb:
                progress_cb(75.0, "Two-pass bitrate budget pass 2...")
            ok2 = self._run_ffmpeg_encode(
                src=info.path,
                dest_temp=temp_output,
                vf=vf,
                start_time=start_time,
                duration=duration,
                pix_fmt=pix_fmt,
                bitrate_bps=target_bps,
                two_pass=2,
                passlog_prefix=passlog,
                is_static=info.is_static_image,
                cpu_used=1
            )
            # Cleanup passlog
            for p in Path(os.path.dirname(output_path)).glob(Path(passlog).name + "*"):
                try:
                    p.unlink()
                except OSError:
                    pass

        if not os.path.exists(temp_output):
            raise ConversionError("FFmpeg failed to produce output file.")

        final_size = os.path.getsize(temp_output)
        if final_size > TELEGRAM_MAX_BYTES:
            try:
                os.remove(temp_output)
            except OSError:
                pass
            raise ConversionError(f"Sticker size ({final_size // 1024} KB) exceeded Telegram limit (256 KB).")

        # Move temp to final destination
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        os.replace(temp_output, output_path)

        if progress_cb:
            progress_cb(100.0, f"Completed • {final_size // 1024} KB")

        return output_path, final_size, duration
