"""Speech recognition: write Japanese subtitles for a video with faster-whisper.

Whisper transcribes (Japanese audio -> Japanese text); it does not translate.
The app downloads what it needs on first use:
  - the Whisper model from Hugging Face (large-v3 ~3 GB, or large-v3-turbo ~1.6 GB)
  - on NVIDIA PCs, NVIDIA's CUDA libraries (cuBLAS 12, cuDNN 9) from PyPI (~1 GB)
Cards mined from these subtitles get source "asr".
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .config import Config
from .media import run as run_tool

Progress = Callable[[float, str], None]

MODELS = {
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabs/faster-whisper-large-v3-turbo",
    "tiny": "Systran/faster-whisper-tiny",  # used by the build self-test
}
MODEL_FILES = re.compile(r"^(config\.json|preprocessor_config\.json|model\.bin|tokenizer\.json|vocabulary\.\w+)$")
# NVIDIA libraries needed by CTranslate2 4.x on Windows: package -> required major version.
CUDA_PACKAGES = {
    "nvidia-cublas-cu12": "12",
    "nvidia-cudnn-cu12": "9",
    "nvidia-cuda-runtime-cu12": "12",
    "nvidia-cuda-nvrtc-cu12": "12",
}
CUDA_MARKERS = ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll")

# Whisper's well-known Japanese hallucinations on silence/music (YouTube outros).
HALLUCINATIONS = {
    "ご視聴ありがとうございました", "ご視聴ありがとうございました。",
    "チャンネル登録をお願いします", "チャンネル登録よろしくお願いします",
    "最後までご視聴いただきありがとうございました",
    "最後までご視聴いただきありがとうございました。",
}
SENTENCE_END = tuple("。！？!?")
# A punctuated Japanese prompt nudges Whisper to punctuate, which gives better line breaks.
JA_PROMPT = "こんにちは。今日は、いい天気ですね。"


class Cancelled(Exception):
    pass


# ---- locations -----------------------------------------------------------------

def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "VidMine"


def models_dir() -> Path:
    return Path(os.environ.get("VIDMINE_MODELS_DIR") or data_dir() / "models")


def cuda_dir() -> Path:
    return Path(os.environ.get("VIDMINE_CUDA_DIR") or data_dir() / "cuda")


def model_path(name: str) -> Path:
    return models_dir() / name


def model_ready(name: str) -> bool:
    return (model_path(name) / ".complete").exists()


def cuda_libs_ready() -> bool:
    return all((cuda_dir() / f).exists() for f in CUDA_MARKERS)


def srt_path_for(video: Path) -> Path:
    return video.with_name(video.stem + ".ja.whisper.srt")


def find_existing_srt(cfg: Config, video: Path) -> Path | None:
    for p in (srt_path_for(video), cfg.library_dir / "transcripts" / srt_path_for(video).name):
        if p.exists():
            return p
    return None


# ---- downloads -----------------------------------------------------------------------

def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "VidMine"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url: str, dest: Path, on_bytes: Callable[[int], None], cancel: threading.Event | None):
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "VidMine"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            on_bytes(len(chunk))
    os.replace(tmp, dest)


def model_files(name: str) -> list[tuple[str, int]]:
    """(path, size) of the files to download for a model."""
    repo = MODELS[name]
    tree = _get_json(f"https://huggingface.co/api/models/{repo}/tree/main")
    return [(f["path"], int(f.get("size") or 0)) for f in tree
            if f.get("type") == "file" and MODEL_FILES.match(f["path"])]


def cuda_wheels(packages: dict[str, str] | None = None) -> list[tuple[str, str, int]]:
    """(package, wheel URL, size) for the newest Windows wheel of each package's required major version."""
    out = []
    for pkg, major in (packages or CUDA_PACKAGES).items():
        data = _get_json(f"https://pypi.org/pypi/{pkg}/json")
        best = None
        for ver, files in data["releases"].items():
            if not ver.split(".")[0] == major or any(c.isalpha() for c in ver):
                continue
            for f in files:
                if f["filename"].endswith(".whl") and "win_amd64" in f["filename"] and not f.get("yanked"):
                    key = tuple(int(x) for x in ver.split(".") if x.isdigit())
                    if best is None or key > best[0]:
                        best = (key, f["url"], int(f["size"]))
        if best is None:
            raise RuntimeError(f"No Windows download found for {pkg} {major}.x")
        out.append((pkg, best[1], best[2]))
    return out


class _Meter:
    def __init__(self, total: int, label: str, progress: Progress | None):
        self.total, self.done, self.label, self.progress = max(total, 1), 0, label, progress

    def __call__(self, n: int):
        self.done += n
        if self.progress:
            mb, tot = self.done / 1e6, self.total / 1e6
            self.progress(min(1.0, self.done / self.total), f"{self.label}: {mb:,.0f} / {tot:,.0f} MB")


def download_model(name: str, progress: Progress | None = None, cancel: threading.Event | None = None) -> Path:
    files = model_files(name)
    if not any(p == "model.bin" for p, _ in files):
        raise RuntimeError(f"Model {name} has no model.bin")
    dest = model_path(name)
    dest.mkdir(parents=True, exist_ok=True)
    meter = _Meter(sum(s for _, s in files), f"Downloading Whisper {name}", progress)
    for path, size in files:
        target = dest / path
        if target.exists() and size and target.stat().st_size == size:
            meter(size)
            continue
        _download(f"https://huggingface.co/{MODELS[name]}/resolve/main/{path}", target, meter, cancel)
    (dest / ".complete").write_text("ok", encoding="utf-8")
    return dest


def download_cuda_libs(progress: Progress | None = None, cancel: threading.Event | None = None,
                       packages: dict[str, str] | None = None) -> Path:
    wheels = cuda_wheels(packages)
    dest = cuda_dir()
    dest.mkdir(parents=True, exist_ok=True)
    meter = _Meter(sum(s for _, _, s in wheels), "Downloading NVIDIA GPU libraries", progress)
    with tempfile.TemporaryDirectory(prefix="vidmine_cuda_") as tmp:
        for pkg, url, _size in wheels:
            whl = Path(tmp) / f"{pkg}.whl"
            _download(url, whl, meter, cancel)
            with zipfile.ZipFile(whl) as z:
                for member in z.namelist():
                    if re.match(r"nvidia/[^/]+/bin/[^/]+\.dll$", member):
                        (dest / Path(member).name).write_bytes(z.read(member))
            whl.unlink()
    return dest


# ---- GPU -------------------------------------------------------------------------------

def use_cuda_dir() -> None:
    d = cuda_dir()
    if sys.platform == "win32" and d.exists():
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
        os.add_dll_directory(str(d))


def gpu_count() -> int:
    """NVIDIA GPUs visible to CTranslate2 (needs only the graphics driver)."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


# ---- transcription -----------------------------------------------------------------------

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


def load_model(name: str, log: Progress | None = None):
    """Load on the GPU when possible, otherwise on the CPU. Returns (model, device, note)."""
    from faster_whisper import WhisperModel
    path = str(model_path(name))
    note = ""
    if gpu_count() > 0:
        if cuda_libs_ready():
            use_cuda_dir()
            try:
                return WhisperModel(path, device="cuda", compute_type="float16"), "cuda", ""
            except Exception as e:
                note = f"GPU failed ({e}); using the CPU instead (slower)."
        else:
            note = "GPU libraries not downloaded; using the CPU (slower)."
    return WhisperModel(path, device="cpu", compute_type="int8"), "cpu", note


def transcribe(cfg: Config, video: Path, model_name: str | None = None, audio_index: int | None = None,
               progress: Progress | None = None, cancel: threading.Event | None = None,
               language: str | None = None) -> Path:
    name = model_name or cfg.whisper.model
    if not model_ready(name):
        raise RuntimeError(f"Whisper model {name} isn't downloaded yet")
    language = language or os.environ.get("VIDMINE_WHISPER_LANGUAGE", "ja")
    report = progress or (lambda f, t: None)

    report(0.0, "Preparing audio…")
    with tempfile.TemporaryDirectory(prefix="vidmine_asr_") as tmp:
        wav = Path(tmp) / "audio.wav"
        # The selected audio track only (not an English dub), as 16 kHz mono.
        run_tool([cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                  "-map", f"0:{audio_index}" if audio_index is not None else "0:a:0",
                  "-vn", "-sn", "-ac", "1", "-ar", "16000", str(wav)])
        report(0.0, "Loading Whisper…")
        model, device, note = load_model(name)
        segments, info = model.transcribe(
            str(wav), language=language, beam_size=cfg.whisper.beam_size, word_timestamps=True,
            vad_filter=True, condition_on_previous_text=False,
            initial_prompt=JA_PROMPT if language == "ja" else None)
        where = "GPU" if device == "cuda" else "CPU"
        words: list[tuple[float, float, str]] = []
        for seg in segments:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if seg.words:
                words.extend((w.start, w.end, w.word) for w in seg.words)
            elif seg.text.strip():
                words.append((seg.start, seg.end, seg.text))
            frac = min(1.0, seg.end / info.duration) if info.duration else 0.0
            report(frac, f"Transcribing on the {where}: {_ts(seg.end)[:8]} / {_ts(info.duration)[:8]}"
                         + (f" — {note}" if note else ""))
    lines = split_words(words)
    out = srt_path_for(video)
    try:
        write_srt(lines, out)
    except OSError:  # video folder not writable: keep it in the library instead
        out = cfg.library_dir / "transcripts" / out.name
        out.parent.mkdir(parents=True, exist_ok=True)
        write_srt(lines, out)
    report(1.0, f"Done: {len(lines)} lines" + (f" ({note})" if note else ""))
    return out
