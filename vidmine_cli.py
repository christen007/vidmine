"""Launcher used by the mpv script: python vidmine_cli.py <command>."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vidmine.cli import main  # noqa: E402

sys.exit(main())
