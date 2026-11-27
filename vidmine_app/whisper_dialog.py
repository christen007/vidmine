"""First-time Whisper setup: choose a model and confirm the one-time download."""
from __future__ import annotations

from .frame95 import Dialog95, msg
from PySide6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton,
                               QVBoxLayout)

MODEL_CHOICES = [
    ("large-v3", "Best accuracy (recommended)", "about 3.1 GB"),
    ("large-v3-turbo", "Faster, slightly less accurate", "about 1.6 GB"),
]
CUDA_SIZE = "about 1.3 GB"


class WhisperSetupDialog(Dialog95):
    def __init__(self, current_model: str, need_model: bool, need_cuda: bool, has_gpu: bool,
                 model_ready, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up Whisper")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self.body)
        intro = QLabel(
            "<b>Whisper listens to the Japanese audio and writes Japanese subtitles</b> for this "
            "video, so you can mine it like any subtitled video. It writes down what's said; it "
            "doesn't translate. The English on each card still comes from Claude when you mine a line.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        lay.addWidget(QLabel("<b>Model</b>"))
        self.group = QButtonGroup(self)
        for name, label, size in MODEL_CHOICES:
            note = "already downloaded" if model_ready(name) else f"one-time download, {size}"
            rb = QRadioButton(f"{label}  ({note})")
            rb.setProperty("model", name)
            rb.setChecked(name == current_model)
            self.group.addButton(rb)
            lay.addWidget(rb)
        if not self.group.checkedButton():
            self.group.buttons()[0].setChecked(True)

        if has_gpu:
            gpu = ("NVIDIA graphics card found. Whisper will run on it, which is fast "
                   "(a 24-minute episode takes a few minutes).")
            if need_cuda:
                gpu += f" This first time, NVIDIA's GPU libraries are also downloaded ({CUDA_SIZE})."
        else:
            gpu = ("No NVIDIA graphics card was found, so Whisper will run on the processor. That "
                   "works but is slow: it can take longer than the video itself. The faster model "
                   "is a good choice here.")
        g = QLabel(gpu)
        g.setWordWrap(True)
        lay.addSpacing(6)
        lay.addWidget(g)
        foot = QLabel("You can keep watching while it works. Downloads are saved, so this only "
                      "happens once.")
        foot.setWordWrap(True)
        lay.addWidget(foot)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Download and transcribe")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def model(self) -> str:
        return self.group.checkedButton().property("model")
