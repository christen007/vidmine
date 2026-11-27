"""Card videos: the mined line's clip on top (with the Japanese line shown as a subtitle
while it's spoken) and the lesson panel below, like the Chrono Trigger card images."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from PIL import Image

from . import media
from .cardpanel import Fonts, render_panel
from .config import Config
from .render import subtitle_overlay

WIDTH = 1024
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(text: str, limit: int = 60) -> str:
    text = _BAD.sub("", text).replace("　", " ").strip(" .")
    return text[:limit].rstrip(" .") or "untitled"


def video_path_for(cfg: Config, card: dict) -> Path:
    m = card["media"]
    s = m["start_ms"] // 1000
    stamp = f"{s // 3600}h{(s % 3600) // 60:02d}m{s % 60:02d}s" if s >= 3600 else f"{s // 60:02d}m{s % 60:02d}s"
    folder = cfg.videos_dir / safe_name(m.get("title") or "Videos")
    return folder / f"{stamp} {safe_name(card['sentence'], 40)}.mp4"


def make_card_video(cfg: Config, card: dict, source: Path, audio_index: int | None = None,
                    video_index: int | None = None, out: Path | None = None) -> Path:
    m = card["media"]
    start, end = m["start_ms"] / 1000, m["end_ms"] / 1000
    clip_start = max(0.0, start - cfg.video.lead_s)
    duration = (end + cfg.video.tail_s) - clip_start
    out = out or video_path_for(cfg, card)
    out.parent.mkdir(parents=True, exist_ok=True)
    fonts = Fonts(cfg)

    with tempfile.TemporaryDirectory(prefix="vidmine_video_") as tmp:
        tmp = Path(tmp)
        # Size of the top half: source frame at display aspect, scaled to the card width.
        frame = tmp / "frame.png"
        media.extract_frame(cfg, source, (start + end) / 2, frame, video_index)
        fw, fh = Image.open(frame).size
        top_h = max(2, round(WIDTH * fh / fw / 2) * 2)
        sub = tmp / "sub.png"
        subtitle_overlay(cfg, (WIDTH, top_h), card["sentence"]).save(sub)
        panel = tmp / "panel.png"
        render_panel(card, fonts).save(panel)

        a, b = start - clip_start, end - clip_start
        vmap = f"0:{video_index}" if video_index is not None else "0:V:0"
        amap = f"0:{audio_index}" if audio_index is not None else "0:a:0?"
        graph = (f"[{vmap}]scale=trunc(iw*sar/2)*2:ih,setsar=1,scale={WIDTH}:{top_h},setsar=1[v];"
                 f"[v][1:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})':shortest=1[top];"
                 f"[top][2:v]vstack=inputs=2:shortest=1,format=yuv420p[out]")
        media.run([cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                   "-ss", f"{clip_start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
                   "-loop", "1", "-i", str(sub), "-loop", "1", "-i", str(panel),
                   "-filter_complex", graph, "-map", "[out]", "-map", amap,
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                   "-c:a", "aac", "-b:a", "160k", "-ac", "2",
                   "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out)])
    return out
