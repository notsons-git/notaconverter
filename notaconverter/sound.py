import struct
import math
import io
import sys
import threading

def parse_volume(text: str, default: float = 0.8) -> float:
    """
    Parses user volume string and returns a float in [0.0, 1.0].
    Supports:
      - '99', '99%', '99 %' -> 0.99
      - '.9', '0.9'         -> 0.90
      - '.5', '0.5'         -> 0.50
      - '100', '100%'       -> 1.00
      - '0', '0%'           -> 0.00
      - '.05'               -> 0.05
    """
    raw = text.strip().replace("%", "").replace(",", ".").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        return default

    # If entered as a decimal <= 1.0 (e.g. '.9', '0.85'):
    if ("." in raw or raw.startswith(".")) and val <= 1.0:
        volume = val
    else:
        volume = val / 100.0

    return max(0.0, min(1.0, volume))


def get_soft_chime_wav(volume: float = 0.8) -> bytes:
    sample_rate = 44100
    duration = 0.38
    n_samples = int(sample_rate * duration)
    audio_data = bytearray()

    v = max(0.0, min(1.0, volume))

    # Pleasant, soft, warm harmonic chime: D5 (587.33 Hz) + A5 (880.0 Hz)
    for i in range(n_samples):
        t = i / sample_rate
        attack = min(1.0, t / 0.01)
        env = attack * math.exp(-7.0 * t)
        val = (0.34 * v) * math.sin(2 * math.pi * 587.33 * t) + (0.24 * v) * math.sin(2 * math.pi * 880.0 * t)
        sample = int(val * env * 32767)
        audio_data.extend(struct.pack('<h', max(-32768, min(32767, sample))))

    wav = io.BytesIO()
    data_len = len(audio_data)
    wav.write(b'RIFF')
    wav.write(struct.pack('<I', 36 + data_len))
    wav.write(b'WAVEfmt ')
    wav.write(struct.pack('<IHHIIHH', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    wav.write(b'data')
    wav.write(struct.pack('<I', data_len))
    wav.write(audio_data)

    return wav.getvalue()


def play_completion_sound(volume: float = 0.8):
    """Plays gentle non-intrusive chime asynchronously on Windows with the given volume."""
    if volume <= 0.001:
        return
    if sys.platform == "win32":
        try:
            import winsound
            wav_bytes = get_soft_chime_wav(volume=volume)
            threading.Thread(
                target=lambda: winsound.PlaySound(wav_bytes, winsound.SND_MEMORY),
                daemon=True
            ).start()
        except Exception:
            pass
