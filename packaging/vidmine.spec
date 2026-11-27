# PyInstaller spec for the VidMine Windows app. Build: pyinstaller --noconfirm packaging/vidmine.spec
from pathlib import Path

root = Path(SPECPATH).parent
deps = root / "deps"

binaries = [(str(deps / "libmpv-2.dll"), "."), (str(deps / "ffmpeg.exe"), ".")]
datas = [(str(root / "KAERU_VIDEO_IMPORT_SPEC.md"), ".")]
font = deps / "NotoSansJP-Bold.otf"
if font.exists():
    datas.append((str(font), "."))

a = Analysis(
    [str(root / "VidMine.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    excludes=["tkinter", "faster_whisper", "ctranslate2", "numpy", "pytest"],
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
