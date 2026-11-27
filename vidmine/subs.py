"""Read a whole subtitle track (embedded or external) into timed lines with ffmpeg."""
from __future__ import annotations

import bisect
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .media import _NO_WINDOW

IMAGE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub", "pgssub", "dvdsub"}
_TIME = r"(\d+):(\d{2}):(\d{2})[,.](\d{3})"
_BLOCK = re.compile(_TIME + r"\s*-->\s*" + _TIME + r"[^\n]*\n(.*?)(?:\n\s*\n|\Z)", re.S)
_TAGS = re.compile(r"<[^>]+>|\{[^}]*\}")


@dataclass
class Line:
    start: float
    end: float
    text: str


def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(data: str) -> list[Line]:
    data = data.replace("\r\n", "\n").replace("﻿", "")
    lines: list[Line] = []
    seen = set()
    for m in _BLOCK.finditer(data + "\n\n"):
        text = _TAGS.sub("", m.group(9)).replace("\\N", "\n").replace("\\n", "\n").strip()
        text = "\n".join(t.strip() for t in text.split("\n") if t.strip())
        if not text:
            continue
        start, end = _secs(*m.group(1, 2, 3, 4)), _secs(*m.group(5, 6, 7, 8))
        key = (round(start, 2), text)
        if key in seen:  # ASS files often repeat a line on several layers
            continue
        seen.add(key)
        lines.append(Line(start, max(end, start + 0.3), text))
    lines.sort(key=lambda l: l.start)
    return lines


def extract(cfg: Config, source: Path, stream_index: int | None = None) -> list[Line]:
    """stream_index: ffmpeg stream index inside a video file; None for a subtitle file."""
    args = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(source)]
    if stream_index is not None:
        args += ["-map", f"0:{stream_index}"]
    args += ["-f", "srt", "-"]
    proc = subprocess.run(args, capture_output=True, creationflags=_NO_WINDOW, timeout=120)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(f"Couldn't read subtitles: {err[-1] if err else proc.returncode}")
    return parse_srt(proc.stdout.decode("utf-8", "replace"))


def line_at(lines: list[Line], t: float) -> int:
    """Index of the line showing at time t, or of the last line before t (-1 if none)."""
    i = bisect.bisect_right([l.start for l in lines], t) - 1
    return i


def english_for(en: list[Line], start: float, end: float) -> str:
    """English text of the lines that overlap [start, end] by a meaningful amount."""
    picked = []
    dur = max(0.3, end - start)
    for l in en:
        if l.end <= start or l.start >= end:
            continue
        overlap = min(end, l.end) - max(start, l.start)
        if overlap >= 0.3 * min(dur, l.end - l.start):
            picked.append(l.text.replace("\n", " "))
    return " ".join(picked)
