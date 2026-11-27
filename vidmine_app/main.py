"""VidMine desktop app entry point."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _prepare_paths() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(root))
        base = root / "deps"
    # python-mpv finds libmpv-2.dll through PATH.
    os.environ["PATH"] = str(base) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory") and base.exists():
        os.add_dll_directory(str(base))
    return base


def _log_path() -> Path:
    from vidmine.config import app_data_dir
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "vidmine.log"


def main() -> int:
    _prepare_paths()
    # The windowed .exe has no console: send output to a log file instead.
    if sys.stdout is None or sys.stderr is None:
        log = open(_log_path(), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log

    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication(sys.argv)
    app.setApplicationName("VidMine")
    app.setStyle("Fusion")
    import locale
    locale.setlocale(locale.LC_NUMERIC, "C")  # libmpv requires this

    args = sys.argv[1:]
    if args[:1] == ["--selftest-whisper"]:
        from .selftest import run_whisper
        return run_whisper(app, Path(args[1]), Path(args[2]))
    if args[:1] == ["--selftest"]:
        from .selftest import run
        return run(app, Path(args[1]) if len(args) > 1 else Path("selftest.json"))

    def excepthook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        print(text, file=sys.stderr)
        QMessageBox.critical(None, "VidMine error", f"{value}\n\nDetails were saved to:\n{_log_path()}")
    sys.excepthook = excepthook

    try:
        import mpv  # noqa: F401
    except Exception as e:
        QMessageBox.critical(None, "VidMine", f"The video engine (libmpv) could not be loaded:\n{e}")
        return 1

    from vidmine import config
    from .window import MainWindow

    win = MainWindow(config.load_app())
    win.show()
    files = [a for a in args if not a.startswith("-") and Path(a).is_file()]
    if files:  # "Open with → VidMine" passes the file here
        win.open_file(files[0])
    return app.exec()
