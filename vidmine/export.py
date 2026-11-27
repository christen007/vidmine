"""Build VID_Cards_export_<date-time>.zip for Kaeru's Mine tab."""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path

from .config import Config
from .store import STATUS_READY, Library

FOLDER = "VID_Cards"


def public_card(card: dict) -> dict:
    return {k: v for k, v in card.items() if not k.startswith("_")}


def content_hash(card: dict) -> str:
    return hashlib.sha1(json.dumps(public_card(card), ensure_ascii=False, sort_keys=True)
                        .encode("utf-8")).hexdigest()


def export(cfg: Config, everything: bool = False) -> dict:
    lib = Library(cfg)
    with lib.lock():
        cards = lib.load()
        state = lib.load_state()
    done = state.setdefault("exported", {})
    ready = [c for c in cards.values() if c.get("_vidmine", {}).get("status") == STATUS_READY]
    skipped = len(cards) - len(ready)
    chosen = [c for c in ready if everything or done.get(c["id"]) != content_hash(c)]
    if not chosen:
        return {"count": 0, "skipped": skipped, "path": ""}

    cfg.exports.mkdir(parents=True, exist_ok=True)
    out = cfg.exports / f"VID_Cards_export_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        lines = []
        for c in sorted(chosen, key=lambda c: c["mined_at"]):
            pub = public_card(c)
            for rel in (pub["images"]["scene"], pub["images"]["scene_original"], pub["audio"]):
                if rel:
                    src = lib.root / rel
                    if not src.exists():
                        raise FileNotFoundError(f"Missing media for {c['id']}: {src}")
                    # JPEG and MP3 are already compressed: store them as-is.
                    z.write(src, f"{FOLDER}/{rel}", compress_type=zipfile.ZIP_STORED)
            lines.append(json.dumps(pub, ensure_ascii=False))
        z.writestr(f"{FOLDER}/cards.jsonl", "\n".join(lines) + "\n")

    for c in chosen:
        done[c["id"]] = content_hash(c)
    state["last_export"] = {"at": datetime.now().isoformat(timespec="seconds"),
                            "file": out.name, "count": len(chosen)}
    with lib.lock():
        lib.save_state(state)
    return {"count": len(chosen), "skipped": skipped, "path": str(out)}
