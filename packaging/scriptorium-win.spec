# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the Scriptorium Windows installer payload.

Build from the repo root:
    pyinstaller packaging/scriptorium-win.spec --noconfirm --clean
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(os.path.abspath(os.path.join(SPECPATH, "..")))

# WeasyPrint pulls in many sub-modules + a UA stylesheet data file. Windows
# users still need the GTK runtime installed for pango/cairo to be available;
# collect_all grabs the python side here.
wp_datas, wp_binaries, wp_hidden = collect_all("weasyprint")

hidden_imports = [
    "core",
    "core.paths",
    "core.registry",
    "core.runner",
    "scripts",
    "scripts.api",
    "scripts.av",
    "scripts.av._utils",
    "scripts.av.dump_frames",
    "scripts.av.filmstrip",
    "scripts.av.join",
    "scripts.av.split",
    "scripts.av.tag",
    "scripts.av.to_anim",
    "scripts.av.trim",
    "scripts.av.video_crop",
    "scripts.av.volume",
    "scripts.downloads",
    "scripts.downloads.download",
    "scripts.formats",
    "scripts.formats._utils",
    "scripts.formats.convert_audio",
    "scripts.formats.convert_image",
    "scripts.formats.convert_tabular",
    "scripts.formats.convert_video",
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
    "scripts.sitemaps",
    "scripts.sitemaps.status_check",
    "scripts.speech",
    "scripts.tabular",
    "scripts.telegram",
    "scripts.telegram._charts",
    "scripts.telegram._metrics",
    "scripts.telegram._parsing",
    "scripts.telegram._pdf",
    "scripts.telegram._runtime",
    "scripts.telegram._stopwords_en",
    "scripts.telegram._stopwords_ru",
    "scripts.telegram.chat_analysis",
    "scripts.web",
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
hidden_imports += wp_hidden

datas = [
    (str(ROOT / "webapp" / "templates"), "webapp/templates"),
    (str(ROOT / "webapp" / "static"), "webapp/static"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "scripts" / "telegram" / "templates"), "scripts/telegram/templates"),
    (str(ROOT / "pyproject.toml"), "."),
]
datas += wp_datas

a = Analysis(
    [str(ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=wp_binaries,
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
    icon=str(ROOT / "packaging" / "logo.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="scriptorium",
)
