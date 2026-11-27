"""Speech recognition fallback: write <video>.ja.whisper.srt with faster-whisper.

Cards mined from this file get source "asr". On an RTX 3080 Ti, large-v3 in
float16 transcribes a 24-minute episode in roughly a minute or two.
"""
from __future__ import annotations

import os
import sys
import sysconfig
from pathlib import Path

from .config import Config

# Whisper's well-known Japanese hallucinations on silence/music (YouTube outros).
HALLUCINATIONS = {
    "ご視聴ありがとうございました", "ご視聴ありがとうございました。",
    "チャンネル登録をお願いします", "チャンネル登録よろしくお願いします",
    "最後までご視聴いただきありがとうございました",
    "最後までご視聴いただきありがとうございました。",
}
SENTENCE_END = tuple("。！？!?")


def srt_path_for(video: Path) -> Path:
    return video.with_name(video.stem + ".ja.whisper.srt")


def _add_cuda_dll_dirs() -> None:
    """On Windows, find cuBLAS/cuDNN DLLs installed by the nvidia-* pip packages."""
    if sys.platform != "win32":
        return
    site = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    if site.exists():
        for bin_dir in site.glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def _ts(t: float) -> str:
    ms = max(0, round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def split_words(words: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Group (start, end, text) words into subtitle-sized lines."""
    lines, cur = [], []
    for i, (s, e, w) in enumerate(words):
        cur.append((s, e, w))
        text = "".join(x[2] for x in cur).strip()
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt[0] - e) if nxt else 99
        dur = e - cur[0][0]
        if (text.endswith(SENTENCE_END) or gap > 0.8 or len(text) >= 45 or dur > 8
                or (len(text) >= 28 and text.endswith("、"))):
            lines.append((cur[0][0], e, text))
            cur = []
    if cur:
        lines.append((cur[0][0], cur[-1][1], "".join(x[2] for x in cur).strip()))
    return [l for l in lines if l[2] and l[2] not in HALLUCINATIONS]


def write_srt(lines: list[tuple[float, float, str]], out: Path) -> None:
    with open(out, "w", encoding="utf-8-sig", newline="\n") as f:
        for n, (s, e, text) in enumerate(lines, 1):
            f.write(f"{n}\n{_ts(s)} --> {_ts(e)}\n{text}\n\n")


def transcribe(cfg: Config, video: Path, model_name: str | None = None) -> Path:
    _add_cuda_dll_dirs()
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper is not installed: pip install faster-whisper") from e
    w = cfg.whisper
    model = WhisperModel(model_name or w.model, device=w.device, compute_type=w.compute_type)
    segments, info = model.transcribe(
        str(video), language="ja", beam_size=w.beam_size, word_timestamps=True,
        vad_filter=True, condition_on_previous_text=False)
    words: list[tuple[float, float, str]] = []
    for seg in segments:
        print(f"\r{_ts(seg.end)[:8]} / {_ts(info.duration)[:8]}", end="", file=sys.stderr, flush=True)
        if seg.words:
            words.extend((x.start, x.end, x.word) for x in seg.words)
        else:
            words.append((seg.start, seg.end, seg.text))
    print(file=sys.stderr)
    out = srt_path_for(video)
    write_srt(split_words(words), out)
    return out
