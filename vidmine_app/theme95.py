"""Windows 95 look: pixel-exact bevel images, a style sheet for every widget, and the
classic font (Microsoft Sans Serif, drawn without smoothing).

Images are generated with Pillow at 1x/2x/3x (nearest-neighbour) on first run, so the
bevels stay crisp at any display scale."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw

VERSION = "3"
FACE, LIGHT, WHITE, SHADOW, BLACK = "#c0c0c0", "#dfdfdf", "#ffffff", "#808080", "#000000"
NAVY = "#000080"

_active = False


def active() -> bool:
    return _active


def assets_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "VidMine" / "theme95" / f"v{VERSION}"


# ---- pixel art -------------------------------------------------------------------------

def _rgba(c: str, a: int = 255):
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


def _bevel(w: int, h: int, tl: tuple[str, str], br: tuple[str, str], face: str) -> Image.Image:
    """Two-pixel Win95 bevel: tl/br = (outer, inner) colours."""
    im = Image.new("RGBA", (w, h), _rgba(face))
    px = im.load()
    for i, (t, b) in enumerate(zip(tl, br)):
        t, b = _rgba(t), _rgba(b)
        for x in range(i, w - 1 - i):
            px[x, i] = t
        for y in range(i, h - 1 - i):
            px[i, y] = t
        for x in range(i, w - i):
            px[x, h - 1 - i] = b
        for y in range(i, h - i):
            px[w - 1 - i, y] = b
    return im


def _thin_sunken(face=FACE) -> Image.Image:
    im = Image.new("RGBA", (3, 3), _rgba(face))
    px = im.load()
    for i in range(3):
        px[i, 0] = px[0, i] = _rgba(SHADOW)
        px[i, 2] = px[2, i] = _rgba(WHITE)
    px[0, 2] = px[2, 0] = _rgba(FACE)
    return im


def _pattern(rows: list[str], color: str, size: tuple[int, int] | None = None) -> Image.Image:
    h, w = len(rows), max(len(r) for r in rows)
    W, H = size or (w, h)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ox, oy = (W - w) // 2, (H - h) // 2
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "X":
                im.putpixel((ox + x, oy + y), _rgba(color))
    return im


ARROW = {
    "down": ["XXXXXXX", ".XXXXX.", "..XXX..", "...X..."],
    "up": ["...X...", "..XXX..", ".XXXXX.", "XXXXXXX"],
    "left": ["...X", "..XX", ".XXX", "XXXX", ".XXX", "..XX", "...X"],
    "right": ["X...", "XX..", "XXX.", "XXXX", "XXX.", "XX..", "X..."],
}
CHECK = ["......X", ".....XX", "X...XXX", "XX.XXX.", "XXXXX..", ".XXX...", "..X...."]
GLYPHS = {
    "min": ["........", "........", "........", "........", "........", ".XXXXXX.", ".XXXXXX."],
    "max": ["XXXXXXXXX", "XXXXXXXXX", "X.......X", "X.......X", "X.......X", "X.......X",
            "X.......X", "X.......X", "XXXXXXXXX"],
    "restore": ["..XXXXXX", "..XXXXXX", "..X....X", "XXXXXX.X", "XXXXXX.X", "X....XXX",
                "X....X..", "X....X..", "XXXXXX.."],
    "close": ["XX....XX", ".XX..XX.", "..XXXX..", "...XX...", "..XXXX..", ".XX..XX.", "XX....XX"],
}
QUESTION = ["..XXXX..", ".XX..XX.", ".XX..XX.", ".....XX.", "....XX..", "...XX...",
            "...XX...", "........", "...XX...", "...XX..."]


def _checkbox(on: bool) -> Image.Image:
    im = _bevel(13, 13, (SHADOW, BLACK), (WHITE, LIGHT), WHITE)
    if on:
        im.alpha_composite(_pattern(CHECK, BLACK), (3, 3))
    return im


def _radio(on: bool) -> Image.Image:
    im = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 11, 11], fill=_rgba(WHITE))
    d.arc([0, 0, 11, 11], 135, 315, fill=_rgba(SHADOW))
    d.arc([1, 1, 10, 10], 135, 315, fill=_rgba(BLACK))
    d.arc([0, 0, 11, 11], 315, 135, fill=_rgba(WHITE))
    d.arc([1, 1, 10, 10], 315, 135, fill=_rgba(LIGHT))
    if on:
        d.rectangle([4, 4, 7, 7], fill=_rgba(BLACK))
    return im


def _dither() -> Image.Image:
    im = Image.new("RGBA", (2, 2), _rgba(FACE))
    im.putpixel((1, 0), _rgba(WHITE))
    im.putpixel((0, 1), _rgba(WHITE))
    return im


def _msg_icon(kind: str) -> Image.Image:
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if kind == "warning":
        d.polygon([(15, 1), (30, 29), (1, 29)], fill=_rgba("#ffff00"), outline=_rgba(BLACK))
        d.rectangle([14, 9, 16, 20], fill=_rgba(BLACK))
        d.rectangle([14, 23, 16, 25], fill=_rgba(BLACK))
    elif kind == "error":
        d.ellipse([1, 1, 30, 30], fill=_rgba("#ff0000"), outline=_rgba("#800000"))
        for o in range(-1, 2):
            d.line([(10 + o, 10), (21 + o, 21)], fill=_rgba(WHITE))
            d.line([(21 + o, 10), (10 + o, 21)], fill=_rgba(WHITE))
    else:  # info / question: white speech bubble with a blue mark
        d.ellipse([1, 1, 30, 26], fill=_rgba(WHITE), outline=_rgba(BLACK))
        d.polygon([(9, 23), (7, 30), (15, 25)], fill=_rgba(WHITE), outline=_rgba(BLACK))
        d.line([(10, 25), (14, 25)], fill=_rgba(WHITE))
        if kind == "question":
            im.alpha_composite(_pattern(QUESTION, "#0000ff").resize((16, 20), Image.NEAREST), (8, 4))
        else:
            d.rectangle([14, 5, 17, 8], fill=_rgba("#0000ff"))
            d.rectangle([14, 11, 17, 21], fill=_rgba("#0000ff"))
            d.rectangle([12, 11, 13, 12], fill=_rgba("#0000ff"))
            d.rectangle([12, 20, 19, 21], fill=_rgba("#0000ff"))
    return im


def _all_images() -> dict[str, Image.Image]:
    imgs = {
        "raised": _bevel(6, 6, (WHITE, LIGHT), (BLACK, SHADOW), FACE),
        "pressed": _bevel(6, 6, (BLACK, SHADOW), (WHITE, LIGHT), FACE),
        "window": _bevel(6, 6, (LIGHT, WHITE), (BLACK, SHADOW), FACE),
        "field": _bevel(6, 6, (SHADOW, BLACK), (WHITE, LIGHT), WHITE),
        "fieldface": _bevel(6, 6, (SHADOW, BLACK), (WHITE, LIGHT), FACE),
        "thin": _thin_sunken(),
        "dither": _dither(),
        "check_off": _checkbox(False), "check_on": _checkbox(True),
        "radio_off": _radio(False), "radio_on": _radio(True),
    }
    tab = _bevel(6, 6, (WHITE, LIGHT), (BLACK, SHADOW), FACE)
    for x in range(6):  # tabs are open at the bottom
        tab.putpixel((x, 4), _rgba(FACE) if 1 < x < 4 else tab.getpixel((x, 3)))
        tab.putpixel((x, 5), _rgba(FACE) if 1 < x < 4 else tab.getpixel((x, 3)))
    tab.putpixel((0, 0), (0, 0, 0, 0))
    tab.putpixel((5, 0), (0, 0, 0, 0))
    imgs["tab"] = tab
    for name, rows in ARROW.items():
        imgs[f"arrow_{name}"] = _pattern(rows, BLACK)
        imgs[f"arrow_{name}_off"] = _pattern(rows, SHADOW)
    for name, rows in GLYPHS.items():
        imgs[f"glyph_{name}"] = _pattern(rows, BLACK, (9, 9))
    for kind in ("info", "warning", "error", "question"):
        imgs[f"icon_{kind}"] = _msg_icon(kind)
    return imgs


def build_assets(dest: Path | None = None) -> Path:
    dest = dest or assets_dir()
    if (dest / ".done").exists():
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    for name, im in _all_images().items():
        im.save(dest / f"{name}.png")
        for k in (2, 3):  # crisp high-DPI variants, picked up automatically by Qt
            im.resize((im.width * k, im.height * k), Image.NEAREST).save(dest / f"{name}@{k}x.png")
    (dest / ".done").write_text("ok")
    return dest


# ---- style sheet ---------------------------------------------------------------------------

def stylesheet(a: Path) -> str:
    u = lambda n: f"url({(a / (n + '.png')).as_posix()})"  # noqa: E731
    raised = f"border-image: {u('raised')} 2 2 2 2 stretch stretch; border-width: 2px;"
    pressed = f"border-image: {u('pressed')} 2 2 2 2 stretch stretch; border-width: 2px;"
    field = f"border-image: {u('field')} 2 2 2 2 stretch stretch; border-width: 2px;"
    window = f"border-image: {u('window')} 2 2 2 2 stretch stretch; border-width: 2px;"
    return f"""
* {{ color: black; }}
QMainWindow, QDialog, QWidget#body95 {{ background: {FACE}; }}
QToolTip {{ background: #ffffe1; color: black; border: 1px solid black; padding: 1px 3px; }}
QLabel {{ background: transparent; }}

QPushButton {{ {raised} background: {FACE}; padding: 3px 10px; min-height: 15px; }}
QPushButton:pressed, QPushButton:checked {{ {pressed} padding: 4px 9px 2px 11px; }}
QPushButton:disabled {{ color: {SHADOW}; }}
QPushButton#tb95 {{ {raised} padding: 0; min-height: 0; min-width: 0; }}
QPushButton#tb95:pressed {{ {pressed} padding: 1px 0 0 1px; }}

QToolBar {{ background: {FACE}; border: none; spacing: 3px; padding: 2px 4px; }}
QToolBar::separator {{ width: 2px; margin: 2px 4px; background: {SHADOW}; border-right: 1px solid white; }}
QToolButton {{ {raised} background: {FACE}; padding: 2px 8px; }}
QToolButton:pressed {{ {pressed} }}

QMenuBar {{ background: {FACE}; padding: 1px 0; }}
QMenuBar::item {{ background: transparent; padding: 2px 7px; }}
QMenuBar::item:selected {{ background: {NAVY}; color: white; }}
QMenu {{ {window} background: {FACE}; padding: 1px; }}
QMenu::item {{ padding: 3px 24px 3px 20px; background: transparent; }}
QMenu::item:selected {{ background: {NAVY}; color: white; }}
QMenu::item:disabled {{ color: {SHADOW}; }}
QMenu::separator {{ height: 2px; margin: 3px 2px; border-top: 1px solid {SHADOW}; border-bottom: 1px solid white; }}

QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QSpinBox, QDoubleSpinBox {{
    {field} background: white; selection-background-color: {NAVY}; selection-color: white; }}
QLineEdit, QSpinBox, QDoubleSpinBox {{ padding: 1px 2px; min-height: 15px; }}
QListWidget::item:selected {{ background: {NAVY}; color: white; }}
QListWidget::item:selected:!active {{ background: {NAVY}; color: white; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ {raised} subcontrol-origin: border; subcontrol-position: top right; width: 14px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ {raised} subcontrol-origin: border; subcontrol-position: bottom right; width: 14px; }}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{ {pressed} }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: {u('arrow_up')}; width: 7px; height: 4px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: {u('arrow_down')}; width: 7px; height: 4px; }}

QComboBox {{ {field} background: white; padding: 1px 18px 1px 3px; min-height: 15px; }}
QComboBox:disabled {{ background: {FACE}; color: {SHADOW}; }}
QComboBox::drop-down {{ {raised} subcontrol-origin: border; subcontrol-position: top right; width: 14px; margin: 2px; }}
QComboBox::drop-down:pressed, QComboBox::drop-down:on {{ {pressed} }}
QComboBox::down-arrow {{ image: {u('arrow_down')}; width: 7px; height: 4px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid black; outline: none;
    selection-background-color: {NAVY}; selection-color: white; }}

QCheckBox {{ spacing: 6px; background: transparent; }}
QCheckBox::indicator {{ width: 13px; height: 13px; image: {u('check_off')}; }}
QCheckBox::indicator:checked {{ image: {u('check_on')}; }}
QRadioButton {{ spacing: 6px; background: transparent; }}
QRadioButton::indicator {{ width: 12px; height: 12px; image: {u('radio_off')}; }}
QRadioButton::indicator:checked {{ image: {u('radio_on')}; }}

QTabWidget::pane {{ {window} background: {FACE}; top: -2px; }}
QTabBar::tab {{ border-image: {u('tab')} 2 2 0 2 stretch stretch; border-width: 2px 2px 0 2px;
    background: {FACE}; padding: 3px 12px 3px 12px; margin-top: 2px; }}
QTabBar::tab:selected {{ margin-top: 0; padding-bottom: 5px; margin-left: -2px; margin-right: -2px; }}
QTabBar::tab:first:selected {{ margin-left: 0; }}

QScrollBar:vertical {{ background: {u('dither')}; width: 16px; margin: 16px 0 16px 0; }}
QScrollBar:horizontal {{ background: {u('dither')}; height: 16px; margin: 0 16px 0 16px; }}
QScrollBar::handle {{ {raised} background: {FACE}; }}
QScrollBar::handle:vertical {{ min-height: 16px; }}
QScrollBar::handle:horizontal {{ min-width: 16px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ {raised} background: {FACE}; subcontrol-origin: margin; }}
QScrollBar::add-line:pressed, QScrollBar::sub-line:pressed {{ {pressed} }}
QScrollBar::add-line:vertical {{ height: 12px; width: 12px; subcontrol-position: bottom; }}
QScrollBar::sub-line:vertical {{ height: 12px; width: 12px; subcontrol-position: top; }}
QScrollBar::add-line:horizontal {{ width: 12px; height: 12px; subcontrol-position: right; }}
QScrollBar::sub-line:horizontal {{ width: 12px; height: 12px; subcontrol-position: left; }}
QScrollBar::up-arrow {{ image: {u('arrow_up')}; width: 7px; height: 4px; }}
QScrollBar::down-arrow {{ image: {u('arrow_down')}; width: 7px; height: 4px; }}
QScrollBar::left-arrow {{ image: {u('arrow_left')}; width: 4px; height: 7px; }}
QScrollBar::right-arrow {{ image: {u('arrow_right')}; width: 4px; height: 7px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QSlider::groove:horizontal {{ border-image: {u('fieldface')} 2 2 2 2 stretch stretch; border-width: 2px; height: 0px; }}
QSlider::handle:horizontal {{ {raised} background: {FACE}; width: 7px; margin: -9px 0; }}
QSlider::handle:horizontal:pressed {{ {raised} }}

QProgressBar {{ border-image: {u('fieldface')} 2 2 2 2 stretch stretch; border-width: 2px;
    background: {FACE}; text-align: center; min-height: 14px; }}
QProgressBar::chunk {{ background: {NAVY}; width: 8px; margin: 1px; }}

QStatusBar {{ background: {FACE}; padding: 1px 2px; }}
QStatusBar::item {{ border: none; }}
QLabel#panel95 {{ border-image: {u('thin')} 1 1 1 1 stretch stretch; border-width: 1px; padding: 1px 4px; }}

QSplitter::handle {{ background: {FACE}; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QSplitter::handle:vertical {{ height: 6px; }}
QWidget#titlebar95 {{ background: transparent; }}
QLabel#title95 {{ color: white; background: transparent; padding-left: 3px; }}
"""


def apply(app) -> None:
    """Switch the whole application to the Windows 95 look."""
    global _active
    from PySide6.QtGui import QColor, QFont, QPalette

    a = build_assets()
    font = QFont()
    font.setFamilies(["Microsoft Sans Serif", "MS Sans Serif", "MS UI Gothic", "Tahoma"])
    font.setPointSize(8)
    font.setStyleStrategy(QFont.NoAntialias)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)
    pal = app.palette()
    for role, c in ((QPalette.Window, FACE), (QPalette.Button, FACE), (QPalette.Base, WHITE),
                    (QPalette.Highlight, NAVY), (QPalette.HighlightedText, WHITE),
                    (QPalette.WindowText, BLACK), (QPalette.ButtonText, BLACK), (QPalette.Text, BLACK),
                    (QPalette.Light, WHITE), (QPalette.Midlight, LIGHT), (QPalette.Mid, SHADOW),
                    (QPalette.Dark, SHADOW), (QPalette.Shadow, BLACK)):
        pal.setColor(role, QColor(c))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(a))
    _active = True


def content_font(size_px: int = 15):
    """Smooth Japanese font for study content (line list), even in the Win95 theme."""
    from PySide6.QtGui import QFont
    f = QFont()
    f.setFamilies(["Yu Gothic UI", "Meiryo UI", "MS UI Gothic", "Noto Sans CJK JP"])
    f.setPixelSize(size_px)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def asset(name: str) -> str:
    return str(assets_dir() / f"{name}.png")
