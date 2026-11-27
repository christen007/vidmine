"""Built-app self-test, run on the build machine: VidMine.exe --selftest result.json

Generates a small video with Japanese and English subtitle tracks, opens it in the
real window (with video/audio output switched off), mines a line with offline
analysis, previews the card and exports a zip. Writes the outcome to result.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

JA = ("1\n00:00:01,000 --> 00:00:03,500\n（ジナ）どうせゆうべ、こうふんして\nねつけなかったんでしょ？\n\n"
      "2\n00:00:04,000 --> 00:00:07,000\nま、建国千年のお祭りだから無理ないけど……\n\n")
EN = ("1\n00:00:01,000 --> 00:00:03,500\nYou couldn't sleep, could you?\n\n"
      "2\n00:00:04,000 --> 00:00:07,000\nWell, it is the Millennial Fair.\n\n")


def make_video(ffmpeg: str, d: Path) -> Path:
    (d / "ja.srt").write_text(JA, encoding="utf-8")
    (d / "en.srt").write_text(EN, encoding="utf-8")
    out = d / "Self Test - 01.mkv"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=9",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=9",
                    "-i", str(d / "ja.srt"), "-i", str(d / "en.srt"),
                    "-map", "0:v", "-map", "1:a", "-map", "2", "-map", "3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-c:s", "srt",
                    "-metadata:s:s:0", "language=jpn", "-metadata:s:s:1", "language=eng", str(out)],
                   check=True, capture_output=True, creationflags=0x08000000 if os.name == "nt" else 0)
    return out


def run(app, out_path: Path) -> int:
    from PySide6.QtCore import QCoreApplication

    from vidmine import config
    from vidmine.store import Library

    result: dict = {"ok": False, "steps": []}

    def step(name, **info):
        result["steps"].append({"step": name, **info})

    def wait(cond, timeout, what):
        end = time.time() + timeout
        while time.time() < end:
            QCoreApplication.processEvents()
            if cond():
                return
            time.sleep(0.05)
        raise TimeoutError(f"timed out waiting for {what}")

    win = None

    def diag():
        if win is None:
            return {}
        tl = win.player.get("track-list", [])
        return {"path": win.player.get("path"), "time_pos": win.player.get("time-pos"),
                "tracks": [{k: t.get(k) for k in ("id", "type", "lang", "codec", "ff-index", "external")}
                           for t in tl],
                "win_path": win.path, "ja": win.ja_combo.currentText(), "en": win.en_combo.currentText(),
                "hint": win.lines_hint.text(), "lines": len(win.lines), "en_lines": len(win.en_lines),
                "busy": win.runner.busy, "last_error": win.last_error,
                "idle": win.player.get("idle-active"), "mpv_log": list(win.player.log)[-60:]}

    try:
        os.environ["VIDMINE_FAKE_ANALYSIS"] = "1"
        tmp = Path(tempfile.mkdtemp(prefix="vidmine_selftest_"))
        cfg = config.load_app(tmp / "settings.json")
        cfg.library_dir = tmp / "library"
        cfg.export_dir = tmp / "exports"
        step("config", ffmpeg=cfg.ffmpeg, font=cfg.image.font)
        video = make_video(cfg.ffmpeg, tmp)
        step("video")

        import mpv  # noqa: F401
        step("libmpv")
        from .settings_dialog import SettingsDialog
        from .window import MainWindow
        SettingsDialog(cfg).close()
        win = MainWindow(cfg, headless=True, selftest=True)
        win.show()
        step("window")

        win.open_file(video)
        wait(lambda: len(win.lines) >= 2 and len(win.en_lines) >= 2, 60, "subtitle lines")
        step("subtitles", lines=[l.text for l in win.lines], ja=win.ja_combo.currentText(),
             en=win.en_combo.currentText())

        wait(lambda: (win.player.get("time-pos") or 0) > 1.2, 30, "playback")
        wait(lambda: win.current_idx >= 0, 10, "current line highlight")
        step("playback", current_line=win.current_idx)

        win.mine_line(1)
        wait(lambda: win.mining == 0 and not win.runner.busy, 90, "mining")
        cards = list(Library(cfg).load().values())
        if len(cards) != 1 or cards[0]["_vidmine"]["status"] != "ready":
            raise AssertionError(f"mining failed: {win.last_error or cards}")
        card = cards[0]
        if card["official_english"] != "Well, it is the Millennial Fair.":
            raise AssertionError(f"english not aligned: {card['official_english']!r}")
        step("mine", id=card["id"], sentence=card["sentence"], context=card["context_before"])
        video = Path(card["_vidmine"].get("video") or "")
        if not video.is_file() or video.stat().st_size < 20_000:
            raise AssertionError(f"card video missing: {card['_vidmine'].get('video_error') or video}")
        from vidmine.cardpanel import Fonts
        step("card video", file=video.name, kb=video.stat().st_size // 1000, fonts=[Fonts(cfg).reg, Fonts(cfg).bold])

        win.card_list.setCurrentRow(0)
        QCoreApplication.processEvents()
        if "(self-test)" not in win.preview.toPlainText():
            raise AssertionError("card preview did not render")
        step("preview")

        win.export_cards()
        wait(lambda: win.last_export is not None, 60, "export")
        with zipfile.ZipFile(win.last_export["path"]) as z:
            names = z.namelist()
            exported = json.loads(z.read("VID_Cards/cards.jsonl").decode("utf-8").splitlines()[0])
        for rel in (exported["images"]["scene"], exported["images"]["scene_original"], exported["audio"]):
            if f"VID_Cards/{rel}" not in names:
                raise AssertionError(f"missing {rel} in export")
        step("export", files=len(names))
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        try:
            result["diag"] = diag()
        except Exception:
            result["diag_error"] = traceback.format_exc()
    finally:
        if win is not None:
            try:
                win.close()
            except Exception:
                pass
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if result["ok"] else 1


def run_whisper(app, out_path: Path, video: Path) -> int:
    """VidMine.exe --selftest-whisper result.json speech.mkv

    Checks the real download sources (Hugging Face model lists, NVIDIA wheels on PyPI),
    downloads the tiny model and the small CUDA runtime package, then transcribes a
    spoken (English) test video through the window and mines a line from it."""
    from PySide6.QtCore import QCoreApplication

    from vidmine import config, transcribe
    from vidmine.store import Library

    result: dict = {"ok": False, "steps": []}
    win = None

    def step(name, **info):
        result["steps"].append({"step": name, **info})

    def wait(cond, timeout, what):
        end = time.time() + timeout
        while time.time() < end:
            QCoreApplication.processEvents()
            if cond():
                return
            time.sleep(0.05)
        raise TimeoutError(f"timed out waiting for {what}")

    try:
        tmp = Path(tempfile.mkdtemp(prefix="vidmine_asr_test_"))
        os.environ.update({"VIDMINE_FAKE_ANALYSIS": "1", "VIDMINE_WHISPER_LANGUAGE": "en",
                           "VIDMINE_MODELS_DIR": str(tmp / "models"), "VIDMINE_CUDA_DIR": str(tmp / "cuda")})
        cfg = config.load_app(tmp / "settings.json")
        cfg.library_dir = tmp / "library"
        cfg.whisper.model = "tiny"

        sources, bad = {}, []
        for n in ("large-v3", "large-v3-turbo"):
            try:
                repo, files = transcribe.model_source(n)
                sources[n] = {"repo": repo, **{p: round(sz / 1e6) for p, sz in files}}
            except Exception as e:
                sources[n] = f"ERROR {e}"
                bad.append(n)
        step("model sources", mb=sources)
        if bad:
            raise AssertionError(f"model downloads not available: {bad}")
        wheels = transcribe.cuda_wheels()
        step("cuda sources", wheels=[(p, u.rsplit("/", 1)[-1], round(s / 1e6)) for p, u, s in wheels],
             total_mb=round(sum(s for _, _, s in wheels) / 1e6))
        transcribe.download_cuda_libs(packages={"nvidia-cuda-runtime-cu12": "12"})
        dlls = sorted(p.name for p in transcribe.cuda_dir().iterdir())
        if not any(d.lower().startswith("cudart64_12") for d in dlls):
            raise AssertionError(f"cudart not extracted: {dlls}")
        step("cuda extract", dlls=dlls)

        import ctranslate2
        step("ctranslate2", version=ctranslate2.__version__, gpus=transcribe.gpu_count())

        from .window import MainWindow
        win = MainWindow(cfg, headless=True, selftest=True)
        win.show()
        win.open_file(video)
        wait(lambda: win.path is not None, 30, "video to open")
        wait(lambda: win.whisper_btn.isVisible(), 10, "Whisper button (no subtitles)")
        step("no subtitles -> whisper button")

        t0 = time.time()
        win.start_transcribe()
        wait(lambda: win.asr_job is None, 900, "transcription")
        if not win.asr_result or "error" in win.asr_result:
            raise AssertionError(f"transcription failed: {win.asr_result}")
        wait(lambda: len(win.lines) >= 1, 30, "transcript lines")
        step("transcribe", seconds=round(time.time() - t0), lines=[l.text for l in win.lines][:10],
             track=win.ja_combo.currentText())

        win.mine_line(0)
        wait(lambda: win.mining == 0 and not win.runner.busy, 90, "mining")
        cards = list(Library(cfg).load().values())
        if len(cards) != 1 or cards[0]["source"] != "asr":
            raise AssertionError(f"expected one asr card: {win.last_error or cards}")
        step("mine", source=cards[0]["source"], sentence=cards[0]["sentence"])
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        if win is not None:
            result["diag"] = {"hint": win.lines_hint.text(), "asr": win.asr_result,
                              "asr_label": win.asr_label.text(), "last_error": win.last_error,
                              "mpv_log": list(win.player.log)[-30:]}
    finally:
        if win is not None:
            try:
                win.close()
            except Exception:
                pass
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if result["ok"] else 1
