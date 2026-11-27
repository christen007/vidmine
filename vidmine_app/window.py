"""VidMine main window: video player, Japanese line list, mined cards."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QProgressBar, QPushButton, QSlider, QSplitter,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from vidmine import config, export, mine, subs, transcribe
from vidmine.store import STATUS_READY, Library

from .player import MpvWidget
from .preview import card_html
from .settings_dialog import SettingsDialog
from .whisper_dialog import WhisperSetupDialog
from .workers import Runner

VIDEO_FILTER = "Video files (*.mkv *.mp4 *.avi *.webm *.m4v *.mov *.ts *.wmv *.flv);;All files (*)"
JA_LANGS = ["ja", "jpn", "jp", "japanese"]
EN_LANGS = ["en", "eng", "english"]


def fmt_time(t: float | None) -> str:
    if t is None or t < 0:
        return "0:00"
    s = int(t)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def track_is(t: dict, langs: list[str]) -> bool:
    if (t.get("lang") or "").lower() in langs:
        return True
    title = (t.get("title") or "").lower()
    if any(len(l) > 3 and l in title for l in langs):
        return True
    if langs is JA_LANGS:
        if "日本語" in (t.get("title") or ""):
            return True
        f = (t.get("external-filename") or "").lower()
        if any(x in f for x in (".ja.", ".ja-", ".ja_", ".jp.", ".jpn.", "whisper.srt")):
            return True
    return False


def is_signs(t: dict) -> bool:
    title = (t.get("title") or "").lower()
    return any(w in title for w in ("sign", "song", "forced"))


def pick_track(tracks: list[dict], langs: list[str]) -> dict | None:
    good = [t for t in tracks if track_is(t, langs) and not is_signs(t)]
    text = [t for t in good if t.get("codec") not in subs.IMAGE_CODECS]
    return (text or good or [None])[0]


def track_label(t: dict) -> str:
    bits = [(t.get("lang") or "?").upper()]
    if t.get("title"):
        bits.append(t["title"])
    if t.get("external"):
        bits.append("(" + Path(t.get("external-filename") or "file").name + ")")
    if t.get("codec") in subs.IMAGE_CODECS:
        bits.append("[image]")
    return " ".join(bits)


class MainWindow(QMainWindow):
    def __init__(self, cfg: config.Config, headless: bool = False, selftest: bool = False):
        super().__init__()
        self.cfg = cfg
        self.headless = headless
        self.selftest = selftest
        self.runner = Runner()
        self.path: str | None = None
        self.sub_ids: tuple | None = None
        self.ja_track: dict | None = None
        self.en_track: dict | None = None
        self.lines: list[subs.Line] = []
        self.en_lines: list[subs.Line] = []
        self.ja_token = 0
        self.en_token = 0
        self.current_idx = -1
        self.mining = 0
        self.audio_player = None
        self.last_error = ""
        self.last_export: dict | None = None
        self.sub_offset = 0.0
        self.asr_job = None
        self.asr_result: dict | None = None
        self.prefer_sub_file: str | None = None

        self.setWindowTitle("VidMine")
        self.resize(1400, 820)
        self.setAcceptDrops(True)
        self._build_ui()
        self._build_shortcuts()
        self.player.tracks_changed.connect(self.on_tracks)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.refresh_cards()
        if not self.cfg.claude.resolved_key() and not selftest:
            self.statusBar().showMessage("Welcome! Add your Claude API key in Settings, then open a video.")

    # ---- UI --------------------------------------------------------------------
    def _build_ui(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        self.toolbar = tb
        for text, slot, tip in (("Open video…", self.choose_file, "Ctrl+O"),
                                ("🎙 Transcribe audio", self.start_transcribe,
                                 "Create Japanese subtitles from the audio with Whisper"),
                                ("Export for Kaeru", self.export_cards, "Save new cards as a zip for Kaeru"),
                                ("Settings", self.open_settings, "API key and folders")):
            act = QAction(text, self)
            act.setToolTip(tip)
            act.triggered.connect(slot)
            tb.addAction(act)

        # Left: player + controls
        self.player = MpvWidget(headless=self.headless)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.sliderReleased.connect(lambda: self.seek(self.slider.value() / 1000))
        self.time_label = QLabel("0:00 / 0:00")
        seek_row = QHBoxLayout()
        seek_row.addWidget(self.slider, 1)
        seek_row.addWidget(self.time_label)

        def button(text, slot, tip):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        self.play_btn = button("▶ Play", self.toggle_pause, "Space")
        self.mine_btn = button("⛏  Mine line", self.mine_current, "M: mine the current Japanese line")
        self.mine_btn.setStyleSheet("QPushButton{background:#3d7a4f;color:white;font-weight:bold;padding:4px 14px;}")
        controls = QHBoxLayout()
        controls.addWidget(self.play_btn)
        controls.addWidget(button("⏮ Line", lambda: self.step_line(-1), "Up arrow: previous line"))
        controls.addWidget(button("↺ Replay", self.replay_line, "R: replay the current line"))
        controls.addWidget(button("Line ⏭", lambda: self.step_line(1), "Down arrow: next line"))
        controls.addWidget(self.mine_btn)
        controls.addStretch(1)
        self.speed = QComboBox()
        self.speed.setFocusPolicy(Qt.NoFocus)
        for s in ("0.75×", "0.9×", "1×", "1.25×"):
            self.speed.addItem(s, float(s[:-1]))
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(lambda: self.player.set("speed", self.speed.currentData()))
        controls.addWidget(QLabel("Speed"))
        controls.addWidget(self.speed)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setFocusPolicy(Qt.NoFocus)
        self.volume.setRange(0, 130)
        self.volume.setValue(100)
        self.volume.setFixedWidth(90)
        self.volume.valueChanged.connect(lambda v: self.player.set("volume", v))
        controls.addWidget(QLabel("Vol"))
        controls.addWidget(self.volume)

        tracks = QHBoxLayout()
        self.ja_combo = QComboBox()
        self.en_combo = QComboBox()
        for c in (self.ja_combo, self.en_combo):
            c.setFocusPolicy(Qt.NoFocus)
            c.setMinimumWidth(200)
        self.ja_combo.activated.connect(lambda i: self.select_ja(self.ja_combo.itemData(i)))
        self.en_combo.activated.connect(lambda i: self.select_en(self.en_combo.itemData(i)))
        self.show_en = QCheckBox("Show English (E)")
        self.show_en.setFocusPolicy(Qt.NoFocus)
        self.show_en.toggled.connect(lambda on: self.player.set("secondary-sub-visibility", on))
        tracks.addWidget(QLabel("Japanese subtitles"))
        tracks.addWidget(self.ja_combo)
        tracks.addSpacing(16)
        tracks.addWidget(QLabel("English subtitles"))
        tracks.addWidget(self.en_combo)
        tracks.addWidget(self.show_en)
        tracks.addSpacing(16)
        self.offset_box = QDoubleSpinBox()
        self.offset_box.setRange(-60.0, 60.0)
        self.offset_box.setSingleStep(0.1)
        self.offset_box.setDecimals(1)
        self.offset_box.setSuffix(" s")
        self.offset_box.setToolTip("Shift the Japanese subtitles if they appear too early or late.\n"
                                   "Z = 0.1 s earlier, X = 0.1 s later")
        self.offset_box.valueChanged.connect(self.set_offset)
        tracks.addWidget(QLabel("Subtitle timing"))
        tracks.addWidget(self.offset_box)
        tracks.addStretch(1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.addWidget(self.player, 1)
        self.controls_box = QWidget()
        cl = QVBoxLayout(self.controls_box)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addLayout(seek_row)
        cl.addLayout(controls)
        cl.addLayout(tracks)
        ll.addWidget(self.controls_box)

        # Right: lines + cards
        self.tabs = QTabWidget()
        lines_page = QWidget()
        lp = QVBoxLayout(lines_page)
        self.lines_hint = QLabel("Open a video (or drag one onto this window) to see its Japanese lines.")
        self.lines_hint.setWordWrap(True)
        self.line_list = QListWidget()
        self.line_list.setFocusPolicy(Qt.NoFocus)
        self.line_list.setWordWrap(True)
        self.line_list.setStyleSheet("QListWidget{font-size:15px;} QListWidget::item{padding:5px;}"
                                     "QListWidget::item:selected{background:#2d4a6b;color:white;}")
        self.line_list.itemDoubleClicked.connect(lambda it: self.jump_to(self.line_list.row(it)))
        self.line_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.line_list.customContextMenuRequested.connect(self._line_menu)
        lp.addWidget(self.lines_hint)
        self.whisper_btn = QPushButton("🎙  Create Japanese subtitles from the audio (Whisper)")
        self.whisper_btn.setFocusPolicy(Qt.NoFocus)
        self.whisper_btn.setStyleSheet("QPushButton{padding:8px;font-weight:bold;}")
        self.whisper_btn.clicked.connect(self.start_transcribe)
        self.whisper_btn.hide()
        lp.addWidget(self.whisper_btn)
        self.asr_box = QWidget()
        ab = QVBoxLayout(self.asr_box)
        ab.setContentsMargins(0, 0, 0, 0)
        self.asr_label = QLabel("")
        self.asr_label.setWordWrap(True)
        self.asr_bar = QProgressBar()
        self.asr_bar.setRange(0, 1000)
        self.asr_bar.setTextVisible(False)
        asr_cancel = QPushButton("Cancel")
        asr_cancel.setFocusPolicy(Qt.NoFocus)
        asr_cancel.clicked.connect(self.cancel_transcribe)
        row_ = QHBoxLayout()
        row_.addWidget(self.asr_bar, 1)
        row_.addWidget(asr_cancel)
        ab.addWidget(self.asr_label)
        ab.addLayout(row_)
        self.asr_box.hide()
        lp.addWidget(self.asr_box)
        lp.addWidget(self.line_list, 1)
        lp.addWidget(QLabel("Double-click a line to jump to it · right-click to mine it"))
        self.tabs.addTab(lines_page, "Lines")

        cards_page = QWidget()
        cp = QVBoxLayout(cards_page)
        self.card_list = QListWidget()
        self.card_list.currentItemChanged.connect(lambda *_: self.show_card())
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.card_list)
        split.addWidget(self.preview)
        split.setSizes([220, 520])
        cp.addWidget(split, 1)
        row = QHBoxLayout()
        self.play_audio_btn = button("🔊 Play audio", self.play_card_audio, "Play this card's audio clip")
        self.video_btn = button("🎬 Play video", self.play_card_video, "Open this card's video")
        self.folder_btn = button("Show in folder", self.show_card_video, "Show the card video in File Explorer")
        self.retry_btn = button("Retry analysis", self.retry_card, "Run Claude's analysis again")
        self.delete_btn = button("Delete", self.delete_card, "Remove this card")
        for b in (self.play_audio_btn, self.video_btn, self.folder_btn, self.retry_btn, self.delete_btn):
            row.addWidget(b)
        row.addStretch(1)
        cp.addLayout(row)
        self.tabs.addTab(cards_page, "Cards")

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([960, 440])
        self.setCentralWidget(self.splitter)
        self._fill_combo(self.ja_combo, [], None)
        self._fill_combo(self.en_combo, [], None)

    def _build_shortcuts(self):
        keys = {
            "Space": self.toggle_pause, "Left": lambda: self.seek_rel(-5), "Right": lambda: self.seek_rel(5),
            "Up": lambda: self.step_line(-1), "Down": lambda: self.step_line(1),
            "R": self.replay_line, "M": self.mine_current, "E": lambda: self.show_en.toggle(),
            "F": self.toggle_fullscreen, "Escape": lambda: self.toggle_fullscreen(False),
            "Ctrl+O": self.choose_file,
            "Z": lambda: self.offset_box.setValue(self.offset_box.value() - 0.1),
            "X": lambda: self.offset_box.setValue(self.offset_box.value() + 0.1),
        }
        for k, fn in keys.items():
            sc = QShortcut(QKeySequence(k), self)  # main window only, not dialogs
            sc.activated.connect(fn)

    # ---- files and tracks ----------------------------------------------------------
    def choose_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open video", "", VIDEO_FILTER)
        if f:
            self.open_file(f)

    def open_file(self, path):
        path = str(Path(path).resolve())
        self.player.mpv.play(path)
        self.player.set("pause", False)
        self.statusBar().showMessage(f"Opening {Path(path).name}…", 3000)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.open_file(url.toLocalFile())
                break

    def _fill_combo(self, combo: QComboBox, tracks: list[dict], selected: dict | None):
        combo.clear()
        combo.addItem("None", None)
        for t in tracks:
            combo.addItem(track_label(t), t)
            if selected and t["id"] == selected["id"]:
                combo.setCurrentIndex(combo.count() - 1)

    def on_tracks(self, tracks: list):
        path = self.player.get("path")
        if not path:
            return
        sub_tracks = [t for t in tracks if t.get("type") == "sub"]
        ids = tuple(t["id"] for t in sub_tracks)
        new_file = path != self.path
        if not new_file and ids == self.sub_ids:
            return
        self.sub_ids = ids
        if new_file:
            self.path = path
            self.lines, self.en_lines, self.current_idx = [], [], -1
            self.line_list.clear()
            self.ja_track = self.en_track = None
            self.offset_box.setValue(0.0)
            title = self.player.get("media-title") or Path(path).name
            self.setWindowTitle(f"{title} — VidMine")
        by_id = {t["id"]: t for t in sub_tracks}
        ja = by_id.get(self.ja_track["id"]) if self.ja_track else None
        en = by_id.get(self.en_track["id"]) if self.en_track else None
        if self.prefer_sub_file:  # a transcript we just added
            want = os.path.normcase(os.path.abspath(self.prefer_sub_file))
            for t in sub_tracks:
                f = t.get("external-filename")
                if f and os.path.normcase(os.path.abspath(f)) == want:
                    ja, self.prefer_sub_file = t, None
                    break
        ja = ja or pick_track(sub_tracks, JA_LANGS)
        en = en or pick_track(sub_tracks, EN_LANGS)
        self._fill_combo(self.ja_combo, sub_tracks, ja)
        self._fill_combo(self.en_combo, sub_tracks, en)
        if new_file or (ja and (not self.ja_track or ja["id"] != self.ja_track["id"])):
            self.select_ja(ja)
        if new_file or (en and (not self.en_track or en["id"] != self.en_track["id"])):
            self.select_en(en)

    def _source_of(self, track: dict):
        if track.get("external"):
            return Path(track["external-filename"]), None
        return Path(self.path), track.get("ff-index")

    def select_ja(self, track: dict | None):
        self.ja_track = track
        self.ja_token += 1
        token = self.ja_token
        self.lines, self.current_idx = [], -1
        self.line_list.clear()
        self.player.set("sid", track["id"] if track else "no")
        self.whisper_btn.setVisible(self.asr_job is None and
                                    (not track or track.get("codec") in subs.IMAGE_CODECS))
        if not track:
            self.lines_hint.setText("This video has no Japanese subtitles. Whisper can create them "
                                    "from the audio, or put a Japanese subtitle file next to the "
                                    "video with the same name (e.g. Episode 03.ja.srt).")
            return
        if track.get("codec") in subs.IMAGE_CODECS:
            self.lines_hint.setText("This Japanese track is made of images (PGS/DVD subtitles), which "
                                    "VidMine can't read yet. Whisper can create text subtitles "
                                    "from the audio instead.")
            return
        self.lines_hint.setText("Reading subtitles…")
        source, idx = self._source_of(track)
        self.runner.start(lambda: subs.extract(self.cfg, source, idx),
                          lambda res, tok=token: self._ja_loaded(tok, res),
                          lambda err, tok=token: self._ja_failed(tok, err))

    def _ja_loaded(self, token: int, lines: list):
        if token != self.ja_token:
            return
        self.lines = lines
        self.line_list.clear()
        for l in lines:
            QListWidgetItem(f"{fmt_time(l.start)}   {l.text.replace(chr(10), '　')}", self.line_list)
        src = ("Whisper transcript. Words may occasionally be misheard. "
               if (self.ja_track or {}).get("external-filename", "").lower().endswith(".whisper.srt") else "")
        self.lines_hint.setText(f"{len(lines)} Japanese lines. {src}Press M (or ⛏ Mine line) to mine "
                                "the current one.")

    def _ja_failed(self, token: int, err: str):
        if token == self.ja_token:
            self.lines_hint.setText(f"Couldn't read this subtitle track: {err}")

    def select_en(self, track: dict | None):
        self.en_track = track
        self.en_token += 1
        token = self.en_token
        self.en_lines = []
        self.player.set("secondary-sid", track["id"] if track else "no")
        self.player.set("secondary-sub-visibility", self.show_en.isChecked())
        if not track or track.get("codec") in subs.IMAGE_CODECS:
            return
        source, idx = self._source_of(track)

        def loaded(res, tok=token):
            if tok == self.en_token:
                self.en_lines = res

        self.runner.start(lambda: subs.extract(self.cfg, source, idx), loaded)

    # ---- playback -----------------------------------------------------------------
    def tick(self):
        t = self.player.get("time-pos")
        dur = self.player.get("duration")
        paused = self.player.get("pause", True)
        self.play_btn.setText("▶ Play" if paused else "⏸ Pause")
        if t is None:
            return
        if dur:
            self.slider.setRange(0, int(dur * 1000))
            if not self.slider.isSliderDown():
                self.slider.setValue(int(t * 1000))
        self.time_label.setText(f"{fmt_time(t)} / {fmt_time(dur)}")
        idx = subs.line_at(self.lines, t - self.sub_offset)
        if idx != self.current_idx and 0 <= idx < self.line_list.count():
            self.current_idx = idx
            self.line_list.setCurrentRow(idx)
            self.line_list.scrollToItem(self.line_list.item(idx), QAbstractItemView.PositionAtCenter)

    def toggle_pause(self):
        if self.path:
            self.player.set("pause", not self.player.get("pause", False))

    def seek(self, t: float):
        if self.path:
            try:
                self.player.mpv.seek(max(0.0, t), reference="absolute", precision="exact")
            except Exception:
                pass

    def seek_rel(self, d: float):
        self.seek((self.player.get("time-pos") or 0) + d)

    def jump_to(self, idx: int):
        if 0 <= idx < len(self.lines):
            self.seek(self.lines[idx].start + self.sub_offset)
            self.player.set("pause", False)

    def current_line(self) -> int:
        return subs.line_at(self.lines, (self.player.get("time-pos") or 0) - self.sub_offset)

    def step_line(self, d: int):
        if not self.lines:
            return
        idx = self.current_line()
        t = self.player.get("time-pos") or 0
        if d < 0 and idx >= 0 and t - (self.lines[idx].start + self.sub_offset) > 1.0:
            target = idx  # back to the start of this line first
        else:
            target = idx + d
        self.jump_to(min(max(target, 0), len(self.lines) - 1))

    def replay_line(self):
        idx = self.current_line()
        if idx >= 0:
            self.jump_to(idx)

    def toggle_fullscreen(self, on: bool | None = None):
        on = (not self.isFullScreen()) if on is None else on
        for w in (self.tabs, self.toolbar, self.statusBar(), self.controls_box):
            w.setVisible(not on)
        self.showFullScreen() if on else self.showNormal()

    # ---- mining -----------------------------------------------------------------
    def _line_menu(self, pos):
        item = self.line_list.itemAt(pos)
        if not item:
            return
        row = self.line_list.row(item)
        menu = QMenu(self)
        menu.addAction("⛏ Mine this line", lambda: self.mine_line(row))
        menu.addAction("Play from here", lambda: self.jump_to(row))
        menu.exec(self.line_list.mapToGlobal(pos))

    def mine_current(self):
        idx = self.current_line()
        if idx < 0:
            self.statusBar().showMessage("No Japanese line to mine yet.", 3000)
            return
        self.mine_line(idx)

    def _ensure_key(self) -> bool:
        if self.cfg.claude.resolved_key() or os.environ.get("VIDMINE_FAKE_ANALYSIS"):
            return True
        QMessageBox.information(self, "Claude API key needed",
                                "VidMine uses Claude to break each line down into words and grammar.\n"
                                "Add your API key in the next window.")
        self.open_settings()
        return bool(self.cfg.claude.resolved_key())

    def _ff_index(self, kind: str):
        t = self.player.get(f"current-tracks/{kind}")
        if isinstance(t, dict) and not t.get("external"):
            return t.get("ff-index")
        return None

    def mine_line(self, idx: int):
        if not (0 <= idx < len(self.lines)) or not self._ensure_key():
            return
        line = self.lines[idx]
        start, end = line.start + self.sub_offset, line.end + self.sub_offset
        payload = {
            "path": self.path,
            "title": self.player.get("media-title") or Path(self.path).name,
            "text": line.text,
            "start": start,
            "end": end,
            "english": subs.english_for(self.en_lines, start, end),
            "context_before": [l.text for l in self.lines[max(0, idx - 2):idx]
                               if line.start - l.start < 30],
            "sub_external": bool(self.ja_track and self.ja_track.get("external")),
            "sub_file": (self.ja_track or {}).get("external-filename") or "",
            "audio_ff_index": self._ff_index("audio"),
            "video_ff_index": self._ff_index("video"),
        }
        self.mining += 1
        self._update_cards_tab()
        short = line.text.replace("\n", "　")
        self.statusBar().showMessage(f"Mining 「{short}」…")
        cfg = self.cfg
        self.runner.start(lambda: mine.mine(cfg, payload), self._mined, self._mine_failed)

    def _mined(self, card: dict):
        self.mining -= 1
        meta = card.get("_vidmine", {})
        if meta.get("status") == STATUS_READY:
            extra = ""
            if self.cfg.video.enabled:
                extra = " · video saved" if meta.get("video") and not meta.get("video_error") \
                    else f" · video failed: {meta.get('video_error', '')}"
            self.statusBar().showMessage(f"✓ Mined 「{card['sentence']}」 — {card['meaning']}{extra}", 10000)
        else:
            self.last_error = meta.get("error", "")
            self.statusBar().showMessage(f"Mined, but analysis failed: {self.last_error}", 10000)
        self.refresh_cards(select_id=card["id"])

    def _mine_failed(self, err: str):
        self.mining -= 1
        self.last_error = err
        self._update_cards_tab()
        self.statusBar().showMessage(f"Couldn't mine that line: {err}", 10000)
        if not self.selftest:
            QMessageBox.warning(self, "Couldn't mine that line", err)

    # ---- cards ------------------------------------------------------------------
    def library(self) -> Library:
        return Library(self.cfg)

    def _update_cards_tab(self):
        n = self.card_list.count()
        extra = f" · mining {self.mining}…" if self.mining else ""
        self.tabs.setTabText(1, f"Cards ({n}){extra}")

    def refresh_cards(self, select_id: str | None = None):
        try:
            cards = sorted(self.library().load().values(), key=lambda c: c.get("mined_at", ""), reverse=True)
        except Exception as e:
            self.statusBar().showMessage(f"Couldn't read the card library: {e}")
            cards = []
        current = select_id or (self.card_list.currentItem().data(Qt.UserRole)
                                if self.card_list.currentItem() else None)
        self.card_list.blockSignals(True)
        self.card_list.clear()
        icons = {"ready": "✓", "failed": "⚠", "pending": "⏳"}
        for c in cards:
            status = c.get("_vidmine", {}).get("status", "pending")
            it = QListWidgetItem(f"{icons.get(status, '·')}  {c['sentence']}", self.card_list)
            it.setData(Qt.UserRole, c["id"])
            it.setToolTip(c.get("location", ""))
            if c["id"] == current:
                self.card_list.setCurrentItem(it)
        self.card_list.blockSignals(False)
        self._update_cards_tab()
        self.show_card()

    def selected_card(self) -> dict | None:
        it = self.card_list.currentItem()
        return self.library().get(it.data(Qt.UserRole)) if it else None

    def show_card(self):
        card = self.selected_card()
        for b in (self.play_audio_btn, self.retry_btn, self.delete_btn):
            b.setEnabled(card is not None)
        meta = (card or {}).get("_vidmine", {})
        has_video = bool(meta.get("video")) and Path(meta.get("video", "")).exists()
        can_make = bool(card) and meta.get("status") == STATUS_READY
        self.video_btn.setText("🎬 Play video" if has_video else "🎬 Make video")
        self.video_btn.setEnabled(has_video or can_make)
        self.folder_btn.setEnabled(has_video)
        if not card:
            self.preview.setHtml("<p style='color:#888'>Mined cards appear here. Select one to preview it.</p>")
            return
        width = max(240, self.preview.viewport().width() - 30)
        self.preview.setHtml(card_html(card, self.library().root, width))

    def play_card_audio(self):
        card = self.selected_card()
        if not card or not card.get("audio"):
            return
        if self.audio_player is None:
            import mpv
            self.audio_player = mpv.MPV(vo="null", video=False, ao="null" if self.headless else "auto")
        self.audio_player.play(str(self.library().root / card["audio"]))

    def _open_path(self, path: str, select: bool = False):
        if sys.platform == "win32":
            import subprocess
            if select:
                subprocess.Popen(["explorer", "/select,", path])
            else:
                os.startfile(path)  # opens in the default video player
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent if select else path)))

    def play_card_video(self):
        card = self.selected_card()
        if not card:
            return
        video = card.get("_vidmine", {}).get("video")
        if video and Path(video).exists():
            self._open_path(video)
            return
        self.statusBar().showMessage("Making the card video…")
        cfg = self.cfg

        def work():
            mine.make_video(cfg, card)
            Library(cfg).upsert(card)
            return card

        def done(c):
            err = c.get("_vidmine", {}).get("video_error")
            self.statusBar().showMessage(f"Video failed: {err}" if err else "Card video saved.", 8000)
            self.refresh_cards(c["id"])
        self.runner.start(work, done, lambda e: self._report("Video failed", e))

    def show_card_video(self):
        card = self.selected_card()
        video = (card or {}).get("_vidmine", {}).get("video")
        if video and Path(video).exists():
            self._open_path(video, select=True)

    def retry_card(self):
        card = self.selected_card()
        if not card or not self._ensure_key():
            return
        self.statusBar().showMessage("Re-analyzing…")
        cfg = self.cfg
        self.runner.start(lambda: mine.analyze_card(cfg, Library(cfg), card),
                          lambda c: (self.statusBar().showMessage("Analysis done.", 4000),
                                     self.refresh_cards(c["id"])),
                          lambda e: self.statusBar().showMessage(f"Analysis failed: {e}", 8000))

    def delete_card(self):
        card = self.selected_card()
        if not card:
            return
        if QMessageBox.question(self, "Delete card", f"Delete this card?\n\n{card['sentence']}") \
                != QMessageBox.Yes:
            return
        self.library().delete(card["id"])
        self.refresh_cards()

    # ---- subtitle timing -----------------------------------------------------------
    def set_offset(self, v: float):
        self.sub_offset = round(v, 2)
        self.player.set("sub-delay", self.sub_offset)
        self.current_idx = -1
        if self.path:
            self.statusBar().showMessage(f"Subtitle timing: {self.sub_offset:+.1f} s", 2000)

    # ---- Whisper ------------------------------------------------------------------
    def start_transcribe(self):
        if not self.path:
            self.statusBar().showMessage("Open a video first.", 3000)
            return
        if self.asr_job is not None:
            return
        video = Path(self.path)
        existing = transcribe.find_existing_srt(self.cfg, video)
        if existing and not self.selftest:
            box = QMessageBox(QMessageBox.Question, "Whisper subtitles",
                              "This video already has Whisper subtitles.", parent=self)
            use = box.addButton("Use them", QMessageBox.AcceptRole)
            again = box.addButton("Transcribe again", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is use:
                self.load_transcript(existing)
                return
            if box.clickedButton() is not again:
                return
        name = self.cfg.whisper.model
        has_gpu = transcribe.gpu_count() > 0
        need_cuda = has_gpu and not transcribe.cuda_libs_ready()
        if (need_cuda or not transcribe.model_ready(name)) and not self.selftest:
            dlg = WhisperSetupDialog(name, not transcribe.model_ready(name), need_cuda, has_gpu,
                                     transcribe.model_ready, self)
            if not dlg.exec():
                return
            name = dlg.model()
            if name != self.cfg.whisper.model:
                self.cfg.whisper.model = name
                config.save_app(self.cfg)
        need_model = not transcribe.model_ready(name)
        cfg, audio_index = self.cfg, self._ff_index("audio")

        def work(report, cancel):
            if need_cuda:
                transcribe.download_cuda_libs(report, cancel)
            if need_model:
                transcribe.download_model(name, report, cancel)
            return {"srt": transcribe.transcribe(cfg, video, name, audio_index, report, cancel),
                    "video": str(video)}

        self.whisper_btn.hide()
        self.asr_box.show()
        self.asr_bar.setValue(0)
        self.asr_label.setText("Starting Whisper…")
        self.tabs.setCurrentIndex(0)
        self.asr_job = self.runner.start(work, self._asr_done, self._asr_failed, self._asr_progress)

    def _asr_progress(self, frac: float, text: str):
        self.asr_bar.setValue(int(frac * 1000))
        self.asr_label.setText(text)

    def cancel_transcribe(self):
        if self.asr_job is not None:
            self.asr_job.cancel.set()
            self.asr_label.setText("Cancelling…")

    def _asr_finished(self):
        self.asr_job = None
        self.asr_box.hide()

    def _asr_done(self, res: dict):
        self._asr_finished()
        self.asr_result = res
        if self.path and os.path.normcase(self.path) == os.path.normcase(res["video"]):
            self.load_transcript(res["srt"])
        self.statusBar().showMessage(f"Whisper subtitles ready: {Path(res['srt']).name}", 8000)

    def _asr_failed(self, err: str):
        self._asr_finished()
        self.whisper_btn.setVisible(not self.lines)
        if err == "Cancelled":
            self.statusBar().showMessage("Transcription cancelled.", 4000)
            return
        self.asr_result = {"error": err}
        self._report("Whisper failed", err)

    def load_transcript(self, srt):
        self.prefer_sub_file = str(srt)
        try:
            self.player.mpv.command("sub-add", str(srt), "select", "Whisper (Japanese)", "ja")
        except Exception as e:
            self._report("Couldn't load the Whisper subtitles", str(e))

    # ---- export / settings --------------------------------------------------------
    def export_cards(self, everything: bool = False):
        cfg = self.cfg
        self.statusBar().showMessage("Exporting…")
        self.runner.start(lambda: export.export(cfg, everything=everything),
                          self._exported, lambda e: self._report("Export failed", e))

    def _exported(self, res: dict):
        self.last_export = res
        if self.selftest:
            return
        if not res["count"]:
            msg = "There are no new cards to export."
            if res["skipped"]:
                msg += f"\n\n{res['skipped']} card(s) still need analysis (see the Cards tab)."
            box = QMessageBox(QMessageBox.Information, "Export for Kaeru", msg, parent=self)
            again = box.addButton("Export all cards again", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Ok)
            box.exec()
            if box.clickedButton() is again:
                self.export_cards(everything=True)
            return
        self.statusBar().showMessage(f"Exported {res['count']} cards.", 6000)
        box = QMessageBox(QMessageBox.Information, "Export for Kaeru",
                          f"Exported {res['count']} card(s) to:\n{res['path']}\n\n"
                          "Import this zip in Kaeru's Mine tab.", parent=self)
        open_btn = box.addButton("Show in folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            if sys.platform == "win32":
                import subprocess
                subprocess.Popen(["explorer", "/select,", res["path"]])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(res["path"]).parent)))

    def _report(self, title: str, err: str):
        self.last_error = err
        self.statusBar().showMessage(f"{title}: {err}", 10000)
        if not self.selftest:
            QMessageBox.warning(self, title, err)

    def open_settings(self):
        if SettingsDialog(self.cfg, self).exec():
            self.refresh_cards()
            self.statusBar().showMessage("Settings saved.", 3000)

    def closeEvent(self, e):
        self.timer.stop()
        self.runner.shutdown()
        self.player.shutdown()
        if self.audio_player is not None:
            try:
                self.audio_player.terminate()
            except Exception:
                pass
        super().closeEvent(e)
