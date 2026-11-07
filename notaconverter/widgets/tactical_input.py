import re
from typing import Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFocusEvent, QKeyEvent
from PyQt6.QtWidgets import QLineEdit, QWidget


class TacticalNumberEdit(QLineEdit):
    """
    Tactical Obsidian Numerical Input Field.
    
    Professional NLE numeric input behavior:
    - Allows full select-all (Ctrl+A), clearing (empty string), Backspace/Delete without immediate interference.
    - Zero intermediate validation blocking keystrokes.
    - Automatically strips unit on focus and selects all for fast replacement.
    - Validates strictly upon editing completion: Enter key or Focus-Out.
    - If valid: clamps to [min_val, max_val], rounds/evens, emits valueChanged.
    - If invalid or empty: flashes subtle red border and restores last valid value.
    - Supports Up / Down arrow keys for incremental stepping.
    """
    valueChanged = pyqtSignal(float)

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 1000.0,
        decimals: int = 0,
        step: float = 1.0,
        unit: str = "",
        even_only: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.min_value: float = float(min_value)
        self.max_value: float = float(max_value)
        self.decimals: int = int(decimals)
        self.step: float = float(step)
        self.unit: str = unit.strip()
        self.even_only: bool = even_only

        self._current_value: float = self._clamp_and_format(value)
        self._last_valid_value: float = self._current_value

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont("Consolas", 8))
        self._apply_base_style()
        self._update_text(formatted=True)

        self.returnPressed.connect(self._on_return_pressed)

    def _apply_base_style(self):
        self.setStyleSheet("""
            QLineEdit {
                background-color: #121411;
                border: 1px solid #2B3026;
                border-radius: 3px;
                color: #E8EBE4;
                padding: 3px 6px;
                font-size: 8.5pt;
                font-family: "Consolas", monospace;
                min-height: 22px;
            }
            QLineEdit:hover {
                border-color: #3E4636;
            }
            QLineEdit:focus {
                border-color: #9EF41A;
                background-color: #151813;
                color: #FFFFFF;
            }
            QLineEdit:disabled {
                background-color: #0E100D;
                color: #555B4F;
                border: 1px solid #1C201A;
            }
        """)

    def value(self) -> float:
        return self._current_value

    def int_value(self) -> int:
        return int(round(self._current_value))

    def setRange(self, min_val: float, max_val: float):
        self.min_value = float(min_val)
        self.max_value = float(max_val)
        self.setValue(self._current_value)

    def setValue(self, val: float, emit_signal: bool = False):
        val = self._clamp_and_format(val)
        prev = self._current_value
        self._current_value = val
        self._last_valid_value = val
        self._update_text(formatted=not self.hasFocus())
        if emit_signal and abs(prev - val) > 1e-6:
            self.valueChanged.emit(self._current_value)

    def _clamp_and_format(self, val: float) -> float:
        val = max(self.min_value, min(self.max_value, float(val)))
        if self.decimals == 0:
            int_val = int(round(val))
            if self.even_only:
                int_val = (int_val // 2) * 2
                int_val = max(int(self.min_value), min(int(self.max_value), int_val))
            return float(int_val)
        return round(val, self.decimals)

    def _update_text(self, formatted: bool = True):
        if self.decimals == 0:
            num_str = str(int(round(self._current_value)))
        else:
            num_str = f"{self._current_value:.{self.decimals}f}"

        if formatted and self.unit:
            self.setText(f"{num_str} {self.unit}")
        else:
            self.setText(num_str)

    def focusInEvent(self, event: QFocusEvent):
        super().focusInEvent(event)
        # Strip unit so the user can easily edit or replace the pure number
        self._update_text(formatted=False)
        # Select all content so any keypress or backspace clears/replaces instantly
        QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, event: QFocusEvent):
        self._commit_edit()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            self._nudge(self.step)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Down:
            self._nudge(-self.step)
            event.accept()
            return
        super().keyPressEvent(event)

    def _nudge(self, delta: float):
        try:
            cur = self._parse_text(self.text())
        except ValueError:
            cur = self._current_value
        new_val = self._clamp_and_format(cur + delta)
        self.setValue(new_val, emit_signal=True)
        self.selectAll()

    def _parse_text(self, raw: str) -> float:
        cleaned = raw.strip()
        # Remove known unit suffix or symbols like px, s, x, %, kb, etc.
        cleaned = re.sub(r"[^\d\.\,\-]", "", cleaned)
        cleaned = cleaned.replace(",", ".")
        if not cleaned or cleaned == "-" or cleaned == ".":
            raise ValueError("Empty or invalid numeric string")
        return float(cleaned)

    def _on_return_pressed(self):
        self._commit_edit()
        self.clearFocus()

    def _commit_edit(self):
        raw = self.text()
        try:
            parsed = self._parse_text(raw)
            clamped = self._clamp_and_format(parsed)
            prev = self._current_value
            self._current_value = clamped
            self._last_valid_value = clamped
            self._update_text(formatted=True)
            self._clear_error()
            if abs(prev - clamped) > 1e-6:
                self.valueChanged.emit(clamped)
        except ValueError:
            # Revert to last valid value and flash subtle error border
            self._current_value = self._last_valid_value
            self._update_text(formatted=True)
            self._flash_error()

    def _flash_error(self):
        self.setStyleSheet("""
            QLineEdit {
                background-color: #1A1312;
                border: 1px solid #FF4D4D;
                border-radius: 3px;
                color: #FFAAAA;
                padding: 3px 6px;
                font-size: 8.5pt;
                font-family: "Consolas", monospace;
                min-height: 22px;
            }
        """)
        QTimer.singleShot(1000, self._apply_base_style)

    def _clear_error(self):
        self._apply_base_style()
