# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the Scriptorium macOS .app bundle.

Build from the repo root:
    cd /path/to/scriptorium
    pyinstaller packaging/scriptorium.spec
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(os.path.abspath(os.path.join(SPECPATH, "..")))

# WeasyPrint imports many sub-modules lazily and ships data files (CSS UA stylesheet etc.).
# collect_all pulls in modules + datas + binaries in one shot. Native libs (pango/cairo/glib)
# are NOT bundled here — _runtime.py's cffi.dlopen monkey-patch resolves them at runtime
# under /opt/homebrew/lib (the .app target requires Homebrew pango on the host machine for
# now; full native-lib bundling for a non-brew machine is a separate task).
wp_datas, wp_binaries, wp_hidden = collect_all("weasyprint")

def _collect(package):
    """collect_all for an optional dependency, tolerating its absence."""
    try:
        return collect_all(package)
    except Exception:  # pragma: no cover - build-time only
        print(f"WARNING: could not collect {package!r}; scripts needing it will be missing")
        return [], [], []


# rembg drives photo.remove_bg and onnxruntime is its inference backend. Neither
# is reachable by static analysis, and core.registry silently skips any script
# whose imports fail — so without these, remove_bg vanishes with no error.
rembg_datas, rembg_binaries, rembg_hidden = _collect("rembg")
ort_datas, ort_binaries, ort_hidden = _collect("onnxruntime")


# Every script module, discovered rather than listed. core.registry finds
# scripts by walking the package at runtime, so a hand-maintained list here
# drifts the moment a script is added — which is how seven scripts ended up
# missing from the v0.5.2 builds.
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
    "webview.platforms.cocoa",
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
]
hidden_imports += wp_hidden + rembg_hidden + ort_hidden

# Data files that must be included in the bundle.
datas = [
    (str(ROOT / "webapp" / "templates"), "webapp/templates"),
    (str(ROOT / "webapp" / "static"), "webapp/static"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "scripts" / "telegram" / "templates"), "scripts/telegram/templates"),
    (str(ROOT / "pyproject.toml"), "."),
]
datas += wp_datas + rembg_datas + ort_datas

a = Analysis(
    [str(ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=wp_binaries + rembg_binaries + ort_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scriptorium",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="scriptorium",
)

app = BUNDLE(
    coll,
    name="Scriptorium.app",
    icon=str(ROOT / "packaging" / "logo.icns"),
    bundle_identifier="com.somethingreally.scriptorium",
    info_plist={
        "CFBundleDisplayName": "Scriptorium",
        "CFBundleShortVersionString": "0.5.2",
        "NSHighResolutionCapable": True,
        "LSBackgroundOnly": False,
    },
)
