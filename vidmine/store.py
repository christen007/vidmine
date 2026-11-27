"""The local card library: cards.jsonl plus images/ and audio/, with a simple file lock.

Each library record is a vid-jp-card/1 card plus an internal "_vidmine" key
(status, error, the original inputs) that is stripped on export.
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path

from .config import Config

STATUS_PENDING = "pending"   # media extracted, analysis not done yet
STATUS_READY = "ready"       # fully analyzed, exportable
STATUS_FAILED = "failed"     # analysis failed; `vidmine analyze` retries


class Library:
    def __init__(self, cfg: Config):
        self.root = cfg.library_dir
        self.cards_path = self.root / "cards.jsonl"
        self.state_path = self.root / "state.json"
        self.images = self.root / "images"
        self.audio = self.root / "audio"
        for d in (self.root, self.images, self.audio):
            d.mkdir(parents=True, exist_ok=True)

    # ---- locking -------------------------------------------------------
    @contextlib.contextmanager
    def lock(self, timeout: float = 30.0):
        path = self.root / ".lock"
        deadline = time.time() + timeout
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:  # break locks left behind by a crashed process
                    if time.time() - path.stat().st_mtime > 120:
                        path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    raise TimeoutError(f"Library is locked: {path}")
                time.sleep(0.1)
        try:
            yield
        finally:
            os.close(fd)
            path.unlink(missing_ok=True)

    # ---- cards ----------------------------------------------------------
    def load(self) -> dict[str, dict]:
        cards: dict[str, dict] = {}
        if self.cards_path.exists():
            with open(self.cards_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        c = json.loads(line)
                        cards[c["id"]] = c
        return cards

    def _save(self, cards: dict[str, dict]) -> None:
        tmp = self.cards_path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for c in cards.values():
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        os.replace(tmp, self.cards_path)

    def upsert(self, card: dict) -> None:
        with self.lock():
            cards = self.load()
            cards[card["id"]] = card
            self._save(cards)

    def delete(self, card_id: str) -> None:
        with self.lock():
            cards = self.load()
            card = cards.pop(card_id, None)
            self._save(cards)
        if card:
            for rel in (card["images"].get("scene"), card["images"].get("scene_original"), card.get("audio")):
                if rel:
                    (self.root / rel).unlink(missing_ok=True)

    def get(self, card_id: str) -> dict | None:
        return self.load().get(card_id)

    # ---- export state -------------------------------------------------------
    def load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"exported": {}}

    def save_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def known_grammar(cfg: Config, lib: Library) -> dict[str, str]:
    """Grammar id -> pattern, from this library and any seed files (e.g. the CT export)."""
    known: dict[str, str] = {}
    sources = [lib.cards_path] + [Path(os.path.expanduser(p)) for p in cfg.claude.grammar_seed_files]
    for src in sources:
        if not src.exists():
            continue
        with open(src, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for g in card.get("grammar", []):
                    if g.get("id"):
                        known.setdefault(g["id"], g.get("pattern", ""))
    return known
