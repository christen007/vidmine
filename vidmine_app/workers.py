"""Run slow work (ffmpeg, Claude) off the GUI thread."""
from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(False)  # the Python side keeps the reference

    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # report every failure to the GUI
            traceback.print_exc()
            self.signals.failed.emit(str(e) or e.__class__.__name__)
        else:
            self.signals.done.emit(result)


class Runner:
    """Starts jobs and keeps them alive until they finish."""

    def __init__(self, max_threads: int = 3):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max_threads)
        self.active: set[Job] = set()

    def start(self, fn, on_done=None, on_failed=None) -> Job:
        job = Job(fn)
        self.active.add(job)

        def finish(_=None):
            self.active.discard(job)

        if on_done:
            job.signals.done.connect(on_done)
        if on_failed:
            job.signals.failed.connect(on_failed)
        job.signals.done.connect(finish)
        job.signals.failed.connect(finish)
        self.pool.start(job)
        return job

    @property
    def busy(self) -> bool:
        return bool(self.active)
