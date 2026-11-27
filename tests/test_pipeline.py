"""End-to-end tests with a synthetic video. Run: python -m pytest tests"""
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vidmine import analyze, config, export, mine, transcribe  # noqa: E402
from vidmine.store import Library  # noqa: E402

JA_SRT = """1
00:00:01,000 --> 00:00:03,500
（ジナ）どうせゆうべ、こうふんして
ねつけなかったんでしょ？

2
00:00:04,000 --> 00:00:07,000
ま、建国千年のお祭りだから無理ないけど……
"""
EN_SRT = """1
00:00:01,000 --> 00:00:03,500
You were so excited you couldn't sleep, weren't you?

2
00:00:04,000 --> 00:00:07,000
Well, it is the Millennial Fair.
"""

FAKE = {
    "speaker": "", "speech_style": "standard",
    "meaning": "Well, it's the kingdom's thousandth-anniversary festival, so I can't blame you…",
    "note": "",
    "tokens": [
        {"surface": "ま", "reading": "", "dictionary_form": "ま", "gloss": "well", "pos": "expr", "game_term": False},
        {"surface": "建国", "reading": "けんこく", "dictionary_form": "建国", "gloss": "founding of a nation", "pos": "noun", "game_term": False},
        {"surface": "千年", "reading": "センネン", "dictionary_form": "千年", "gloss": "a thousand years", "pos": "noun", "game_term": False},
        {"surface": "の", "reading": "の", "dictionary_form": "の", "gloss": "of", "pos": "particle", "game_term": False},
        {"surface": "お祭り", "reading": "おまつり", "dictionary_form": "お祭り", "gloss": "festival", "pos": "noun", "game_term": False},
        {"surface": "だから", "reading": "", "dictionary_form": "だから", "gloss": "because it's…", "pos": "conj", "game_term": False},
        {"surface": "無理ない", "reading": "むりない", "dictionary_form": "無理ない", "gloss": "no wonder", "pos": "expr", "game_term": False},
        {"surface": "けど", "reading": "", "dictionary_form": "けど", "gloss": "but…", "pos": "particle", "game_term": False},
    ],
    "grammar": [{"id": "muri-nai", "pattern": "無理ない", "explanation": "Understandable, no wonder."}],
}


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    (d / "ja.srt").write_text(JA_SRT, encoding="utf-8")
    (d / "en.srt").write_text(EN_SRT, encoding="utf-8")
    out = d / "[Fansub] Test Show - 03 (1080p).mkv"
    # Anamorphic 720x480 (SAR 32:27) to check display-aspect frame grabs.
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=720x480:rate=24:duration=9",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=9",
        "-i", str(d / "ja.srt"), "-i", str(d / "en.srt"),
        "-map", "0:v", "-map", "1:a", "-map", "2", "-map", "3",
        "-c:v", "libx264", "-preset", "ultrafast", "-vf", "setsar=32/27",
        "-c:a", "aac", "-c:s", "srt",
        "-metadata:s:s:0", "language=jpn", "-metadata:s:s:1", "language=eng", str(out)],
        check=True)
    return out


@pytest.fixture
def cfg(tmp_path):
    c = config.Config()
    c.library_dir = tmp_path / "lib"
    return c


def payload(video, **kw):
    p = {"path": str(video), "title": video.name,
         "text": "ま、建国千年のお祭りだから無理ないけど……",
         "start": 4.0, "end": 7.0, "english": "Well, it is the Millennial Fair.",
         "context_before": ["（ジナ）どうせゆうべ、こうふんして\nねつけなかったんでしょ？"],
         "sub_external": False, "sub_file": "", "audio_ff_index": 1, "video_ff_index": 0}
    p.update(kw)
    return p


def test_clean_line():
    assert mine.clean_line("（ジナ）どうせゆうべ、こうふんして\nねつけなかったんでしょ？") == \
        ("どうせゆうべ、こうふんして　ねつけなかったんでしょ？", "ジナ")
    assert mine.clean_line("（拍手）\n≪ありがとう≫") == ("ありがとう", "")
    assert mine.clean_line("（拍手）") == ("", "")
    assert mine.clean_title("[Fansub] Test Show - 03 (1080p).mkv") == "Test Show - 03"


def test_furigana_and_readings():
    card = {"sentence": "ま、建国千年のお祭りだから無理ないけど……"}
    warnings = analyze.apply_analysis(card, json.loads(json.dumps(FAKE)))
    assert warnings == []
    assert card["furigana"] == "ま、 建国[けんこく] 千年[せんねん]の お祭り[おまつり]だから 無理ない[むりない]けど……"
    by = {t["surface"]: t for t in card["tokens"]}
    assert by["千年"]["reading"] == "せんねん"   # katakana normalized
    assert by["の"]["reading"] == ""            # no kanji -> empty


def test_coverage_warning():
    card = {"sentence": "ま、建国千年のお祭り"}
    bad = dict(FAKE, tokens=FAKE["tokens"][:2])
    w = analyze.apply_analysis(card, bad)
    assert any("千年のお祭り" in x for x in w)


def test_mine_analyze_export(video, cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "call_claude", lambda c, msg: calls.append(msg) or FAKE)
    card = mine.mine(cfg, payload(video))
    assert card["_vidmine"]["status"] == "ready"
    assert card["id"].startswith("vid-jp:") and card["id"].endswith(":4000")
    assert card["location"] == "Test Show - 03 @ 0:04"
    assert card["context_before"] == ["どうせゆうべ、こうふんして　ねつけなかったんでしょ？"]
    assert "KNOWN_GRAMMAR_IDS" in calls[0]

    lib = Library(cfg)
    scene = Image.open(lib.root / card["images"]["scene"])
    raw = Image.open(lib.root / card["images"]["scene_original"])
    assert scene.size == raw.size


def test_frame_aspect_and_audio(video, cfg, monkeypatch):
    monkeypatch.setattr(analyze, "call_claude", lambda c, msg: FAKE)
    card = mine.mine(cfg, payload(video))
    lib = Library(cfg)
    raw = Image.open(lib.root / card["images"]["scene_original"])
    assert abs(raw.width / raw.height - 16 / 9) < 0.01
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(lib.root / card["audio"])], capture_output=True, text=True).stdout)
    assert 3.3 < dur < 3.8   # 3 s line + 2 x 250 ms padding


def test_export_upsert_and_incremental(video, cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(analyze, "call_claude", lambda c, msg: FAKE)
    mine.mine(cfg, payload(video))
    mine.mine(cfg, payload(video, text=JA_SRT.split("\n")[2] + "\n" + JA_SRT.split("\n")[3],
                           start=1.0, end=3.5, english=""))
    res = export.export(cfg)
    assert res["count"] == 2
    with zipfile.ZipFile(res["path"]) as z:
        names = set(z.namelist())
        lines = z.read("VID_Cards/cards.jsonl").decode("utf-8").strip().split("\n")
        cards = [json.loads(l) for l in lines]
        for c in cards:
            assert c["schema"] == "vid-jp-card/1"
            assert not any(k.startswith("_") for k in c)
            for rel in (c["images"]["scene"], c["images"]["scene_original"], c["audio"]):
                assert f"VID_Cards/{rel}" in names
            assert c["images"]["card"] is None and c["choices"] == []
    first = next(c for c in cards if c["media"]["start_ms"] == 1000)
    assert first["speaker"] == "ジナ" and first["english_source"] == ""

    assert export.export(cfg)["count"] == 0            # nothing new
    mine.mine(cfg, payload(video, english="Changed"))    # re-mine same line -> same id, new content
    assert len(Library(cfg).load()) == 2
    assert export.export(cfg)["count"] == 1
    assert export.export(cfg, everything=True)["count"] == 2


def test_failed_analysis_kept_and_skipped(video, cfg, monkeypatch):
    def boom(c, m):
        raise analyze.AnalysisError("HTTP 401: bad key")
    monkeypatch.setattr(analyze, "call_claude", boom)
    card = mine.mine(cfg, payload(video))
    assert card["_vidmine"]["status"] == "failed"
    assert export.export(cfg) == {"count": 0, "skipped": 1, "path": ""}


def test_cli_mine_no_analyze(video, cfg, tmp_path):
    conf = tmp_path / "config.toml"
    conf.write_text(f'library_dir = "{(tmp_path / "clilib").as_posix()}"\n', encoding="utf-8")
    proc = subprocess.run([sys.executable, str(ROOT / "vidmine_cli.py"), "--config", str(conf),
                           "mine", "--no-analyze"],
                          input=json.dumps(payload(video), ensure_ascii=False).encode("utf-8"),
                          capture_output=True)
    out = json.loads(proc.stdout.decode("utf-8").strip().splitlines()[-1])
    assert out["ok"] and out["status"] == "pending", proc.stderr


def test_whisper_line_splitting():
    words = [(0.0, 0.4, "今日"), (0.4, 0.6, "は"), (0.6, 1.0, "いい"), (1.0, 1.4, "天気"),
             (1.4, 1.8, "ですね。"), (3.5, 4.0, "ご視聴ありがとうございました")]
    lines = transcribe.split_words(words)
    assert lines == [(0.0, 1.8, "今日はいい天気ですね。")]


def test_subtitle_tracks(video, cfg):
    from vidmine import subs
    ja = subs.extract(cfg, video, 2)
    en = subs.extract(cfg, video, 3)
    assert [l.text.split("\n")[0] for l in ja] == ["（ジナ）どうせゆうべ、こうふんして", "ま、建国千年のお祭りだから無理ないけど……"]
    assert abs(ja[0].start - 1.0) < 0.05 and abs(ja[1].end - 7.0) < 0.05
    assert subs.line_at(ja, 0.5) == -1 and subs.line_at(ja, 3.8) == 0 and subs.line_at(ja, 5) == 1
    assert subs.english_for(en, ja[1].start, ja[1].end) == "Well, it is the Millennial Fair."


def test_parse_ass_style_srt():
    from vidmine import subs
    data = "1\n00:00:01,000 --> 00:00:02,000\n<i>{\\an8}こんにちは</i>\n\n2\n00:00:01,000 --> 00:00:02,000\nこんにちは\n\n"
    out = subs.parse_srt(data)
    assert len(out) == 1 and out[0].text == "こんにちは"


def test_app_settings_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    c = config.load_app(p)
    c.claude.api_key = "sk-test"
    c.library_dir = tmp_path / "lib"
    config.save_app(c, p)
    c2 = config.load_app(p)
    assert c2.claude.api_key == "sk-test" and c2.library_dir == tmp_path / "lib"


def test_whisper_download_helpers(tmp_path, monkeypatch):
    import io
    import urllib.request
    monkeypatch.setenv("VIDMINE_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("VIDMINE_CUDA_DIR", str(tmp_path / "cuda"))
    pypi = {"releases": {
        "9.1.0.70": [{"filename": "nvidia_cudnn_cu12-9.1.0.70-py3-none-win_amd64.whl", "url": "https://x/u91", "size": 5}],
        "9.10.2.21": [{"filename": "nvidia_cudnn_cu12-9.10.2.21-py3-none-win_amd64.whl", "url": "https://x/u910", "size": 7},
                      {"filename": "nvidia_cudnn_cu12-9.10.2.21-py3-none-manylinux.whl", "url": "lin", "size": 7}],
        "10.0.0": [{"filename": "nvidia_cudnn_cu12-10.0.0-py3-none-win_amd64.whl", "url": "u10", "size": 9}],
        "9.11.0rc1": [{"filename": "nvidia_cudnn_cu12-9.11.0rc1-py3-none-win_amd64.whl", "url": "rc", "size": 9}],
    }}
    present = {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"}
    monkeypatch.setattr(transcribe, "_get_json", lambda url: pypi)
    monkeypatch.setattr(transcribe, "_head_size",
                        lambda url: 3 if url.rsplit("/", 1)[-1] in present else None)
    assert transcribe.cuda_wheels({"nvidia-cudnn-cu12": "9"}) == [("nvidia-cudnn-cu12", "https://x/u910", 7)]
    assert sorted(p for p, _ in transcribe.model_files("tiny")) == \
        ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]

    # Fake wheel: only nvidia/*/bin/*.dll members are extracted.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("nvidia/cudnn/bin/cudnn64_9.dll", b"dll")
        z.writestr("nvidia/cudnn/include/cudnn.h", b"h")

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: Resp(buf.getvalue()))
    transcribe.download_cuda_libs(packages={"nvidia-cudnn-cu12": "9"})
    assert sorted(p.name for p in (tmp_path / "cuda").iterdir()) == ["cudnn64_9.dll"]
    seen = []
    transcribe.download_model("tiny", progress=lambda f, t: seen.append(f))
    assert transcribe.model_ready("tiny") and seen[-1] == 1.0


def test_clean_key_and_segment_splitting():
    assert analyze.clean_key('  "sk-ant-abc\n123"  ') == "sk-ant-abc123"
    assert analyze.clean_key("Bearer sk-ant-xyz") == "sk-ant-xyz"
    # a short fragment isn't cut off on its own just because of a pause
    words = [(0.0, 0.3, "卵"), (1.5, 2.4, "も買います")]
    assert transcribe.split_words(words) == [(0.0, 2.4, "卵も買います")]


def _fake_api(monkeypatch, handler):
    import io
    import urllib.error
    import urllib.request
    seen = []

    class Resp(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=0):
        h = {k.lower(): v for k, v in req.header_items()}
        seen.append((req.full_url, h))
        code, body = handler(req.full_url, h)
        if code == 200:
            return Resp(json.dumps(body).encode())
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(json.dumps(body).encode()))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_auth_finds_workspace(monkeypatch):
    def handler(url, h):
        if "workspaces" in url:
            return 200, {"data": [{"id": "wrkspc_other", "name": "Other"},
                                  {"id": "wrkspc_def", "name": "Default Workspace"}]}
        if h.get("anthropic-workspace-id") == "wrkspc_def" and "authorization" in h:
            return 200, {"content": []}
        return 401, {"error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    seen = _fake_api(monkeypatch, handler)
    ok, ws, auth, msg, report = analyze.find_working_setup("sk-ant-usr-abcdefghijklmnop")
    assert ok and ws == "wrkspc_def" and auth == "bearer" and "Default Workspace" in msg
    assert not any("abcdefghijklmnop" in line for line in report[1:])  # key never fully printed
    assert "sk-ant-usr-abc" in report[0] and "mnop" in report[0]


def test_auth_falls_back_to_x_api_key_and_reports_credits(monkeypatch):
    _fake_api(monkeypatch, lambda url, h: (200, {}) if "x-api-key" in h else
              (401, {"error": {"type": "authentication_error", "message": "bad"}}))
    ok, ws, auth, msg, _ = analyze.find_working_setup("sk-ant-api03-xyz")
    assert ok and auth == "x-api-key"
    _fake_api(monkeypatch, lambda url, h: (400, {"error": {
        "type": "invalid_request_error", "message": "Your credit balance is too low to access the API."}}))
    ok, ws, auth, msg, _ = analyze.find_working_setup("sk-ant-usr-xyz")
    assert ok is False and "no credits" in msg


def test_structured_output_request_and_parsing(monkeypatch):
    sent = []

    def handler(url, h):
        return 200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(FAKE)}]}
    seen = _fake_api(monkeypatch, handler)
    import urllib.request
    real = urllib.request.urlopen

    def capture(req, timeout=0):
        sent.append(json.loads(req.data.decode("utf-8")))
        return real(req, timeout)
    monkeypatch.setattr(urllib.request, "urlopen", capture)
    c = config.Config()
    c.claude.api_key = "sk-ant-usr-" + "x" * 90
    out = analyze.call_claude(c, analyze.build_user_message({"sentence": "テスト"}, {}))
    assert out["meaning"] == FAKE["meaning"]
    body = sent[0]
    assert "tools" not in body and "tool_choice" not in body
    schema = body["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["tokens"]["items"]["additionalProperties"] is False
    assert seen[0][1]["authorization"].startswith("Bearer ")


def test_key_problem():
    assert "shortened preview" in analyze.key_problem("sk-ant-usr-1UY...ZwAA")
    assert "characters" in analyze.key_problem("sk-ant-usr-abc")
    assert analyze.key_problem("sk-ant-usr-" + "a" * 95) == ""
    with pytest.raises(analyze.AnalysisError):
        analyze.parse_card_response({"stop_reason": "max_tokens", "content": []})


def test_card_video(video, cfg, monkeypatch):
    from vidmine import cardvideo
    monkeypatch.setattr(analyze, "call_claude", lambda c, msg: FAKE)
    card = mine.mine(cfg, payload(video))
    out = cardvideo.make_card_video(cfg, card, video, 1, 0)
    assert out.exists() and out.parent.parent == cfg.videos_dir
    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
         "-of", "json", str(out)], capture_output=True, text=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert v["width"] == 1024 and v["height"] > 576 + 500
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert 4.7 < float(info["format"]["duration"]) < 5.4   # 3 s line + 1 s before + 1 s after
