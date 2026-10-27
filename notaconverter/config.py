import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any

CONFIG_PATH = Path.home() / ".notaconverter.json"

# Telegram Video Sticker specifications
TELEGRAM_MAX_SIDE = 512
TELEGRAM_MAX_DURATION = 3.0
TELEGRAM_MAX_BYTES = 256 * 1024  # 262,144 bytes
TELEGRAM_SAFETY_BYTES = 252 * 1024  # 258,048 bytes (safety margin against rejection)
TELEGRAM_MAX_FPS = 30

@dataclass
class AppConfig:
    output_mode: str = "first_file"  # "first_file" or "custom"
    custom_folder: str = ""
    max_side: int = 512
    max_duration: float = 3.0
    fps: int = 30
    max_size_kb: int = 252
    quality_preset: str = "ultra"  # "ultra" (maximum sharpness/Lanczos+unsharp), "balanced", "fast"
    enable_unsharp: bool = True
    concurrency: int = 2  # simultaneous encodes
    keep_names: bool = True
    overwrite: bool = True
    open_after: bool = False
    play_sound: bool = True
    sound_volume_str: str = "80%"
    loop_output: bool = True
    auto_fit_duration: bool = True  # clamp duration > 3.0s to 3.0s automatically
    
    @classmethod
    def load(cls) -> "AppConfig":
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**valid_fields)
            except Exception:
                pass
        return cls()

    def save(self):
        try:
            CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
