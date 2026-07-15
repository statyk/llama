# PyInstaller spec for llama. Cross-platform: same file on macOS, Linux, Windows.
#
# Build:   LLAMA_VERSION=<ver> pyinstaller packaging/llama.spec --clean --noconfirm
# Output:  dist/llama         (single self-contained executable)
#          dist/llama.exe     (on Windows)
#
# ruff: noqa
# (loaded as Python by PyInstaller; lint is not useful here)

import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = Path(SPECPATH).parent  # type: ignore[name-defined]  # SPECPATH injected by PyInstaller

# Version is injected via LLAMA_VERSION (set by packaging/build.py from the git
# tag). Defaults to 0.0.0 for a plain spec run. Affects only the Windows
# file-version resource; the binary's own --version comes from _version.py.
LLAMA_VERSION = os.environ.get("LLAMA_VERSION", "0.0.0")


def _version_tuple(v):
    m = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?", v or "")
    parts = [int(g) if g else 0 for g in (m.groups() if m else ())]
    parts += [0] * (4 - len(parts))
    return tuple(parts[:4])


# Windows file-version resource (Windows only). Failures must not break the
# build — fall back to no resource with a warning.
_win_version_file = None
if sys.platform == "win32":
    try:
        from PyInstaller.utils.win32.versioninfo import (
            FixedFileInfo,
            StringFileInfo,
            StringStruct,
            StringTable,
            VarFileInfo,
            VarStruct,
            VSVersionInfo,
        )

        _vt = _version_tuple(LLAMA_VERSION)
        _vsinfo = VSVersionInfo(
            ffi=FixedFileInfo(filevers=_vt, prodvers=_vt, mask=0x3F, flags=0x0,
                              OS=0x40004, fileType=0x1, subtype=0x0),
            kids=[
                StringFileInfo([StringTable("040904B0", [
                    StringStruct("CompanyName", "llama"),
                    StringStruct("FileDescription", "llama-radio"),
                    StringStruct("FileVersion", LLAMA_VERSION),
                    StringStruct("ProductName", "llama"),
                    StringStruct("ProductVersion", LLAMA_VERSION),
                    StringStruct("OriginalFilename", "llama.exe"),
                ])]),
                VarFileInfo([VarStruct("Translation", [1033, 1200])]),
            ],
        )
        _vfile = PROJECT_ROOT / "build" / "llama_version_info.txt"
        _vfile.parent.mkdir(parents=True, exist_ok=True)
        _vfile.write_text(str(_vsinfo), encoding="utf-8")
        _win_version_file = str(_vfile)
    except Exception as exc:  # noqa: BLE001
        print(f"[llama.spec] WARNING: could not build Windows version resource: {exc}")

# The one mandatory bundling step: prompt templates are loaded at runtime via
# importlib.resources.files("llama.prompts").
datas = collect_data_files("llama.prompts")

a = Analysis(  # type: ignore[name-defined]
    [str(PROJECT_ROOT / "src" / "llama" / "__main__.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)  # type: ignore[name-defined]

exe = EXE(  # type: ignore[name-defined]
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="llama",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_win_version_file,  # Windows resource (None elsewhere)
)
