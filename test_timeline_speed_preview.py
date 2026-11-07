import os
import sys
import subprocess
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from notaconverter.config import AppConfig, TELEGRAM_MAX_SIDE, TELEGRAM_MAX_BYTES, TELEGRAM_MAX_DURATION
from notaconverter.media_probe import MediaProbe, MediaInfo
from notaconverter.converter import StickerConverter, ItemSettings, CropRect
from notaconverter.widgets.timeline_slider import TimelineRangeSlider
from notaconverter.widgets.crop_overlay import InteractiveCropWidget
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPixmap, QImage, QColor

def test_timeline_speed_coordinates():
    print("--- Testing Timeline Speed Coordinates ---")
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. 12-second source file
    source_dur = 12.0

    # At 1x:
    speed = 1.0
    eff_dur = source_dur / speed
    assert eff_dur == 12.0, f"Expected 12.0s, got {eff_dur}"
    slider = TimelineRangeSlider()
    slider.set_speed(speed)
    slider.set_duration(eff_dur, default_clamp_3s=False)
    slider.set_range(0.0, 3.0)
    assert abs(slider.total_duration - 12.0) < 1e-4
    assert abs(slider.selected_duration - 3.0) < 1e-4

    # Output selection 0.0 - 3.0s maps to source:
    src_start = slider.start_time * speed
    src_end = slider.end_time * speed
    assert abs(src_start - 0.0) < 1e-4
    assert abs(src_end - 3.0) < 1e-4
    print("  ✓ 1x: 12.0s timeline, 3s selection = 3s source slice")

    # At 2x:
    speed = 2.0
    eff_dur = source_dur / speed
    assert eff_dur == 6.0, f"Expected 6.0s, got {eff_dur}"
    slider.set_speed(speed)
    slider.set_duration(eff_dur, default_clamp_3s=False)
    slider.set_range(0.0, 3.0)
    assert abs(slider.total_duration - 6.0) < 1e-4
    assert abs(slider.selected_duration - 3.0) < 1e-4

    # Output selection 0.0 - 3.0s maps to source:
    src_start = slider.start_time * speed
    src_end = slider.end_time * speed
    assert abs(src_start - 0.0) < 1e-4
    assert abs(src_end - 6.0) < 1e-4
    print("  ✓ 2x: 6.0s timeline, 3s selection = 6s source slice -> 3s output")

    # At 3x:
    speed = 3.0
    eff_dur = source_dur / speed
    assert eff_dur == 4.0, f"Expected 4.0s, got {eff_dur}"
    slider.set_speed(speed)
    slider.set_duration(eff_dur, default_clamp_3s=False)
    slider.set_range(0.0, 3.0)
    assert abs(slider.total_duration - 4.0) < 1e-4
    assert abs(slider.selected_duration - 3.0) < 1e-4

    src_start = slider.start_time * speed
    src_end = slider.end_time * speed
    assert abs(src_start - 0.0) < 1e-4
    assert abs(src_end - 9.0) < 1e-4
    print("  ✓ 3x: 4.0s timeline, 3s selection = 9s source slice -> 3s output")

    # At 6x:
    speed = 6.0
    eff_dur = source_dur / speed
    assert eff_dur == 2.0, f"Expected 2.0s, got {eff_dur}"
    slider.set_speed(speed)
    slider.set_duration(eff_dur, default_clamp_3s=False)
    slider.set_range(0.0, 2.0)
    assert abs(slider.total_duration - 2.0) < 1e-4
    assert abs(slider.selected_duration - 2.0) < 1e-4

    src_start = slider.start_time * speed
    src_end = slider.end_time * speed
    assert abs(src_start - 0.0) < 1e-4
    assert abs(src_end - 12.0) < 1e-4
    print("  ✓ 6x: 2.0s timeline, 2s selection captures FULL 12s source -> 2s output")

def test_crop_preview_viewport():
    print("--- Testing Viewport Live Preview & Mode Switcher ---")
    app = QApplication.instance() or QApplication(sys.argv)
    widget = InteractiveCropWidget()
    widget.resize(600, 500)

    # Test modes
    assert widget.view_mode == "preview"
    widget.set_view_mode("crop")
    assert widget.view_mode == "crop"
    widget.set_view_mode("preview")
    assert widget.view_mode == "preview"

    # Test resolution change and aspect ratio lock
    widget.set_target_dimensions(512, 512, is_locked=True)
    assert widget.target_width == 512
    assert widget.target_height == 512
    assert widget.is_aspect_locked is True

    # Squash to 512x256 unlocked
    widget.set_target_dimensions(512, 256, is_locked=False)
    assert widget.target_width == 512
    assert widget.target_height == 256
    assert widget.is_aspect_locked is False

    stage = widget._get_preview_stage_rect()
    stage_aspect = stage.width() / stage.height()
    target_aspect = 512.0 / 256.0
    assert abs(stage_aspect - target_aspect) < 0.05, f"Stage aspect {stage_aspect} does not match {target_aspect}"
    print(f"  ✓ Live Preview Stage rectangle: {stage.width():.1f}x{stage.height():.1f} matches aspect {target_aspect}")

def test_converter_filter_and_export():
    print("--- Testing Real 12-Second Video Speed Export ---")
    fixtures_dir = Path("test_fixtures")
    fixtures_dir.mkdir(exist_ok=True)
    src_12s = fixtures_dir / "test_12s.mp4"

    # Generate 12-second test video if not present
    if not src_12s.exists():
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=duration=12:size=640x360:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(src_12s)
        ], capture_output=True, check=True)

    probe = MediaProbe()
    info = probe.probe(str(src_12s))
    assert info is not None
    assert abs(info.duration - 12.0) < 0.5, f"Expected ~12s video, got {info.duration}s"

    cfg = AppConfig()
    converter = StickerConverter(cfg)

    # Convert at 2x: output 3s from 6s slice
    settings_2x = ItemSettings(
        trim_start=0.0,
        trim_end=6.0,
        speed=2.0,
        custom_width=512,
        custom_height=512
    )
    vf_2x = converter.build_video_filter(info, settings_2x, 512, 288)
    assert "setpts=(PTS-STARTPTS)/2.0000" in vf_2x, f"Filter does not contain expected setpts: {vf_2x}"
    print(f"  ✓ 2x Video filter verified: {vf_2x}")

    out_2x = fixtures_dir / "out_12s_2x.webm"
    res_path, sz, dur = converter.convert(info, str(out_2x), settings_2x)
    assert abs(dur - 3.0) <= 0.15, f"Expected ~3.0s output, got {dur}s"
    assert sz <= TELEGRAM_MAX_BYTES, f"Size {sz} exceeds ceiling"
    print(f"  ✓ 2x Export successful: {res_path} ({sz} bytes, duration {dur:.2f}s)")

    # Convert at 6x: output 2s from whole 12s source
    settings_6x = ItemSettings(
        trim_start=0.0,
        trim_end=12.0,
        speed=6.0,
        custom_width=512,
        custom_height=512
    )
    vf_6x = converter.build_video_filter(info, settings_6x, 512, 288)
    assert "setpts=(PTS-STARTPTS)/6.0000" in vf_6x, f"Filter does not contain expected setpts: {vf_6x}"
    print(f"  ✓ 6x Video filter verified: {vf_6x}")

    out_6x = fixtures_dir / "out_12s_6x.webm"
    res_path_6x, sz_6x, dur_6x = converter.convert(info, str(out_6x), settings_6x)
    assert abs(dur_6x - 2.0) <= 0.15, f"Expected ~2.0s output, got {dur_6x}s"
    assert sz_6x <= TELEGRAM_MAX_BYTES, f"Size {sz_6x} exceeds ceiling"
    print(f"  ✓ 6x Export successful: {res_path_6x} ({sz_6x} bytes, duration {dur_6x:.2f}s)")

if __name__ == "__main__":
    test_timeline_speed_coordinates()
    test_crop_preview_viewport()
    test_converter_filter_and_export()
    print("\nALL TIMELINE SPEED & VIEWPORT TESTS PASSED SUCCESSFULLY!")
