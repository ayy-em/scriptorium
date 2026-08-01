# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the Scriptorium Windows installer payload.

Build from the repo root:
    pyinstaller packaging/scriptorium-win.spec --noconfirm --clean
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(os.path.abspath(os.path.join(SPECPATH, "..")))

# WeasyPrint pulls in many sub-modules + a UA stylesheet data file. Windows
# users still need the GTK runtime installed for pango/cairo to be available;
# collect_all grabs the python side here.
wp_datas, wp_binaries, wp_hidden = collect_all("weasyprint")


def _collect(package):
    """collect_all for an optional dependency, tolerating its absence."""
    try:
        return collect_all(package)
    except Exception:  # pragma: no cover - build-time only
        print(f"WARNING: could not collect {package!r}; scripts needing it will be missing")
        return [], [], []


def _metadata(package):
    """Copy a package's dist-info, and that of everything it requires.

    Some libraries resolve their own version through importlib.metadata at
    import time and do not guard the lookup — pymatting is one, so a bundle
    without its dist-info raises PackageNotFoundError and takes photo.remove_bg
    down with it. Recursive covers the rest of the graph rather than waiting for
    the next transitive dependency to do the same thing.
    """
    try:
        return copy_metadata(package, recursive=True)
    except Exception:  # pragma: no cover - build-time only
        print(f"WARNING: could not copy metadata for {package!r}")
        return []


# rembg drives photo.remove_bg and onnxruntime is its inference backend. Neither
# is reachable by static analysis, and core.registry silently skips any script
# whose imports fail — so without these, remove_bg vanishes from the built app
# with no error at all.
rembg_datas, rembg_binaries, rembg_hidden = _collect("rembg")
ort_datas, ort_binaries, ort_hidden = _collect("onnxruntime")

# pywebview reaches the native window through pythonnet/clr, which loads a
# managed runtime at import time. Missing pieces here make pywebview raise
# "Failed to initialize Python.Runtime.dll", silently downgrading the app to
# the Chromium fallback tier — which has no system tray.
clr_datas, clr_binaries, clr_hidden = _collect("clr_loader")
pn_datas, pn_binaries, pn_hidden = _collect("pythonnet")

# Every script module, discovered rather than listed. core.registry finds
# scripts by walking the package at runtime, so a hand-maintained list here
# drifts the moment a script is added — which is how photo.remove_bg and three
# telegram scripts ended up missing from the v0.5.2 build.
hidden_imports = collect_submodules("scripts") + collect_submodules("core") + [
    # Third-party libraries that might be lazily imported
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.config",
    "uvicorn.server",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "jinja2",
    "multipart",
    "yaml",
    "httpx",
    "yt_dlp",
    "PIL",
    "pandas",
    "openpyxl",
    "requests",
    "ffmpeg",
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "pystray",
    "pystray._win32",
    "matplotlib",
    "matplotlib.backends.backend_agg",
    "weasyprint",
    "cffi",
    "_cffi_backend",
    "wordcloud",
    "emoji",
    "ijson",
    "ijson.backends",
    "ijson.backends.python",
    # Reached only through numpy's lazy __getattr__, so static analysis misses it.
    "numpy.testing",
]
hidden_imports += wp_hidden + rembg_hidden + ort_hidden + clr_hidden + pn_hidden

datas = [
    (str(ROOT / "webapp" / "templates"), "webapp/templates"),
    (str(ROOT / "webapp" / "static"), "webapp/static"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "scripts" / "telegram" / "templates"), "scripts/telegram/templates"),
    (str(ROOT / "pyproject.toml"), "."),
]
datas += wp_datas + rembg_datas + ort_datas + clr_datas + pn_datas
datas += _metadata("rembg")
binaries = wp_binaries + rembg_binaries + ort_binaries + clr_binaries + pn_binaries

a = Analysis(
    [str(ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 'unittest' must stay collected. scipy imports array_api_compat, which does
    # `from numpy import *`; 'testing' is in numpy's __all__, so that triggers
    # numpy/testing/__init__.py -> `from unittest import TestCase`. Excluding it
    # broke photo.remove_bg (rembg -> pymatting -> scipy) at run time only.
    excludes=["tkinter", "test"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScriptoriumApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "logo.ico"),
)

exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scriptorium",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ROOT / "packaging" / "logo.ico"),
)

coll = COLLECT(
    exe_gui,
    exe_cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="scriptorium",
)
