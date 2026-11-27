"""The embedded mpv video player widget."""
from __future__ import annotations

import collections

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QWidget


class MpvWidget(QWidget):
    """Hosts libmpv inside a native child window. headless=True plays without video/audio
    output (used by the self-test on build machines)."""

    tracks_changed = Signal(object)

    def __init__(self, parent=None, headless: bool = False):
        super().__init__(parent)
        import mpv  # imported late so main.py can set up the DLL search path first

        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_NativeWindow)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("black"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.setMinimumSize(320, 180)

        opts = dict(
            input_default_bindings=False, input_vo_keyboard=False, input_cursor=False,
            osc=False, keep_open="yes", idle="yes", hwdec="auto-safe",
            sub_auto="fuzzy", slang="ja,jpn,jp", audio_file_auto="no",
            sub_font_size=46, sub_border_size=3,
        )
        if headless:
            opts.update(vo="null", ao="null")
        else:
            opts["wid"] = str(int(self.winId()))
        self.log = collections.deque(maxlen=300)  # recent mpv messages, for error reports
        self.mpv = mpv.MPV(log_handler=self._on_log, loglevel="info", **opts)
        self.mpv.observe_property("track-list", self._on_tracks)

    def _on_log(self, level, prefix, text):
        self.log.append(f"[{level}] {prefix}: {text.rstrip()}")

    def _on_tracks(self, _name, value):
        # Called on mpv's thread; Qt queues the signal to the GUI thread.
        self.tracks_changed.emit(list(value or []))

    # Small helpers that never raise (mpv properties are unavailable while idle).
    def get(self, prop: str, default=None):
        # Note: python-mpv's mpv[...] reads *options*; live properties need _get_property.
        try:
            v = self.mpv._get_property(prop)
            return default if v is None else v
        except Exception:
            return default

    def set(self, prop: str, value) -> None:
        try:
            self.mpv._set_property(prop, value)
        except Exception:
            pass

    def shutdown(self) -> None:
        try:
            self.mpv.terminate()
        except Exception:
            pass
