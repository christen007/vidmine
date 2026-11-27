"""Settings: Claude API key, folders, grammar seed file."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

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


class SettingsDialog(QDialog):
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
        form.addRow("Claude API key", key_row)
        hint = QLabel('Create one at <a href="https://console.anthropic.com/settings/keys">console.anthropic.com</a>. '
                      "It's stored only on this PC.")
        hint.setOpenExternalLinks(True)
        hint.setWordWrap(True)
        form.addRow("", hint)

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

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
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

    def save(self):
        c = self.cfg
        c.claude.api_key = self.key.text().strip()
        c.claude.model = self.model.currentText().strip() or MODELS[0]
        c.library_dir = Path(self.library.text().strip() or config.Config().library_dir)
        exp = self.exports.text().strip()
        c.export_dir = Path(exp) if exp else None
        c.claude.grammar_seed_files = [self.seed.text().strip()] if self.seed.text().strip() else []
        c.audio.padding_ms = self.padding.value()
        config.save_app(c)
        self.accept()
