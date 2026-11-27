"""Turn one subtitle line (as reported by the mpv script) into a library card."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import analyze, media, render
from .config import Config
from .store import STATUS_FAILED, STATUS_PENDING, STATUS_READY, Library, known_grammar

SCHEMA = "vid-jp-card/1"
CC_MARKS = str.maketrans("", "", "≪≫➡→《》")
SPEAKER_RE = re.compile(r"^[（(]([^（）()]{1,12})[）)]\s*")
ONLY_SOUND_RE = re.compile(r"^[（(［\[〔][^）)］\]〕]*[）)］\]〕]$")


def clean_line(raw: str) -> tuple[str, str]:
    """Return (sentence, speaker). Handles Japanese closed-caption conventions."""
    speaker = ""
    parts = []
    for line in raw.replace("\r", "").split("\n"):
        line = line.translate(CC_MARKS).strip()
        if not line or ONLY_SOUND_RE.match(line):
            continue  # drop sound descriptions like （拍手）
        m = SPEAKER_RE.match(line)
        if m and len(line) > m.end():
            if not speaker:
                speaker = m.group(1).strip()
            line = line[m.end():].strip()
        parts.append(line)
    return "　".join(parts), speaker


def clean_title(title: str) -> str:
    t = re.sub(r"\.(mkv|mp4|avi|webm|m4v|mov|ts)$", "", title, flags=re.I)
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.sub(r"\((?:[^)]*?(?:\d{3,4}p|bit|HEVC|x26[45]|BD|WEB|AAC|FLAC)[^)]*)\)", " ", t, flags=re.I)
    t = t.replace("_", " ")
    return re.sub(r"\s+", " ", t).strip(" -")


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def source_of(payload: dict) -> str:
    if payload.get("sub_external"):
        f = str(payload.get("sub_file", "")).lower()
        return "asr" if f.endswith(".whisper.srt") else "external-subs"
    return "embedded-subs"


def mine(cfg: Config, payload: dict, do_analyze: bool = True) -> dict:
    """payload keys (from vidmine.lua): path, title, text, start, end, english,
    context_before, sub_external, sub_file, audio_ff_index, video_ff_index."""
    video = Path(payload["path"])
    if not video.is_file():
        raise RuntimeError(f"Not a local file: {payload['path']}")
    sentence, speaker = clean_line(payload.get("text", ""))
    if not sentence:
        raise RuntimeError("Nothing to mine: the current line is empty or only a sound description")
    start, end = float(payload["start"]), float(payload["end"])
    if end <= start:
        end = start + 2.0

    lib = Library(cfg)
    fhash = media.file_hash(video)
    start_ms, end_ms = round(start * 1000), round(end * 1000)
    stem = f"vid_{fhash}_{start_ms}"
    scene = lib.images / f"{stem}_scene.jpg"
    scene_raw = lib.images / f"{stem}_scene_raw.jpg"
    audio = lib.audio / f"{stem}.mp3"

    media.extract_audio(cfg, video, start, end, audio, payload.get("audio_ff_index"))
    tmp = media.temp_png()
    try:
        media.extract_frame(cfg, video, (start + end) / 2, tmp, payload.get("video_ff_index"))
        render.make_scene_images(cfg, tmp, sentence, scene, scene_raw)
    finally:
        tmp.unlink(missing_ok=True)

    title = clean_title(payload.get("title") or video.name)
    english = " ".join(clean_line(payload.get("english", ""))[0].split("　")).strip()
    context = [c for c in (clean_line(x)[0] for x in payload.get("context_before", [])) if c][-2:]
    card = {
        "schema": SCHEMA,
        "id": f"vid-jp:{fhash}:{start_ms}",
        "source": source_of(payload),
        "mined_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "location": f"{title} @ {fmt_ts(start)}",
        "speaker": speaker,
        "speech_style": "standard",
        "sentence": sentence,
        "choices": [],
        "furigana": "",
        "meaning": "",
        "official_english": english,
        "english_source": "subtitle-track" if english else "",
        "context_before": context,
        "tokens": [],
        "grammar": [],
        "note": "",
        "images": {
            "card": None,
            "scene": f"images/{scene.name}",
            "scene_original": f"images/{scene_raw.name}",
        },
        "audio": f"audio/{audio.name}",
        "media": {
            "title": title,
            "file_name": video.name,
            "file_hash": fhash,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "audio_padding_ms": cfg.audio.padding_ms,
        },
        "_vidmine": {"status": STATUS_PENDING, "error": "", "warnings": [],
                     "caption_speaker": speaker},
    }
    lib.upsert(card)
    if do_analyze:
        card = analyze_card(cfg, lib, card)
    return card


def analyze_card(cfg: Config, lib: Library, card: dict) -> dict:
    meta = card.setdefault("_vidmine", {})
    # Re-analysis starts from the caption speaker, not a previous guess.
    card["speaker"] = meta.get("caption_speaker", "")
    try:
        msg = analyze.build_user_message(card, known_grammar(cfg, lib))
        result = analyze.call_claude(cfg, msg)
        meta["warnings"] = analyze.apply_analysis(card, result)
        meta["status"], meta["error"] = STATUS_READY, ""
    except Exception as e:  # keep the card; `vidmine analyze` can retry
        meta["status"], meta["error"] = STATUS_FAILED, str(e)
    lib.upsert(card)
    return card
