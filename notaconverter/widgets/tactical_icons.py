from pathlib import Path
from typing import Dict, Tuple, Optional
from PyQt6.QtCore import Qt, QSize, QByteArray
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

_ICONS_DIR = Path(__file__).parent.parent / "assets" / "icons"
if not _ICONS_DIR.exists():
    _ICONS_DIR = Path(__file__).parent.parent.parent / "assets" / "icons"

_SVG_CACHE: Dict[str, str] = {}
_PIXMAP_CACHE: Dict[Tuple[str, str, int], QPixmap] = {}
_ICON_CACHE: Dict[Tuple[str, str, str, str, int], QIcon] = {}


def _load_svg(name: str) -> Optional[str]:
    clean_name = name if name.endswith(".svg") else f"{name}.svg"
    if clean_name in _SVG_CACHE:
        return _SVG_CACHE[clean_name]

    svg_file = _ICONS_DIR / clean_name
    if not svg_file.exists():
        # Fallback to local assets if running unpacked
        alt = Path("assets/icons") / clean_name
        if alt.exists():
            svg_file = alt

    if not svg_file.exists():
        return None

    try:
        content = svg_file.read_text(encoding="utf-8")
        _SVG_CACHE[clean_name] = content
        return content
    except Exception:
        return None


def get_pixmap(name: str, color: str = "#E8EBE4", size: int = 16) -> QPixmap:
    """Renders an SVG icon into a high-DPI crisp QPixmap with a specific stroke color."""
    key = (name, color, size)
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]

    raw_svg = _load_svg(name)
    if not raw_svg:
        # Return transparent dummy
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        return pm

    # Inject color into currentColor
    tinted = raw_svg.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(tinted.encode("utf-8")))

    # Scale 2x for sharp HiDPI rendering
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(scale)

    _PIXMAP_CACHE[key] = pm
    return pm


def get_tactical_icon(
    name: str,
    normal_color: str = "#E8EBE4",
    active_color: str = "#9EF41A",
    disabled_color: str = "#4D5247",
    size: int = 16
) -> QIcon:
    """
    Returns a multi-state QIcon with Tactical Obsidian states:
    - Normal: crisp neutral whitish (#E8EBE4)
    - Active / Hover / Selected: Cyber Lime (#9EF41A)
    - Disabled: muted dark (#4D5247)
    """
    key = (name, normal_color, active_color, disabled_color, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    pm_normal = get_pixmap(name, normal_color, size)
    pm_active = get_pixmap(name, active_color, size)
    pm_disabled = get_pixmap(name, disabled_color, size)

    icon = QIcon()
    icon.addPixmap(pm_normal, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(pm_active, QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(pm_active, QIcon.Mode.Selected, QIcon.State.Off)
    icon.addPixmap(pm_disabled, QIcon.Mode.Disabled, QIcon.State.Off)

    _ICON_CACHE[key] = icon
    return icon
