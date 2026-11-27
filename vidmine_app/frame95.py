"""Windows 95 window frame: navy title bar with _ □ × buttons, beveled border, and
frameless move/resize through the operating system (so snapping still works).
Also Win95-style message boxes and status bar. With the Modern theme these fall back
to ordinary windows and Qt message boxes."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QSizeGrip, QStatusBar,
                               QVBoxLayout, QWidget)

from . import theme95

BORDER = 4  # outer frame thickness (2px bevel + 2px face)
GRIP = 6    # resize hot zone


def app_icon() -> QIcon:
    from vidmine.config import bundled
    from pathlib import Path
    for p in (bundled("icon.ico"), str(Path(__file__).resolve().parent.parent / "packaging" / "icon.ico")):
        if p and Path(p).exists():
            return QIcon(p)
    return QIcon()


class TitleBar(QWidget):
    def __init__(self, window: QWidget, buttons=("min", "max", "close")):
        super().__init__(window)
        self.win = window
        self.setObjectName("titlebar95")
        self.setFixedHeight(20)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        self.icon = QLabel()
        self.icon.setFixedSize(16, 16)
        ic = window.windowIcon() if not window.windowIcon().isNull() else app_icon()
        self.icon.setPixmap(ic.pixmap(16, 16))
        lay.addWidget(self.icon)
        self.title = QLabel(window.windowTitle())
        self.title.setObjectName("title95")
        f = QFont(self.title.font())
        f.setBold(True)
        self.title.setFont(f)
        lay.addWidget(self.title, 1)
        self.buttons = {}
        for name in buttons:
            if name == "close" and len(buttons) > 1:
                lay.addSpacing(2)
            b = QPushButton()
            b.setObjectName("tb95")
            b.setFixedSize(16, 14)
            b.setFocusPolicy(Qt.NoFocus)
            b.setIcon(QIcon(theme95.asset(f"glyph_{name}")))
            b.setIconSize(QSize(9, 9))
            b.clicked.connect(getattr(self, f"_on_{name}"))
            lay.addWidget(b)
            self.buttons[name] = b
        window.windowTitleChanged.connect(self.title.setText)

    def _on_min(self):
        self.win.showMinimized()

    def _on_max(self):
        self.win.showNormal() if self.win.isMaximized() else self.win.showMaximized()

    def _on_close(self):
        self.win.close()

    def sync_state(self):
        active = self.win.isActiveWindow()
        if getattr(self, "_active", None) != active:  # restyle only on change (avoids repaint loops)
            self._active = active
            self.title.setStyleSheet("color: white;" if active else f"color: {theme95.FACE};")
        if "max" in self.buttons:
            g = "restore" if self.win.isMaximized() else "max"
            self.buttons["max"].setIcon(QIcon(theme95.asset(f"glyph_{g}")))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme95.NAVY if self.win.isActiveWindow() else theme95.SHADOW))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.win.windowHandle():
            self.win.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if "max" in self.buttons:
            self._on_max()


def paint_frame(w: QWidget) -> None:
    if w.isMaximized() or w.isFullScreen():
        return
    p = QPainter(w)
    r = w.rect()
    W, H = r.width(), r.height()
    # outer: light / black ; inner: white / shadow
    for i, (tl, br) in enumerate(((theme95.LIGHT, theme95.BLACK), (theme95.WHITE, theme95.SHADOW))):
        p.setPen(QColor(tl))
        p.drawLine(i, i, W - 2 - i, i)
        p.drawLine(i, i, i, H - 2 - i)
        p.setPen(QColor(br))
        p.drawLine(i, H - 1 - i, W - 1 - i, H - 1 - i)
        p.drawLine(W - 1 - i, i, W - 1 - i, H - 1 - i)


class FrameMixin:
    """Mix into a QMainWindow/QDialog subclass (before the Qt class) to give it the Win95 frame."""

    def init_frame(self):
        self.framed = theme95.active()
        if not self.framed:
            return False
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setMouseTracking(True)
        self.setContentsMargins(BORDER, BORDER, BORDER, BORDER)
        return True

    def _edges(self, pos: QPoint):
        if not getattr(self, "framed", False) or self.isMaximized() or self.isFullScreen():
            return Qt.Edges()
        r = self.rect()
        e = Qt.Edges()
        if pos.x() <= GRIP:
            e |= Qt.LeftEdge
        if pos.x() >= r.width() - GRIP:
            e |= Qt.RightEdge
        if pos.y() <= GRIP:
            e |= Qt.TopEdge
        if pos.y() >= r.height() - GRIP:
            e |= Qt.BottomEdge
        return e

    def mouseMoveEvent(self, e):
        edges = self._edges(e.position().toPoint())
        if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edges & (Qt.LeftEdge | Qt.RightEdge):
            self.setCursor(Qt.SizeHorCursor)
        elif edges & (Qt.TopEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        edges = self._edges(e.position().toPoint())
        if edges and e.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemResize(edges)
            return
        super().mousePressEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        if getattr(self, "framed", False):
            paint_frame(self)

    def changeEvent(self, e):
        super().changeEvent(e)
        if getattr(self, "framed", False) and e.type() in (QEvent.ActivationChange, QEvent.WindowStateChange):
            m = 0 if (self.isMaximized() or self.isFullScreen()) else BORDER
            self.setContentsMargins(m, m, m, m)
            tb = getattr(self, "titlebar", None)
            if tb is not None:
                tb.sync_state()
            self.update()


class Dialog95(FrameMixin, QDialog):
    """Dialog with the Win95 frame. Put content in self.body (its layout), not in self."""

    def __init__(self, parent=None, title: str = ""):
        super().__init__(parent)
        if title:
            self.setWindowTitle(title)
        if self.init_frame():
            self.setWindowIcon(app_icon())
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            self.titlebar = TitleBar(self, ("close",))
            outer.addWidget(self.titlebar)
            self.body = QWidget()
            self.body.setObjectName("body95")
            outer.addWidget(self.body, 1)
        else:
            self.body = QWidget()
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(self.body)


def msg(parent, title: str, text: str, kind: str = "info", buttons=("OK",), default: int = 0) -> str | None:
    """Message box. Returns the text of the clicked button (None if closed)."""
    if not theme95.active():
        from PySide6.QtWidgets import QMessageBox
        icons = {"info": QMessageBox.Information, "warning": QMessageBox.Warning,
                 "error": QMessageBox.Critical, "question": QMessageBox.Question}
        box = QMessageBox(icons.get(kind, QMessageBox.Information), title, text, parent=parent)
        made = [box.addButton(b, QMessageBox.AcceptRole) for b in buttons]
        box.setDefaultButton(made[default])
        box.exec()
        clicked = box.clickedButton()
        return buttons[made.index(clicked)] if clicked in made else None

    dlg = Dialog95(parent, title)
    dlg.setModal(True)
    lay = QVBoxLayout(dlg.body)
    lay.setContentsMargins(12, 12, 12, 10)
    row = QHBoxLayout()
    icon = QLabel()
    icon.setPixmap(QPixmap(theme95.asset(f"icon_{kind}")))
    icon.setAlignment(Qt.AlignTop)
    row.addWidget(icon)
    row.addSpacing(12)
    label = QLabel(text)
    label.setWordWrap(True)
    label.setMinimumWidth(min(420, max(220, len(text) * 5)))
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    row.addWidget(label, 1)
    lay.addLayout(row)
    lay.addSpacing(12)
    brow = QHBoxLayout()
    brow.addStretch(1)
    result = {"value": None}
    for i, name in enumerate(buttons):
        b = QPushButton(name)
        b.setMinimumWidth(75)
        b.clicked.connect(lambda _=False, n=name: (result.__setitem__("value", n), dlg.accept()))
        if i == default:
            b.setDefault(True)
            b.setFocus()
        brow.addWidget(b)
    brow.addStretch(1)
    lay.addLayout(brow)
    dlg.exec()
    return result["value"]


class StatusBar95(QStatusBar):
    """Status bar with Win95 sunken panels: a message panel and a card-count panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeGripEnabled(True)
        self.panel = QLabel("")
        self.count = QLabel("")
        if theme95.active():
            self.panel.setObjectName("panel95")
            self.count.setObjectName("panel95")
        self.count.setMinimumWidth(110)
        self.addWidget(self.panel, 1)
        self.addPermanentWidget(self.count)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.panel.setText(""))

    def showMessage(self, text: str, timeout: int = 0):  # noqa: N802 (Qt naming)
        self.panel.setText(text)
        if timeout:
            self._timer.start(timeout)
        else:
            self._timer.stop()

    def currentMessage(self) -> str:  # noqa: N802
        return self.panel.text()
