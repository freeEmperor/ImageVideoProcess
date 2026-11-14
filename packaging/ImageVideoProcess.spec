# Canonical build configuration. Invoked by scripts/build-exe.ps1.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
onedir = os.environ.get("IVP_BUILD_DIR") == "1"
console = os.environ.get("IVP_BUILD_CONSOLE") == "1"
a = Analysis(
    [str(root / "src/imagevideoprocess/__main__.py")],
    pathex=[str(root / "src")],
    datas=collect_data_files("imageio_ffmpeg") + [(str(root / "src/imagevideoprocess/resources/app.ico"), "imagevideoprocess/resources")],
    excludes=["PySide6.QtDataVisualization", "PySide6.QtCharts", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "tkinter", "pytest", "matplotlib", "IPython"],
)
# PyAV adds av.libs to the DLL search path itself; keep its canonical copies.
# Remove a root copy only when its bytes match a retained av.libs copy.
import hashlib
canonical = {Path(name).name.lower(): source for name, source, kind in a.binaries if name.replace("\\", "/").startswith("av.libs/")}
def redundant(entry):
    name, source, kind = entry
    if "/" in name or "\\" in name or name.lower() not in canonical:
        return False
    return hashlib.sha256(Path(source).read_bytes()).digest() == hashlib.sha256(Path(canonical[name.lower()]).read_bytes()).digest()
a.binaries = [entry for entry in a.binaries if not redundant(entry)]
pyz = PYZ(a.pure)
common = dict(name="ImageVideoProcess", console=console, icon=str(root / "src/imagevideoprocess/resources/app.ico"), upx=False)
if onedir:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, name="ImageVideoProcess", upx=False)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)
