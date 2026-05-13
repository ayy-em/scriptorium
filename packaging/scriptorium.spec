# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the Scriptorium macOS .app bundle.

Build from the repo root:
    cd /path/to/scriptorium
    pyinstaller packaging/scriptorium.spec
"""

import os
from pathlib import Path

ROOT = Path(os.path.abspath(os.path.join(SPECPATH, "..")))

# Collect every script sub-package so the registry can discover them at runtime.
hidden_imports = [
    "core",
    "core.paths",
    "core.registry",
    "core.runner",
    "scripts",
    "scripts.api",
    "scripts.av",
    "scripts.av._utils",
    "scripts.av.convert",
    "scripts.av.dump_frames",
    "scripts.av.filmstrip",
    "scripts.av.join",
    "scripts.av.split",
    "scripts.av.tag",
    "scripts.av.to_anim",
    "scripts.av.trim",
    "scripts.av.volume",
    "scripts.downloads",
    "scripts.downloads.download",
    "scripts.formats",
    "scripts.homeassistant",
    "scripts.llm",
    "scripts.lora",
    "scripts.lora._dataset",
    "scripts.lora.export_captions",
    "scripts.lora.import_captions",
    "scripts.lora.renumber",
    "scripts.lora.validate",
    "scripts.photo",
    "scripts.printing",
    "scripts.speech",
    "scripts.tabular",
    "scripts.web",
    # Third-party libraries that might be lazily imported
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
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
    "ffmpeg",
]

# Data files that must be included in the bundle.
datas = [
    (str(ROOT / "webapp" / "templates"), "webapp/templates"),
    (str(ROOT / "webapp" / "static"), "webapp/static"),
    (str(ROOT / "pyproject.toml"), "."),
]

a = Analysis(
    [str(ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=[],
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
    target_arch="universal2",
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
        "CFBundleShortVersionString": "0.2.0",
        "NSHighResolutionCapable": True,
        "LSBackgroundOnly": False,
    },
)
