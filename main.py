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
