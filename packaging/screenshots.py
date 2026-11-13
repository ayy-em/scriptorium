"""Capture the README screenshots and assemble them into animated WebP carousels.

Usage:
    uv run --with playwright packaging/screenshots.py
    uv run --with playwright packaging/screenshots.py --keep-frames shots/

Writes ``docs/screenshots/showcase-light.webp`` and ``showcase-dark.webp``, which
README.md shows through a ``<picture>`` element so GitHub serves each viewer the
one matching their theme.

How it stays honest and repeatable:

- The web UI runs in a subprocess with a throwaway home directory, so the
  shots never contain the operator's own history, favourites or settings. A
  few illustrative history rows and favourites are seeded there instead.
- Sample media is generated with ffmpeg's test sources, so nothing personal is
  uploaded and every run captures the same content.
- Playwright drives the Chrome already installed on the machine
  (``channel="chrome"``), so there is no browser download and Playwright is not
  a project dependency — ``--with`` brings it in for this one run.
- Anything the capture stages in the repo's ``inputs/`` and ``outputs/`` folders
  is removed afterwards; files that were there before are left alone.

Needs ffmpeg on ``PATH`` and Chrome installed.
"""

import argparse
import base64
from collections.abc import Callable, Iterator
import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "docs" / "screenshots"

VIEWPORT = {"width": 1280, "height": 800}
# The composed slide: screenshot in a window frame on a tinted backdrop, with
# a caption above it. The animated file is resized to this width.
SLIDE_WIDTH = 1200

HOLD_MS = 3200
TRANSITION_FRAMES = 6
TRANSITION_MS = 45

# Backdrop and caption colours per theme, taken from the app's own palette so
# the carousel reads as part of the product rather than a marketing overlay.
FRAME_STYLE = {
    "light": {"bg": "#f3f1fa", "ink": "#1f1d2b", "muted": "#6b6880", "accent": "#7c5cdb", "shadow": "0.16"},
    "dark": {"bg": "#14131b", "ink": "#ecebf3", "muted": "#9c99ad", "accent": "#a48cf0", "shadow": "0.55"},
}


@dataclass(frozen=True)
class Slide:
    """One screen in the carousel.

    Attributes:
        name: File stem for the kept frame.
        title: Caption headline.
        body: Caption sub-line.
        capture: Puts the page in the state to photograph.
    """

    name: str
    title: str
    body: str
    capture: Callable


# ─── Fixtures ──────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_media(workdir: Path) -> dict[str, Path]:
    """Generate a short test video and a tone, so no personal media is used."""
    video = workdir / "holiday-clip.mp4"
    tone = workdir / "voice-memo.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=24",
            "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100:duration=24",
            "-filter_complex", "[1:a]volume='0.25+0.75*abs(sin(t*0.9))*abs(sin(t*3.1))':eval=frame[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "60", "-c:a", "aac", "-shortest",
            str(video),
        ],
        check=True,
    )  # fmt: skip
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100:duration=12",
            str(tone),
        ],
        check=True,
    )  # fmt: skip
    return {"video": video, "tone": tone}


def _seed_home(home: Path, theme: str) -> None:
    """Write illustrative history, favourites and the theme into the throwaway home."""
    data = home / "scriptorium"
    data.mkdir(parents=True, exist_ok=True)
    (data / "config.json").write_text(
        json.dumps({"theme": theme, "favourites": ["av.trim", "photo.remove_bg", "downloads.download"]}),
        encoding="utf-8",
    )
    now = datetime.now().replace(microsecond=0)
    rows = [
        ("av.trim", "success", 4.2, ["holiday-clip.mp4", "00:03", "00:18"], 2),
        ("photo.remove_bg", "success", 11.8, ["portrait.heic", "--preset", "balanced"], 9),
        ("downloads.download", "success", 37.5, ["https://example.com/talk"], 31),
        ("formats.convert_image", "success", 1.4, ["IMG_2041.HEIC", "--format", "jpeg"], 55),
        ("av.join", "cancelled", 22.0, ["clips/"], 80),
        ("formats.convert_docs", "error", 0.9, ["notes.md", "--to", "pdf"], 140),
        ("av.filmstrip", "success", 6.3, ["holiday-clip.mp4", "--grid", "3x4"], 210),
        ("telegram.chat_analysis", "success", 48.1, ["ChatExport_2026-10-02"], 1500),
    ]
    history = [
        {
            "run_id": f"demo{i}",
            "key": key,
            "status": status,
            "started_at": (now - timedelta(minutes=ago)).isoformat(),
            "elapsed": elapsed,
            "exit_code": {"success": 0, "error": 1}.get(status),
            "argv": argv,
            "params": {},
            "outputs": [],
            "batch_id": "",
        }
        for i, (key, status, elapsed, argv, ago) in enumerate(rows)
    ]
    (data / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")


@contextlib.contextmanager
def _server(home: Path) -> Iterator[str]:
    """Run the web UI against ``home`` and yield its base URL."""
    port = _free_port()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-c", "from webapp.app import run; run()", "--port", str(port)],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/", timeout=1)  # noqa: S310 — localhost only
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("web UI did not start")
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@contextlib.contextmanager
def _tidy(*dirs: Path) -> Iterator[None]:
    """Remove whatever appears under ``dirs`` while the block runs."""
    before = {d: set(d.rglob("*")) if d.exists() else set() for d in dirs}
    try:
        yield
    finally:
        for d, existed in before.items():
            if not d.exists():
                continue
            # Deepest first, so directories are empty by the time they are reached.
            for path in sorted(set(d.rglob("*")) - existed, key=lambda p: len(p.parts), reverse=True):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)


# ─── Page states ───────────────────────────────────────────────────────────


def _settle(page) -> None:
    """Wait for the splash to leave and transitions to finish."""
    page.wait_for_selector("#splash", state="hidden", timeout=15000)
    page.wait_for_timeout(500)


def _goto(page, url: str) -> None:
    page.goto(url)
    _settle(page)


def _home(page, base: str, media: dict) -> None:  # noqa: ARG001
    _goto(page, base + "/")


def _form(page, base: str, media: dict) -> None:
    _goto(page, base + "/scripts/av/filmstrip")
    page.locator("form input[type=file]").first.set_input_files(str(media["video"]))
    page.wait_for_timeout(1200)
    grid = page.locator("input[name=grid]")
    if grid.count():
        grid.fill("3x4")
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Copy CLI command").click()
    page.wait_for_selector("#command-preview", state="visible")
    page.locator("#command-preview").scroll_into_view_if_needed()
    page.wait_for_timeout(2400)  # let the "Copied" tick revert


def _run(page, base: str, media: dict) -> None:
    _form(page, base, media)
    page.locator("#run-btn").click()
    page.wait_for_selector(".status-strip--success", timeout=120000)
    page.wait_for_timeout(800)
    page.locator(".status-strip").scroll_into_view_if_needed()
    page.wait_for_timeout(400)


def _drop(page, base: str, media: dict) -> None:
    _goto(page, base + "/")
    payload = base64.b64encode(media["video"].read_bytes()).decode()
    page.evaluate(
        """([name, b64]) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const dt = new DataTransfer();
            dt.items.add(new File([bytes], name, { type: 'video/mp4' }));
            const target = document.querySelector('[x-data^="scriptBrowser"]');
            target.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
        }""",
        [media["video"].name, payload],
    )
    page.wait_for_timeout(2500)


def _trim(page, base: str, media: dict) -> None:
    _goto(page, base + "/scripts/av/trim")
    page.locator("#run-form input[type=file]").first.set_input_files(str(media["video"]))
    page.wait_for_timeout(3500)
    start = page.locator("#run-form input[x-model='startInput']")
    end = page.locator("#run-form input[x-model='endInput']")
    if start.count() and end.count():
        start.fill("00:04")
        start.dispatch_event("change")
        end.fill("00:17")
        end.dispatch_event("change")
    page.wait_for_timeout(800)


def _settings(page, base: str, media: dict) -> None:  # noqa: ARG001
    _goto(page, base + "/")
    page.get_by_label("Open settings").click()
    page.wait_for_selector(".modal-dialog--settings", state="visible")
    page.wait_for_timeout(900)


def _history(page, base: str, media: dict) -> None:  # noqa: ARG001
    _goto(page, base + "/history")


SLIDES = [
    Slide("home", "Every tool, one tidy shelf", "27 scripts across video, images, documents, data and more.", _home),
    Slide(
        "drop",
        "Drop a file, get every tool that fits",
        "Scriptorium works out what can handle it and offers just those.",
        _drop,
    ),
    Slide("form", "Forms instead of flags", "Every option explained, with the exact CLI command shown live.", _form),
    Slide("run", "Watch it work", "Live output, real progress and one-click access to the results.", _run),
    Slide("trim", "Trim by eye", "Pick the cut on the waveform, then hear it before you commit.", _trim),
    Slide(
        "history", "Never retype a command", "Every run is logged, and Re-run brings back the exact settings.", _history
    ),
    Slide(
        "settings", "Yours, and only yours", "Runs offline on your machine. Keys stay local. Light or dark.", _settings
    ),
]


# ─── Composition ───────────────────────────────────────────────────────────


def _compose(page, shot: bytes, slide: Slide, theme: str, base: str) -> Image.Image:
    """Frame a raw screenshot with its caption and return the composed slide."""
    s = FRAME_STYLE[theme]
    img = base64.b64encode(shot).decode()
    page.set_content(
        f"""<!doctype html><html><head><style>
        @font-face {{ font-family: Inter; font-weight: 100 900;
                      src: url({base}/static/fonts/inter-latin-wght-normal.woff2); }}
        html, body {{ margin: 0; background: {s["bg"]}; font-family: Inter, sans-serif; }}
        .slide {{ width: 1360px; padding: 44px 40px 48px; box-sizing: border-box; }}
        .cap {{ text-align: center; margin-bottom: 30px; }}
        .t {{ font-size: 40px; font-weight: 700; letter-spacing: -0.02em; color: {s["ink"]}; }}
        .t::before {{ content: ""; display: inline-block; width: 12px; height: 12px; border-radius: 50%;
                      background: {s["accent"]}; margin-right: 16px; vertical-align: middle; }}
        .b {{ font-size: 22px; color: {s["muted"]}; margin-top: 10px; }}
        .win {{ border-radius: 14px; overflow: hidden; width: 1280px;
                box-shadow: 0 24px 60px rgba(0,0,0,{s["shadow"]}), 0 0 0 1px rgba(127,127,127,.18); }}
        .win img {{ display: block; width: 1280px; }}
        </style></head><body><div class="slide">
        <div class="cap"><div class="t">{slide.title}</div><div class="b">{slide.body}</div></div>
        <div class="win"><img src="data:image/png;base64,{img}"></div>
        </div></body></html>"""
    )
    page.wait_for_timeout(300)
    png = page.locator(".slide").screenshot()
    frame = Image.open(io.BytesIO(png)).convert("RGB")
    height = round(frame.height * SLIDE_WIDTH / frame.width)
    return frame.resize((SLIDE_WIDTH, height), Image.Resampling.LANCZOS)


def _carousel(frames: list[Image.Image], target: Path) -> None:
    """Write a looping animated WebP that slides from each frame to the next."""
    out: list[Image.Image] = []
    durations: list[int] = []
    w, h = frames[0].size
    for i, frame in enumerate(frames):
        out.append(frame)
        durations.append(HOLD_MS)
        nxt = frames[(i + 1) % len(frames)]
        for step in range(1, TRANSITION_FRAMES + 1):
            # Ease-in-out, so the slide starts and lands gently.
            t = step / (TRANSITION_FRAMES + 1)
            eased = t * t * (3 - 2 * t)
            offset = round(w * eased)
            tween = Image.new("RGB", (w, h))
            tween.paste(frame, (-offset, 0))
            tween.paste(nxt, (w - offset, 0))
            out.append(tween)
            durations.append(TRANSITION_MS)
    target.parent.mkdir(parents=True, exist_ok=True)
    out[0].save(
        target,
        save_all=True,
        append_images=out[1:],
        duration=durations,
        loop=0,
        quality=72,
        method=6,
        minimize_size=True,
    )


def main() -> None:
    """Capture every slide in both themes and write the two carousels."""
    from playwright.sync_api import sync_playwright  # noqa: PLC0415 — only present under `--with playwright`

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="directory for the carousel files")
    parser.add_argument("--keep-frames", type=Path, help="also save each raw and composed frame here")
    parser.add_argument(
        "--only",
        nargs="+",
        choices=[s.name for s in SLIDES],
        help="capture just these slides (for checking frames; the carousel then holds only them)",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required on PATH")

    with tempfile.TemporaryDirectory(prefix="scriptorium-shots-") as tmpdir:
        tmp = Path(tmpdir)
        home = tmp / "home"
        _seed_home(home, "light")
        media = _make_media(tmp)

        with _tidy(REPO / "inputs", REPO / "outputs"), _server(home) as base, sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            for theme in ("light", "dark"):
                # Reset per theme: the server keeps the theme too, and the light
                # pass's own run would otherwise pile up in the dark pass's history.
                _seed_home(home, theme)
                ctx = browser.new_context(
                    viewport=VIEWPORT,
                    device_scale_factor=1,
                    color_scheme=theme,
                    permissions=["clipboard-read", "clipboard-write"],
                )
                ctx.add_init_script(
                    f"localStorage.setItem('theme', '{theme}'); localStorage.setItem('onboarding_seen', '1');"
                )
                # A release newer than this checkout would otherwise put an update banner in every shot.
                ctx.route(
                    "**/api/update-check",
                    lambda route: route.fulfill(json={"update_available": False}),
                )
                page = ctx.new_page()
                composer = ctx.new_page()
                frames = []
                for slide in [s for s in SLIDES if not args.only or s.name in args.only]:
                    slide.capture(page, base, media)
                    shot = page.screenshot()
                    frame = _compose(composer, shot, slide, theme, base)
                    frames.append(frame)
                    if args.keep_frames:
                        args.keep_frames.mkdir(parents=True, exist_ok=True)
                        (args.keep_frames / f"{theme}-{slide.name}-raw.png").write_bytes(shot)
                        frame.save(args.keep_frames / f"{theme}-{slide.name}.png")
                    print(f"  {theme:5} {slide.name}")
                target = args.out / f"showcase-{theme}.webp"
                _carousel(frames, target)
                print(f"wrote {target} ({target.stat().st_size / 1e6:.1f} MB)")
                ctx.close()
            browser.close()


if __name__ == "__main__":
    main()
