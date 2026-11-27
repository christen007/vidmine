"""Settings: Claude API key, folders, grammar seed file."""
from __future__ import annotations

from pathlib import Path

from .frame95 import Dialog95, msg
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from vidmine import config

MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]


def _path_row(edit: QLineEdit, pick) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(edit)
    b = QPushButton("Browse…")
    b.clicked.connect(pick)
    lay.addWidget(b)
    return w


class SettingsDialog(Dialog95):
    def __init__(self, cfg: config.Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("VidMine settings")
        self.setMinimumWidth(560)
        form = QFormLayout()

        self.key = QLineEdit(cfg.claude.api_key)
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("sk-ant-…")
        show = QCheckBox("Show")
        show.toggled.connect(lambda on: self.key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        key_row = QWidget()
        kl = QHBoxLayout(key_row)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.addWidget(self.key)
        kl.addWidget(show)
        test = QPushButton("Test connection")
        test.clicked.connect(self.test_connection)
        kl.addWidget(test)
        form.addRow("Claude API key", key_row)
        hint = QLabel('Create one at <a href="https://platform.claude.com/settings/keys">platform.claude.com</a>. '
                      "It's stored only on this PC.")
        hint.setOpenExternalLinks(True)
        hint.setWordWrap(True)
        form.addRow("", hint)

        self.workspace = QLineEdit(cfg.claude.workspace_id)
        self.workspace.setPlaceholderText("Found automatically when you save (wrkspc_…)")
        form.addRow("Workspace ID", self.workspace)

        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(MODELS)
        self.model.setCurrentText(cfg.claude.model)
        form.addRow("Claude model", self.model)

        self.library = QLineEdit(str(cfg.library_dir))
        form.addRow("Library folder", _path_row(self.library, lambda: self._pick_dir(self.library)))
        self.exports = QLineEdit(str(cfg.exports))
        form.addRow("Export folder", _path_row(self.exports, lambda: self._pick_dir(self.exports)))

        seeds = cfg.claude.grammar_seed_files
        self.seed = QLineEdit(seeds[0] if seeds else "")
        self.seed.setPlaceholderText("Optional: your Chrono Trigger cards.jsonl")
        form.addRow("Shared grammar IDs", _path_row(self.seed, self._pick_seed))
        seed_hint = QLabel("Video cards reuse the grammar IDs found in this file, so Kaeru's "
                           "grammar index covers both sources.")
        seed_hint.setWordWrap(True)
        form.addRow("", seed_hint)

        self.padding = QSpinBox()
        self.padding.setRange(0, 2000)
        self.padding.setSingleStep(50)
        self.padding.setSuffix(" ms")
        self.padding.setValue(cfg.audio.padding_ms)
        form.addRow("Audio padding", self.padding)

        self.whisper = QComboBox()
        self.whisper.addItem("Best accuracy (large-v3)", "large-v3")
        self.whisper.addItem("Faster (large-v3-turbo)", "large-v3-turbo")
        i = self.whisper.findData(cfg.whisper.model)
        self.whisper.setCurrentIndex(max(0, i))
        form.addRow("Whisper model", self.whisper)

        self.theme = QComboBox()
        self.theme.addItem("Windows 95", "win95")
        self.theme.addItem("Modern", "modern")
        self.theme.setCurrentIndex(max(0, self.theme.findData(cfg.theme)))
        form.addRow("Appearance", self.theme)

        self.video_on = QCheckBox("Also make a video for each mined line (clip + lesson panel)")
        self.video_on.setChecked(cfg.video.enabled)
        form.addRow("Card videos", self.video_on)
        self.lead = QDoubleSpinBox()
        self.tail = QDoubleSpinBox()
        for box, val in ((self.lead, cfg.video.lead_s), (self.tail, cfg.video.tail_s)):
            box.setRange(0.0, 15.0)
            box.setSingleStep(0.5)
            box.setDecimals(1)
            box.setSuffix(" s")
            box.setValue(val)
        times = QWidget()
        tl = QHBoxLayout(times)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(QLabel("before"))
        tl.addWidget(self.lead)
        tl.addWidget(QLabel("after"))
        tl.addWidget(self.tail)
        tl.addStretch(1)
        form.addRow("Extra video time", times)
        self.videos = QLineEdit(str(cfg.videos_dir))
        form.addRow("Video folder", _path_row(self.videos, lambda: self._pick_dir(self.videos)))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self.body)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _pick_dir(self, edit: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text())
        if d:
            edit.setText(d)

    def _pick_seed(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose cards.jsonl", self.seed.text(),
                                           "Card files (*.jsonl);;All files (*)")
        if f:
            self.seed.setText(f)

    def _run_check(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from vidmine.analyze import clean_key, find_working_setup
        key = clean_key(self.key.text())
        model = self.model.currentText().strip() or MODELS[0]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return key, find_working_setup(key, self.workspace.text().strip(), model)
        finally:
            QApplication.restoreOverrideCursor()

    def test_connection(self):
        from vidmine.analyze import clean_key, key_problem
        key = clean_key(self.key.text())
        if not key:
            msg(self, "Test connection", "Paste your API key first.")
            return
        if key_problem(key):
            msg(self, "Test connection", key_problem(key), "warning")
            return
        _key, (ok, ws, auth, msg, report) = self._run_check()
        verdict = ("✓ Working. Click Save to keep these settings." + (f" {msg}" if msg else "")
                   if ok else f"✗ {msg}")
        if ok or (ok is False and "no credits" in msg):
            self.workspace.setText(ws)
            self._auth = auth
        ReportDialog(verdict, "\n".join(report), self).exec()

    def save(self):

        from vidmine.analyze import clean_key, key_problem
        c = self.cfg
        key = clean_key(self.key.text())
        ws = self.workspace.text().strip()
        auth = getattr(self, "_auth", c.claude.auth)
        if key and (key != c.claude.api_key or ws != c.claude.workspace_id or not getattr(self, "_auth", None)):
            if key_problem(key):
                msg(self, "Claude API key", key_problem(key), "warning")
                return
            key, (ok, ws, auth, why, report) = self._run_check()
            if ok is False and "no credits" in why:
                # The key itself works; save it and just warn about the balance.
                msg(self, "Claude API key", "Key accepted and saved. However: " + why, "warning")
            elif ok is False:
                ReportDialog("✗ " + why + "\n\nThe settings were not saved. Fix the problem above, or "
                             "send the details below to get help.", "\n".join(report), self).exec()
                return
            elif ok is None:
                msg(self, "Claude API key", why + "\nThe key is saved anyway.")
            elif why:
                msg(self, "Claude API key", "Key accepted. " + why)
            self.workspace.setText(ws)
        c.claude.api_key = key
        c.claude.workspace_id = ws
        c.claude.auth = auth
        c.claude.model = self.model.currentText().strip() or MODELS[0]
        c.library_dir = Path(self.library.text().strip() or config.Config().library_dir)
        exp = self.exports.text().strip()
        c.export_dir = Path(exp) if exp else None
        c.claude.grammar_seed_files = [self.seed.text().strip()] if self.seed.text().strip() else []
        c.audio.padding_ms = self.padding.value()
        c.whisper.model = self.whisper.currentData()
        c.video.enabled = self.video_on.isChecked()
        c.video.lead_s = self.lead.value()
        c.video.tail_s = self.tail.value()
        vd = self.videos.text().strip()
        c.video_dir = Path(vd) if vd and Path(vd) != c.library_dir / "Videos" else None
        new_theme = self.theme.currentData()
        theme_changed = new_theme != c.theme
        c.theme = new_theme
        config.save_app(c)
        if theme_changed:
            msg(self, "Appearance", "The new appearance takes effect the next time you start VidMine.")
        self.accept()


class ReportDialog(Dialog95):
    """Shows a connection check result with copyable details (the key is shortened)."""

    def __init__(self, verdict: str, details: str, parent=None):
        from PySide6.QtWidgets import QApplication, QPlainTextEdit
        super().__init__(parent)
        self.setWindowTitle("Claude connection")
        self.setMinimumSize(640, 360)
        lay = QVBoxLayout(self.body)
        v = QLabel(verdict)
        v.setWordWrap(True)
        lay.addWidget(v)
        box = QPlainTextEdit(details)
        box.setReadOnly(True)
        lay.addWidget(box, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy = buttons.addButton("Copy details", QDialogButtonBox.ActionRole)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(verdict + "\n\n" + details))
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
