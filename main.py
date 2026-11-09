import sys
import os

# Hide Windows console window when launched from .py directly
if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass
elif sys.platform == "darwin":
    # Ensure standard Homebrew & MacPorts bin paths exist in PATH for ffmpeg discovery
    for extra_path in ["/opt/homebrew/bin", "/usr/local/bin"]:
        if extra_path not in os.environ.get("PATH", "") and os.path.isdir(extra_path):
            os.environ["PATH"] = f"{extra_path}:{os.environ.get('PATH', '')}"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from notaconverter.ui import MainWindow


def main():
    # Setup Application
    app = QApplication(sys.argv)
    app.setApplicationName("NotAconverter")
    app.setApplicationVersion("2.0.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
