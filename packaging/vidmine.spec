# PyInstaller spec for the VidMine Windows app. Build: pyinstaller --noconfirm packaging/vidmine.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH).parent
deps = root / "deps"

binaries = [(str(deps / "libmpv-2.dll"), "."), (str(deps / "ffmpeg.exe"), ".")]
binaries += collect_dynamic_libs("ctranslate2")
datas = [(str(root / "KAERU_VIDEO_IMPORT_SPEC.md"), ".")]
datas += collect_data_files("faster_whisper")  # includes the Silero VAD model
font = deps / "NotoSansJP-Bold.otf"
if font.exists():
    datas.append((str(font), "."))

a = Analysis(
    [str(root / "VidMine.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=collect_submodules("faster_whisper") + ["ctranslate2"],
    excludes=["tkinter", "pytest", "torch", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VidMine",
    console=False,
    icon=str(root / "packaging" / "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="VidMine")
