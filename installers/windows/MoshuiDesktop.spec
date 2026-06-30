# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Windows tray EXE (onefile, windowed).
# Using a spec instead of command-line --add-data avoids all PowerShell quoting
# pain (the ';' path separator + PS 5.1 native-arg handling broke --add-data).
# Run: pyinstaller --noconfirm --clean installers\windows\MoshuiDesktop.spec
import os
from PyInstaller.utils.hooks import collect_all

# SPECPATH is injected by PyInstaller = absolute dir of this spec file.
REPO = os.path.dirname(os.path.dirname(SPECPATH))


def P(*parts):
    return os.path.join(REPO, *parts)


# Data files bundled into the onefile _MEIPASS, mirroring the repo layout so
# app.py's REPO_ROOT (= _MEIPASS at runtime) finds web/styles/installers.
# (No fonts/ dir in this repo — Chromium renders with the OS system fonts.)
# Only include paths that actually exist, so a missing optional dir can't abort the build.
_data_pairs = [
    (P('web'), 'web'),
    (P('styles'), 'styles'),
    (P('installers'), 'installers'),
    (P('server', 'sources', 'collectors'), 'server/sources/collectors'),
    (P('APP_VERSION'), '.'),          # version file, written by build-win-app.ps1
]
datas = [(src, dst) for (src, dst) in _data_pairs if os.path.exists(src)]
binaries = []
hiddenimports = ['server.run', 'server.tray_win']

# uvicorn/zeroconf load submodules dynamically -> collect everything.
for pkg in ('uvicorn', 'zeroconf'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [P('server', 'win_entry.py')],
    pathex=[REPO],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['rumps', 'server.menubar'],   # Mac-only; never on the Windows import path
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MoshuiDesktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,                          # windowed (no console)
    disable_windowed_traceback=False,
    icon=P('installers', 'windows', 'app.ico'),
)
