"""Launch the VidMine desktop app (also the PyInstaller entry point)."""
import sys

from vidmine_app.main import main

if __name__ == "__main__":
    sys.exit(main())
