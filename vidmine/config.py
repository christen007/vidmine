"""Configuration: defaults, overridden by config.toml next to the project."""
from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.toml"


@dataclass
class AudioCfg:
    padding_ms: int = 250
    bitrate: str = "128k"


@dataclass
class ImageCfg:
    max_width: int = 1280
    jpeg_quality: int = 88
    font: str = ""  # path to a Japanese font; empty = auto-detect


@dataclass
class ClaudeCfg:
    model: str = "claude-sonnet-5-5"
    api_key: str = ""  # empty = read the ANTHROPIC_API_KEY environment variable
    workspace_id: str = ""  # needed for personal/service-account keys not scoped to a workspace
    auth: str = "bearer"  # how the key is sent: "bearer" (Authorization header) or "x-api-key"
    max_tokens: int = 4000
    # Extra cards.jsonl files whose grammar ids should be reused (e.g. the CT export).
    grammar_seed_files: list[str] = field(default_factory=list)

    def resolved_key(self) -> str:
        return self.api_key or os.environ.get("ANTHROPIC_API_KEY", "")


@dataclass
class WhisperCfg:
    model: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    beam_size: int = 5


@dataclass
class VideoCfg:
    enabled: bool = True   # make a card video for every mined line
    lead_s: float = 1.0    # extra seconds before the line
    tail_s: float = 1.0    # extra seconds after the line


@dataclass
class Config:
    library_dir: Path = Path.home() / "Documents" / "VidMine"
    export_dir: Path | None = None  # default: <library_dir>/exports
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    audio: AudioCfg = field(default_factory=AudioCfg)
    image: ImageCfg = field(default_factory=ImageCfg)
    claude: ClaudeCfg = field(default_factory=ClaudeCfg)
    whisper: WhisperCfg = field(default_factory=WhisperCfg)
    video: VideoCfg = field(default_factory=VideoCfg)
    video_dir: Path | None = None  # default: <library_dir>/Videos

    @property
    def exports(self) -> Path:
        return self.export_dir or (self.library_dir / "exports")

    @property
    def videos_dir(self) -> Path:
        return self.video_dir or (self.library_dir / "Videos")


FROZEN = getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    """Folder holding bundled tools (ffmpeg.exe, libmpv-2.dll, the font) in the built app."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return PROJECT_DIR / "deps"


def bundled(name: str) -> str | None:
    p = bundle_dir() / name
    return str(p) if p.exists() else None


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "VidMine"


APP_SETTINGS_FIELDS = {
    # json key: (section or None, attribute)
    "library_dir": (None, "library_dir"),
    "export_dir": (None, "export_dir"),
    "api_key": ("claude", "api_key"),
    "workspace_id": ("claude", "workspace_id"),
    "auth": ("claude", "auth"),
    "model": ("claude", "model"),
    "grammar_seed_files": ("claude", "grammar_seed_files"),
    "padding_ms": ("audio", "padding_ms"),
    "whisper_model": ("whisper", "model"),
    "video_enabled": ("video", "enabled"),
    "video_lead_s": ("video", "lead_s"),
    "video_tail_s": ("video", "tail_s"),
    "video_dir": (None, "video_dir"),
}


def load_app(path: Path | None = None) -> Config:
    """Settings for the desktop app: %APPDATA%/VidMine/settings.json."""
    path = path or app_data_dir() / "settings.json"
    cfg = Config()
    for tool in ("ffmpeg", "ffprobe"):
        exe = bundled(tool + (".exe" if sys.platform == "win32" else ""))
        if exe:
            setattr(cfg, tool, exe)
    font = bundled("NotoSansJP-Bold.otf")
    if font:
        cfg.image.font = font
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}
        for key, (section, attr) in APP_SETTINGS_FIELDS.items():
            if key in raw and raw[key] not in (None, ""):
                target = getattr(cfg, section) if section else cfg
                val = raw[key]
                if attr in ("library_dir", "export_dir", "video_dir"):
                    val = _expand(val)
                setattr(target, attr, val)
    return cfg


def save_app(cfg: Config, path: Path | None = None) -> None:
    path = path or app_data_dir() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {}
    for key, (section, attr) in APP_SETTINGS_FIELDS.items():
        val = getattr(getattr(cfg, section) if section else cfg, attr)
        out[key] = str(val) if isinstance(val, Path) else val
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def _expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


def load(path: Path | None = None) -> Config:
    path = path or Path(os.environ.get("VIDMINE_CONFIG", DEFAULT_CONFIG_PATH))
    cfg = Config()
    if not path.exists():
        return cfg
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    if "library_dir" in raw:
        cfg.library_dir = _expand(raw["library_dir"])
    if raw.get("export_dir"):
        cfg.export_dir = _expand(raw["export_dir"])
    cfg.ffmpeg = raw.get("ffmpeg", cfg.ffmpeg)
    cfg.ffprobe = raw.get("ffprobe", cfg.ffprobe)
    for name, sub in (("audio", cfg.audio), ("image", cfg.image),
                      ("claude", cfg.claude), ("whisper", cfg.whisper), ("video", cfg.video)):
        for k, v in raw.get(name, {}).items():
            if hasattr(sub, k):
                setattr(sub, k, v)
    return cfg
