# Build on 64-bit Windows with the environment in requirements-build.txt.
from pathlib import Path
import runpy
import sqlite3
import sys
from contextlib import closing

from PyInstaller.utils.hooks import collect_submodules, copy_metadata
from PyInstaller.config import CONF
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct,
)

root = Path(SPECPATH)
sys.path.insert(0, str(root))
release = runpy.run_path(str(root / "fmeda_tool" / "version.py"))
version = release["APP_VERSION"]
app_name = release["APP_NAME"]
version_tuple = tuple(int(part) for part in version.split(".")) + (0,)

# SQLite backup includes committed WAL data and leaves the operational database
# untouched. Only this consistent release snapshot is installed for first use.
staging = Path(CONF["workpath"]) / "runtime-library"
staging.mkdir(parents=True, exist_ok=True)
snapshot = staging / "fmeda.sqlite"
operational = root / "data" / "fmeda.sqlite"
if operational.exists():
    with closing(sqlite3.connect(operational.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(snapshot)) as destination:
            source.backup(destination)
else:
    from fmeda_tool.db.database import DatabaseService
    ready, message = DatabaseService.initialize_from_seed(db_path=snapshot, force_rebuild=True)
    if not ready:
        raise RuntimeError(message)
with closing(sqlite3.connect(snapshot)) as connection:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Release SQLite snapshot failed integrity_check")

datas = [
    (str(snapshot), "data"),
    (str(root / "data" / "components_db.json"), "data"),
    (str(root / "data" / "seed" / "Combined_Exida_Component_library_version2.json"), "data/seed"),
    (str(root / "fmeda_tool" / "db" / "schema.sql"), "fmeda_tool/db"),
    # Formula Reference's inspect.getsource links need the actual source file.
    (str(root / "fmeda_tool" / "services" / "calculation_service.py"), "fmeda_tool/services"),
]
for directory in ("assets", "icons", "images", "templates", "config"):
    if (root / directory).is_dir():
        datas.append((str(root / directory), directory))
for package in ("pydantic", "openpyxl"):
    datas += copy_metadata(package)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple,
                      mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("FileDescription", release["APP_DISPLAY_NAME"]),
            StringStruct("FileVersion", version),
            StringStruct("ProductName", app_name),
            StringStruct("ProductVersion", version),
            StringStruct("OriginalFilename", app_name + ".exe"),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    [str(root / "main.py")], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=collect_submodules("fmeda_tool") + collect_submodules("openpyxl") + [
        "PyQt6.QtPrintSupport", "sqlite3", "_sqlite3", "pydantic_core._pydantic_core",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["PyQt5", "PySide2", "PySide6", "pytest", "pytestqt", "tkinter"],
    noarchive=False,
)
# PyInstaller's Qt hooks collect qwindows, imageformats, print support and the Qt
# DLLs corresponding to the imported PyQt6 modules. Do not use collect_all(PyQt6).
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=app_name,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / "assets" / "FMEDA.ico"), version=version_info,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=app_name)
