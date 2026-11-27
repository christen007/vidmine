"""Command line: python vidmine_cli.py <command>  (or: python -m vidmine <command>)

  mine          read one line's JSON on stdin (sent by vidmine.lua) and make a card
  analyze       (re)run Claude analysis on pending/failed cards; --all redoes every card
  export        write VID_Cards_export_<date-time>.zip; --all includes already-exported cards
  status        show counts and any failed cards
  transcribe    VIDEO  -> VIDEO.ja.whisper.srt using faster-whisper on the GPU

mine/export/transcribe print one JSON line on stdout for the mpv script;
human-readable messages go to stderr.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config as config_mod
from .store import STATUS_FAILED, STATUS_PENDING, STATUS_READY, Library


def _utf8_io() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass


def emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def cmd_mine(cfg, args) -> int:
    from .mine import mine
    raw = Path(args.json).read_bytes() if args.json else sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
        card = mine(cfg, payload, do_analyze=not args.no_analyze)
    except Exception as e:
        emit({"ok": False, "error": str(e)})
        return 1
    meta = card["_vidmine"]
    emit({"ok": True, "id": card["id"], "status": meta["status"], "error": meta["error"],
          "sentence": card["sentence"], "meaning": card["meaning"]})
    return 0


def cmd_analyze(cfg, args) -> int:
    from .mine import analyze_card
    lib = Library(cfg)
    cards = list(lib.load().values())
    if args.id:
        todo = [c for c in cards if c["id"] in args.id]
    elif args.all:
        todo = cards
    else:
        todo = [c for c in cards if c.get("_vidmine", {}).get("status") != STATUS_READY]
    failed = 0
    for i, c in enumerate(todo, 1):
        c = analyze_card(cfg, lib, c)
        meta = c["_vidmine"]
        ok = meta["status"] == STATUS_READY
        failed += not ok
        print(f"[{i}/{len(todo)}] {'ok ' if ok else 'ERR'} {c['sentence']}"
              + ("" if ok else f"  ({meta['error']})"), file=sys.stderr)
    print(f"Analyzed {len(todo) - failed}, failed {failed}.", file=sys.stderr)
    return 1 if failed else 0


def cmd_export(cfg, args) -> int:
    from .export import export
    try:
        res = export(cfg, everything=args.all)
    except Exception as e:
        emit({"ok": False, "error": str(e)})
        return 1
    if res["count"]:
        print(f"Exported {res['count']} cards to {res['path']}", file=sys.stderr)
    else:
        print("Nothing new to export.", file=sys.stderr)
    if res["skipped"]:
        print(f"{res['skipped']} cards not analyzed yet; run: analyze", file=sys.stderr)
    emit({"ok": True, **res})
    return 0


def cmd_status(cfg, args) -> int:
    lib = Library(cfg)
    cards = lib.load()
    by = {STATUS_READY: 0, STATUS_PENDING: 0, STATUS_FAILED: 0}
    for c in cards.values():
        by[c.get("_vidmine", {}).get("status", STATUS_PENDING)] += 1
    state = lib.load_state()
    print(f"Library: {lib.root}")
    print(f"Cards: {len(cards)}  ready {by[STATUS_READY]}  pending {by[STATUS_PENDING]}  "
          f"failed {by[STATUS_FAILED]}")
    if state.get("last_export"):
        le = state["last_export"]
        print(f"Last export: {le['at']}  {le['count']} cards  {le['file']}")
    for c in cards.values():
        meta = c.get("_vidmine", {})
        if meta.get("status") == STATUS_FAILED:
            print(f"  FAILED {c['id']}  {c['sentence']}  ({meta.get('error')})")
        for w in meta.get("warnings", []):
            print(f"  warning {c['id']}: {w}")
    return 0


def cmd_transcribe(cfg, args) -> int:
    from .transcribe import download_model, model_ready, srt_path_for, transcribe
    existing = srt_path_for(Path(args.video))
    if existing.exists() and not args.force:
        print(f"Using existing {existing} (--force to redo)", file=sys.stderr)
        emit({"ok": True, "path": str(existing), "cached": True})
        return 0
    try:
        name = args.model or cfg.whisper.model
        if not model_ready(name):
            print(f"Downloading Whisper {name}…", file=sys.stderr)
            download_model(name)
        out = transcribe(cfg, Path(args.video), name,
                         progress=lambda f, t: print(f"\r{t}", end="", file=sys.stderr))
    except Exception as e:
        emit({"ok": False, "error": str(e)})
        return 1
    print(f"Wrote {out}", file=sys.stderr)
    emit({"ok": True, "path": str(out)})
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_io()
    p = argparse.ArgumentParser(prog="vidmine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", help="path to config.toml")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mine")
    m.add_argument("--json", help="read the payload from this file instead of stdin")
    m.add_argument("--no-analyze", action="store_true")
    a = sub.add_parser("analyze")
    a.add_argument("--all", action="store_true")
    a.add_argument("--id", nargs="*")
    e = sub.add_parser("export")
    e.add_argument("--all", action="store_true")
    sub.add_parser("status")
    t = sub.add_parser("transcribe")
    t.add_argument("video")
    t.add_argument("--model")
    t.add_argument("--force", action="store_true", help="re-transcribe even if a transcript exists")
    args = p.parse_args(argv)
    cfg = config_mod.load(Path(args.config) if args.config else None)
    return {"mine": cmd_mine, "analyze": cmd_analyze, "export": cmd_export,
            "status": cmd_status, "transcribe": cmd_transcribe}[args.cmd](cfg, args)
