import os
import sys
import subprocess
import shutil
from pathlib import Path
from PIL import Image, ImageDraw

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from notaconverter.config import AppConfig, TELEGRAM_MAX_SIDE, TELEGRAM_MAX_BYTES, TELEGRAM_MAX_DURATION
from notaconverter.media_probe import MediaProbe, is_supported_file
from notaconverter.converter import StickerConverter, ItemSettings, CropRect

TEST_DIR = Path("test_fixtures")


def create_test_media():
    TEST_DIR.mkdir(exist_ok=True)

    # 1. Create a transparent PNG
    png_path = TEST_DIR / "test_icon.png"
    im = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    draw.ellipse((100, 100, 700, 500), fill=(117, 87, 255, 255), outline=(255, 255, 255, 255), width=8)
    im.save(png_path)

    # 2. Create an animated GIF
    gif_path = TEST_DIR / "test_anim.gif"
    frames = []
    for i in range(15):
        f = Image.new("RGBA", (300, 300), (20, 20, 30, 255))
        d = ImageDraw.Draw(f)
        d.rectangle((20 + i * 15, 50, 100 + i * 15, 150), fill=(73, 212, 146, 255))
        frames.append(f)
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=100, loop=0)

    # 3. Create a test MP4 video using ffmpeg
    mp4_path = TEST_DIR / "test_video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "testsrc=duration=4:size=1280x720:rate=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(mp4_path)
    ], capture_output=True)

    return png_path, gif_path, mp4_path


def verify_sticker_compliance(output_path: Path):
    assert output_path.exists(), f"Output file does not exist: {output_path}"
    size = output_path.stat().st_size
    print(f"Checking {output_path.name}: {size} bytes ({size / 1024:.1f} KB)")

    # 1. Size constraint
    assert size <= TELEGRAM_MAX_BYTES, f"Size {size} exceeds Telegram max {TELEGRAM_MAX_BYTES}"

    # 2. FFprobe inspection
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,codec_name,duration:format=duration",
        "-select_streams", "v:0",
        "-of", "json",
        str(output_path)
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    import json
    data = json.loads(r.stdout)
    stream = data["streams"][0]

    w = int(stream["width"])
    h = int(stream["height"])
    codec = stream["codec_name"].lower()
    dur = float(stream.get("duration") or data["format"].get("duration") or 0)

    print(f"  Dimensions: {w}x{h}, Codec: {codec}, Duration: {dur:.2f}s")

    # Dimensions check: One side MUST be exactly 512, other <= 512
    assert (w == TELEGRAM_MAX_SIDE and h <= TELEGRAM_MAX_SIDE) or (h == TELEGRAM_MAX_SIDE and w <= TELEGRAM_MAX_SIDE), \
        f"Dimensions invalid: {w}x{h}, one side must be 512"

    # Codec check: VP9
    assert codec == "vp9", f"Codec {codec} is not VP9"

    # Duration check: <= 3.05s
    assert dur <= 3.05, f"Duration {dur} exceeds max 3.0s"

    # Audio check: no audio streams allowed
    cmd_audio = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type",
        "-select_streams", "a",
        "-of", "json",
        str(output_path)
    ]
    r_a = subprocess.run(cmd_audio, capture_output=True, text=True)
    audio_data = json.loads(r_a.stdout)
    assert not audio_data.get("streams"), "Telegram video stickers MUST NOT have any audio streams!"

    print(f"  ✓ PASSED all Telegram technical compliance checks!")


def test_converter():
    print("=== Creating Test Media ===")
    png_path, gif_path, mp4_path = create_test_media()

    config = AppConfig()
    converter = StickerConverter(config)

    print("\n=== Testing PNG Conversion ===")
    info_png = MediaProbe.probe(str(png_path))
    assert info_png is not None
    assert info_png.has_alpha is True
    out_png = TEST_DIR / "sticker_from_png.webm"
    converter.convert(info_png, str(out_png))
    verify_sticker_compliance(out_png)

    print("\n=== Testing GIF Conversion with Crop ===")
    info_gif = MediaProbe.probe(str(gif_path))
    assert info_gif is not None
    out_gif = TEST_DIR / "sticker_from_gif.webm"
    crop_settings = ItemSettings(
        crop=CropRect(x=50, y=50, width=200, height=200) # 1:1 square crop
    )
    converter.convert(info_gif, str(out_gif), item_settings=crop_settings)
    verify_sticker_compliance(out_gif)

    print("\n=== Testing MP4 Conversion with Trimming & Crop ===")
    info_mp4 = MediaProbe.probe(str(mp4_path))
    assert info_mp4 is not None
    out_mp4 = TEST_DIR / "sticker_from_mp4.webm"
    trim_and_crop = ItemSettings(
        trim_start=1.0,
        trim_end=3.5, # 2.5s duration
        crop=CropRect(x=200, y=100, width=800, height=500)
    )
    converter.convert(info_mp4, str(out_mp4), item_settings=trim_and_crop)
    verify_sticker_compliance(out_mp4)

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! The stickers are 100% compliant with Telegram specifications!")


if __name__ == "__main__":
    try:
        test_converter()
    finally:
        # Cleanup test fixtures
        shutil.rmtree(TEST_DIR, ignore_errors=True)
