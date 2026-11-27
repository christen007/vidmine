"""Video file hashing and ffmpeg extraction (audio clip, still frame)."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import Config

CHUNK = 4 * 1024 * 1024
# Keep ffmpeg from flashing a console window when mpv launches us on Windows.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def file_hash(path: Path) -> str:
    """Fast content hash: file size + first and last 4 MB. Stable across renames."""
    size = path.stat().st_size
    h = hashlib.sha256(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(CHUNK))
        if size > CHUNK:
            f.seek(max(CHUNK, size - CHUNK))
            h.update(f.read(CHUNK))
    return h.hexdigest()[:16]


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, creationflags=_NO_WINDOW)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(f"{Path(args[0]).name} failed: {err[-1] if err else proc.returncode}")


def _map(index: int | None, fallback: str) -> str:
    return f"0:{index}" if index is not None else fallback


def extract_audio(cfg: Config, video: Path, start_s: float, end_s: float,
                  out: Path, audio_index: int | None = None) -> None:
    pad = cfg.audio.padding_ms / 1000
    a = max(0.0, start_s - pad)
    dur = max(0.2, end_s + pad - a)
    fade_out_at = max(0.0, dur - 0.06)
    run([cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{a:.3f}", "-t", f"{dur:.3f}", "-i", str(video),
         "-map", _map(audio_index, "0:a:0"), "-vn", "-sn", "-ac", "2",
         "-af", f"afade=t=in:d=0.03,afade=t=out:st={fade_out_at:.3f}:d=0.06",
         "-c:a", "libmp3lame", "-b:a", cfg.audio.bitrate, str(out)])


def extract_frame(cfg: Config, video: Path, at_s: float, out_png: Path,
                  video_index: int | None = None) -> None:
    """Grab one frame at display aspect ratio (fixes anamorphic DVD rips)."""
    run([cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{at_s:.3f}", "-i", str(video),
         "-map", _map(video_index, "0:V:0"), "-frames:v", "1",
         "-vf", "scale=trunc(iw*sar/2)*2:ih,setsar=1",
         "-c:v", "png", str(out_png)])


def temp_png() -> Path:
    fd, name = tempfile.mkstemp(suffix=".png", prefix="vidmine_")
    os.close(fd)
    return Path(name)
