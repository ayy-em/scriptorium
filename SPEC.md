# Scriptorium — Technical Spec

## What this is

A single-entrypoint collection of themed utility scripts. All execution — CLI or
programmatic — goes through `core/runner.py`, which provides a uniform middleware
layer (timing, a per-run record in `logs/runs.jsonl`, an optional Telegram
notification). Scripts themselves stay lean: no cross-cutting logic, no
`sys.exit` outside of `run()`.

---

## Repository layout

```
scriptorium/
├── build.sh                 # unified build entrypoint (detects OS, delegates)
├── build.bat                # Windows entrypoint → packaging/build_installer.bat
├── main.py                  # CLI entrypoint
├── assets/                  # shared images and fonts used across themes
├── inputs/                  # drop files here (shared across every theme)
│   └── processed/           # files auto-archived here after successful runs
├── outputs/                 # per-theme outputs land here as <theme>/<file>
├── logs/                    # runs.jsonl from the runner middleware; what /api/open-logs reveals
├── core/
│   ├── argparse.py          # ScriptoriumParser with ui_label support
│   ├── capabilities.py      # external dependencies: one probe, one value type
│   ├── categories.py        # extension → category (video, audio, image, …) for drop matching
│   ├── config.py            # user settings persistence (UserConfig, load, save)
│   ├── history.py           # run history persistence (RunRecord, load, append)
│   ├── downloads.py         # pooch progress → ProgressReporter, for model weights
│   ├── env.py               # .env loading, plus the user .env the app writes keys to
│   ├── images.py            # registers the HEIF opener so Pillow reads .heic
│   ├── invocation.py        # who started this run — webapp or a human
│   ├── native_libs.py       # cffi dlopen fallback for pango/cairo/glib
│   ├── outputs.py           # standardized output path resolution
│   ├── paths.py             # centralized path resolution (frozen vs dev)
│   ├── progress.py          # the ::progress:: reporting contract
│   ├── registry.py          # auto-discovers scripts and themes
│   └── runner.py            # dispatch + middleware (run, run_fn)
├── scripts/
│   └── <theme>/
│       ├── __init__.py      # LABEL, DESCRIPTION
│       ├── _helpers.py      # private shared code (ignored by registry)
│       └── <script>.py      # one script per file
├── webapp/
│   ├── app.py               # FastAPI server
│   ├── _badges.py           # ACCEPTS-derived compatibility badges
│   ├── _form.py             # argparse introspection for auto-generated forms
│   ├── _icons.py            # glyph-name lookup for scripts and file categories
│   ├── _runs.py             # live run registry + process-tree termination
│   ├── _waveform.py         # ffmpeg-decoded peak envelope + staged-input containment
│   ├── static/
│   │   ├── style.css        # the entire stylesheet, sectioned (see below)
│   │   ├── fonts/           # self-hosted Inter + JetBrains Mono (OFL 1.1)
│   │   ├── js/              # vendored Alpine.js + focus plugin
│   │   ├── logo.svg         # splash, top bar, favicon
│   │   ├── logo-{64,128,256,512}.png  # logo-64.png is the tray icon
│   │   └── logo.{png,webp}, favicon.ico  # raster fallbacks, README, browser tab
│   └── templates/           # Jinja2 (see "Web UI layer" below)
└── packaging/
    ├── entrypoint.py            # frozen app entry (web server + --run-script mode)
    ├── scriptorium.spec         # PyInstaller spec for macOS .app bundle
    ├── scriptorium-win.spec     # PyInstaller spec for Windows folder bundle
    ├── scriptorium-linux.spec   # PyInstaller spec for Linux binary
    ├── build.sh                 # macOS build script
    ├── build_installer.bat      # Windows build script (PyInstaller + Inno Setup)
    ├── build_linux.sh           # Linux build script
    ├── installer.iss            # Inno Setup script for Windows installer
    └── logo.icns, logo.ico      # app icons for the macOS bundle and Windows installer
```

Local data lives at the repo root: a single `inputs/` directory shared across
every theme, an `outputs/` directory with one subdirectory per theme
(`outputs/<theme>/`), and `inputs/processed/` where files are auto-archived
after a successful run. The `inputs/` and `outputs/` folders themselves are
tracked via `.gitkeep`; their contents are gitignored.

---

## Invocation

### CLI

```sh
uv run main.py                          # list all scripts across all themes
uv run main.py <theme>                  # list scripts in one theme with descriptions
uv run main.py <theme>.<script> [args]  # run a script
uv run main.py <theme>.<script> --help  # show usage, arguments, and examples
```

`uv run` is the only supported CLI invocation — use it on all platforms.

#### Theme listing output format

`uv run main.py <theme>` prints the theme's description first, then the script list:

```
Audio and video processing backed by ffmpeg

Theme 'av' (9 script(s)):

  av.dump_frames                            Dump all frames from a video clip
                                            Extract every frame between two timestamps to JPEG files.

  av.trim                                   Trim the media file that's just too damn long
                                            Cut a video or audio file to a start/end timestamp.
  ...

Run 'uv run main.py av.<script> --help' for usage details.
```

### Webapp

```sh
uv run webapp                           # start the local web UI (default: http://127.0.0.1:8000)
uv run webapp --port 9000               # custom port
```

The web UI lists all scripts grouped by theme, with live search, sortable
categories, favourites, and dark/light mode. Clicking a script opens a detail
page with an auto-generated form (built from `get_parser()`). Path-typed
arguments render as drag-and-drop file upload fields (except `--output` and
`--inputs` directory args, which remain text fields). Submitting the form runs
the script and streams its output via SSE, which can be cancelled mid-run;
completed runs are recorded and re-runnable from `/history`.

Uploaded files are saved to the theme's inputs directory via `POST /upload/{theme}`.

When a required dependency is missing (ffmpeg, pandoc, the pango stack, an
API key) it is named in the sidebar, at the top of any script page that needs
it, and — for ffmpeg — on a final onboarding slide, each with a one-click
Install where an unattended install command exists. See `core.capabilities`.

---

## Web UI layer

No build step. Jinja2 templates, one stylesheet, and Alpine.js — all served
locally so the packaged app works offline.

### Third-party assets, vendored

| Asset | Version | Path | Licence |
|---|---|---|---|
| Alpine.js | 3.15.12 | `static/js/alpinejs.min.js` | MIT |
| Alpine Focus plugin | 3.15.12 | `static/js/alpinejs-focus.min.js` | MIT |
| Inter (variable, latin) | — | `static/fonts/inter-latin-wght-normal.woff2` | SIL OFL 1.1 |
| JetBrains Mono (variable, latin) | — | `static/fonts/jetbrains-mono-latin-wght-normal.woff2` | SIL OFL 1.1 |

The focus plugin must load **before** Alpine core; it supplies `x-trap`, which
the settings modal uses for focus trapping. Fonts total ~89KB. PyInstaller
bundles `webapp/static` wholesale, so vendored assets need no spec changes.

### Templates

```
templates/
├── base.html              # shell: topnav, sidebar slot, $store.ui, splash
├── index.html             # script browser + Drop-to-Discover (scriptBrowser())
├── script.html            # script detail page (scriptRunner())
├── history.html           # past runs with re-run links
├── _splash.html           # boot overlay, plain JS — see below
├── _icons.html            # glyph(), icon(name, size, cls), icon_sprite() — the icon set
├── _components.html       # badge(), empty_state(), soon_button()
├── _macros.html           # theme_icon() — maps a theme to a glyph name
├── _settings_modal.html   # settings dialog
├── _script_form.html      # auto-generated argument form
├── _script_context.html   # right-hand context column
├── _terminal.html         # run status strip + streaming console
├── _sidebar.html, _onboarding_modal.html, _howto_modal.html
├── _capability_banner.html   # "this script needs X" + Install, shared by script.html and trim.html
├── _icon_placeholder.html    # stand-in glyph for icons not drawn yet (tracked in _icons.py)
├── _drop_{overlay,chooser,runner}.html   # browser-side drop: hint, wheel, runner
├── _drop_hint.html        # drop_hover()/drop_reject() macros, shared by both pages
├── _script_drop.html      # detail-page window-level drop target
└── scripts/av/trim.html   # hand-written override via a script's TEMPLATE attr
```

`webapp/static/style.css` is one file, sectioned with a table of contents at the
top. **Design tokens are defined in pairs**: every custom property in `:root`
has a matching entry in `html.dark`. Adding one without the other is a bug.

### Icons

There is one icon system: inline SVG on a 16×16 grid, stroked with
`currentColor`, defined once in `_icons.html`. Nothing is a raster and nothing
needs a dark-mode variant — the glyphs tint with the text colour they sit in.

`glyph(name)` holds the geometry. Two macros wrap it, and which one you want
depends on when the name is known:

| Known at | Use | Example |
|---|---|---|
| Template render | `icon(name, size, cls)` | `{{ icon('gear', 18) }}` |
| Runtime, from JSON | `<use :href="'#i-' + name">` | the drop chooser |

The second reads from the `<symbol>` sprite that `base.html` emits once per
page via `icon_sprite()`. Symbols deliberately carry **no** `stroke-width`, so
each consumer's CSS class picks a weight — the same glyph is drawn at 24px in
the wheel and 72px in the file chip, and one fixed stroke cannot serve both.

Adding a glyph means adding a branch to `glyph()` **and** its name to
`ICON_NAMES`; a name missing from the list renders standalone but is absent
from the sprite. `tests/webapp/test_icons.py` checks that every name referenced
by `webapp/_icons.py` and `_macros.html` actually resolves.

### Client-side state

Only two things live in `localStorage`, because only they must be known before
the first paint or before any request has returned:

| Key | Shape | Notes |
|---|---|---|
| `theme` | `"light"` \| `"dark"` | mirrors `UserConfig.theme` to avoid a dark-mode flash |
| `onboarding_seen` | `"1"` | |

Favourites and sort order used to be here too, and were therefore per browser
profile — the three launch tiers each kept their own set. They moved into
`UserConfig` on 2026-08-01 (`favourites`, `sort_order`, validated by
`clean_favourites` / `clean_sort_order`). `base.html` seeds them into the page
as `window.__PREFS__` via the `user_preferences_json()` Jinja global, so the
first paint already has the right stars, and writes changes back through
`POST /api/preferences`. A one-time migration lifts anything an older build
left in `localStorage`, then removes those keys.

`/favourites` still renders every script and lets Alpine hide the rest —
which rows are shown is a client decision made from the seeded set;
`[x-cloak]` covers the pre-init frame. `__THEME_META__`
carries each theme's label, script count and script keys — index-aligned with
that theme's entry in `__THEMES__` — so the client can filter and reorder
without a round trip. Sections reorder via the flex `order` property, so no DOM
nodes move.

### Splash screen

`_splash.html` covers the window until Alpine initialises, replacing the
unstyled `[x-cloak]`-blanked first paint. It is driven by **plain JS, not
Alpine** — an Alpine-driven splash could never dismiss itself if Alpine were the
thing that failed. It clears when Alpine initialises and fonts are ready, with a
1.2s font timeout, and falls back to a retry/open-logs error state after 4s.

### Web endpoints

Everything under `/static/` is served with `Cache-Control: no-cache`. The
packaged app binds the same port every launch, so every build shares one
browser origin; without the header the Chromium app window kept a stylesheet
from an older build indefinitely. ETag revalidation makes the usual cost a 304.

| Endpoint | Purpose |
|---|---|
| `GET /` | script browser |
| `GET /favourites` | the same browser, client-filtered to starred scripts |
| `GET /scripts/{theme}/{script_name}` | detail page + generated form |
| `GET /scripts/{theme}/{script_name}/run` | run the script, stream output as SSE (`start`, unnamed output, `progress`, `done`) |
| `POST /api/runs/{run_id}/cancel` | kill a running script and its whole process tree |
| `GET /history` | past runs, newest first, with re-run links |
| `POST /api/history/clear` | delete every stored run record |
| `POST /api/preferences` | write favourites and sort order into `UserConfig` |
| `GET /api/recent-outputs/{theme}/{script_name}?limit=` | files earlier runs of this script wrote and that still exist, for the detail page's recent-outputs panel |
| `GET /api/script-fields/{theme}/{script_name}` | field specs, minus the file input |
| `GET /api/preview-command/{theme}/{script_name}` | CLI equivalent of the current form state |
| `POST /upload/{theme}` | single-file upload |
| `GET /api/waveform` | peak envelope for a staged media file, for the `av.trim` editor |
| `POST /api/drop-upload` | multi-file drop; returns matching scripts |
| `GET`/`POST /api/settings` | read/write `UserConfig` |
| `POST /api/browse-folder` | native folder picker; 501 outside the desktop app |
| `POST /api/open-outputs` | reveal the outputs root |
| `POST /api/reveal-output` | reveal one produced file's folder |
| `POST /api/reveal-run-outputs` | reveal the folders one run wrote into, by run id |
| `POST /api/open-logs` | reveal the logs directory |
| `POST /api/quit` | shut the server down (frozen mode only) |
| `GET /api/update-check` | compare against the latest GitHub release |
| `GET /api/capabilities/{name}/install` | run a missing dependency's install command, output streamed as SSE |
| `GET /api/model-weights/{theme}/{script_name}` | which model weights the current form state would download; only for scripts exposing `models_for_args` |
| `GET`/`POST /api/keys` | list the API keys the app manages (set / not set, never the value) and store or clear one in `~/scriptorium/.env` |
| `GET /api/staged-input` | stream a staged input back to the page, for `av.trim` playback of a prefilled file; same containment rule as `/api/waveform` |

`preview-command` shares `webapp._form.build_argv` with the run endpoint, so the
previewed command cannot drift from what actually executes. It quotes with
`subprocess.list2cmdline` on Windows and `shlex.join` elsewhere, and prefixes
`scriptorium` when frozen, `uv run main.py` otherwise.

`browse-folder` requires `app.state.webview_window`, set by
`packaging/entrypoint.py` only on the pywebview tier. A browser cannot return an
absolute directory path, so on the other two launch tiers the endpoint returns
501 and the UI disables the button.

### Run output classification

`_stream_script` yields stdout lines, then stderr lines wrapped in
`<span class='stderr'>`, then an exit line and a `done` event carrying
`{exit_code, elapsed, status, outputs}`. The client maps these to console
severities.

One special case: `core/runner.py` writes its own run banner
(`[av.filmstrip] done in 1.2s`) to **stderr** as routine progress. Without
handling, every successful run would render as a wall of warnings, so the client
demotes lines matching `^\[<key>\] ` to info — unless they say `failed`.

Output artifacts are detected server-side from what the script printed; see
`core.outputs.find_reported_outputs` and the "Recent outputs panel" entry in
BACKLOG.md for what that heuristic does and does not cover.

A printed path counts as a result if it is inside the managed outputs tree
**or** was last modified after the run started. The second test is what lets a
file the user sent to `~/Downloads` be reported at all, while still not
crediting a script with writing an input path it merely echoed — that file
predates the run. `_stream_script` passes the run's start time as `since`.

Revealing a result in the OS file manager is gated the same way round:
`webapp.app._is_revealable` accepts anything under the outputs root, plus any
path a past run was recorded as having written. That keeps `POST
/api/reveal-output` from becoming "open any folder on this machine" for whatever
else can reach localhost. `POST /api/reveal-run-outputs` takes a run id instead
of a path and needs no such check — the folders come from what the server itself
recorded.

### Waveforms are read server-side

`av.trim` draws a waveform so a cut can be placed by eye. That waveform used to
be decoded in the browser — `decodeAudioData` over the uploaded file — which
made the editor's usefulness a property of the browser rather than of the file.
MP3 needs a Chromium built with proprietary codecs, which not every one is, and
MKV, AVI, FLV and WMA are never decodable that way. A file `av.trim` could
happily cut would show "Waveform unavailable" and send the user back to typing
timestamps blind. A file arriving via the drop overlay got no waveform at all,
in any format, because the prefill path never decoded anything.

`GET /api/waveform?path=…&buckets=900` answers with
`{"duration": float, "peaks": [float, …]}`, peaks normalised so the loudest is
`1.0`. ffmpeg is already a hard requirement for every `av.*` script, so the
machine running the editor can always decode what the editor is about to cut.

Three things worth not rediscovering, all in `webapp/_waveform.py`:

- **Peaks, not averages.** A waveform is centred on zero, so an average over
  thousands of samples tends to zero regardless of how loud the audio is. Every
  file would draw a flat line.
- **The decode rate is chosen per file**, from its duration and the bucket
  count, and clamped to `[1000, 8000]` Hz. The ceiling stops a short file being
  decoded at far more resolution than 900 bars can show; the floor stops the
  resampler's low-pass flattening a two-hour recording into a silent-looking
  line. Between them the PCM held in memory stays bounded whatever the input.
- **Playback is separate and best-effort.** The browser decode still happens,
  but only to power the play button, and only on the upload path where a `File`
  object exists. When it fails the waveform is unaffected — the play button
  simply does not appear. This is the reverse of the old coupling, where a
  failed decode cost the waveform too.

The endpoint reads whatever it is pointed at, so which paths it will accept is
the whole of its security. `_waveform.resolve_staged_input` resolves the path
first (collapsing `..` and symlinks) and then requires it to sit inside the
shared inputs root — the only place `POST /upload/{theme}` and drop sessions
ever write. Anything else is a 403.

### Trimming respects what was asked for, not where the keyframes are

A stream copy cannot begin mid-GOP, so `-ss` before `-i` seeks *backwards* to
the nearest keyframe. On a sparsely-keyed source — a long GOP, a low frame
rate, a screen recording — that keyframe can be seconds before the requested
cut. Trimming the first second off such a file reported success and handed back
something indistinguishable from the original.

`av.trim --mode` decides what to do about it:

| Mode | Behaviour |
|---|---|
| `auto` (default) | Probe where a copy would actually land. Within `KEYFRAME_TOLERANCE` (0.1 s) of the request → stream copy, as before. Further than that → re-encode, and say so on stdout. |
| `fast` | Always stream-copy, accepting the keyframe snap. The old behaviour, kept as an opt-out. |
| `precise` | Always re-encode. |

`scripts.av._utils.copy_would_land_on` is the decision. It short-circuits twice
before spending an ffprobe: a cut at `0` is always exact, and an audio-only
file has no GOP to round to (audio frames are milliseconds long, so a copy
lands closer than anyone can hear). Only a real video stream is probed — cover
art is a video stream to ffprobe, so `has_video_stream` excludes attached
pictures, or every MP3 with artwork would be treated as having keyframes.

The probe reads *packets*, not frames, and only up to the requested cut point:
a keyframe is a packet flag, so this demuxes rather than decodes, and the cost
does not grow with however much file follows the cut.

A re-encode keeps input-side seeking — modern ffmpeg seeks to the preceding
keyframe and then decodes and discards up to the exact point, so the cut is
accurate without decoding the whole file. Audio is `-c:a copy`: it has no GOP
to be inaccurate about, and since the output container is the source's own, its
codec is muxable by definition. No video encoder is named, for the same reason
`formats.convert_video` names none — ffmpeg's default for a container is
muxable into it, which `libx264` is not for every container.

### `av.join` and the output container

`av.join` takes the output extension from the first input and re-encodes audio
during preprocessing, so the container has a say in three places
(`_resolve_profile` in `scripts/av/join.py`): the audio codec follows it (Opus
for `.webm`/`.ogg`/`.opus`, AAC otherwise); a copied video codec the container
will not hold (`_CONTAINER_VIDEO_CODECS`) forces a re-encode even when the
inputs agree with each other; and a re-encode — always H.264 + AAC — bound for a
container that cannot hold that pair is written as `.mp4` instead, with a line on
stdout saying so. `join()` returns the path actually written. Intermediates go to
`.mp4` when AAC and an MP4-friendly codec allow it, `.mkv` otherwise.

### Progress reporting

A script is a subprocess, so its only channel to the UI is its own output. A
stdout line prefixed `::progress::` followed by JSON
(`{"fraction": 0.42, "label": "0:12 / 0:30"}`) is a progress report rather than
output. `_stream_script` pulls those lines out and re-emits them as
`event: progress`, so they never reach the terminal and never reach output
detection — a label that happens to look like a path is not credited as a
written file. A malformed sentinel line is left alone and shown as ordinary
output, on the grounds that a stray visible line beats a swallowed one.

`fraction` may be `null`, meaning the script is working but cannot say how far
along it is; the client's bar stays indeterminate for that rather than sitting
at zero.

Scripts do not write the sentinel by hand — `core/progress.py` owns it:

| Producer | Used by | Axis |
|---|---|---|
| `scripts.av._utils.run_ffmpeg_with_progress` | one long ffmpeg pass — `av.{trim,volume,video_crop,dump_frames,to_anim}`, `formats.convert_{audio,video}` | position within the output, from ffmpeg's `-progress pipe:1` |
| `core.progress.ProgressReporter` directly | many short ffmpeg calls — `av.{split,filmstrip,join}` | calls completed |
| `core.downloads.reporting_downloads` | model weights fetched by rembg — `photo.remove_bg` | bytes received, from pooch's progress-bar hook |

The split matters. Where a script makes N short calls, ffmpeg's own progress
reports against a different total each time, so the bar would reset on every
file boundary; calls-completed is the axis the user is actually waiting on. The
two are never mixed within one script.

Two further rules, both enforced in `core/progress.py`:

- **Throttling is the producer's job.** ffmpeg reports about twice a second and
  a run can last an hour. `ProgressReporter` drops updates arriving inside
  `MIN_INTERVAL_SECONDS` (0.4) and repeats of the same whole percent.
- **A human at a terminal never sees a sentinel.** For a CLI run the reporter
  writes a carriage-returned percentage to stderr instead, and stays silent
  when stderr is not a tty — so piping a script's output somewhere does not
  fill it with progress noise. The caller is distinguished by
  `core.invocation.is_webapp_run()`.

`run_ffmpeg_with_progress` reports against the **output** duration, which is not
the source duration whenever a script trims or changes speed — `av.trim`,
`av.dump_frames` and `av.to_anim` each compute their own. It drains stderr on a
thread; reading stdout to exhaustion first would deadlock on any file verbose
enough to fill the stderr pipe.

---

## Run lifecycle

### Cancellation

A run is not one process. `main.py` spawns the script, which shells out to
ffmpeg or yt-dlp — so killing the direct child leaves the real worker running
and writing to disk. On Windows this is not a subtlety: `Process.kill()` is an
alias for `terminate()`, which calls `TerminateProcess` on that PID alone.

`webapp/_runs.py` therefore kills the tree:

| Platform | Spawn (`spawn_kwargs()`) | Kill |
|---|---|---|
| Windows | `creationflags=CREATE_NO_WINDOW` | `taskkill /T /F /PID` — `/T` walks the tree |
| POSIX | `start_new_session=True` — child leads its own process group | `killpg(SIGTERM)`, then `SIGKILL` after a 3s grace |

Flow: `run_script` mints a `run_id` and registers a `RunHandle`;
`_stream_script` emits `event: start` carrying that id before any output;
`POST /api/runs/{run_id}/cancel` looks the handle up and kills the tree.
A finished run is discarded from the registry, so cancelling it returns 404.

A killed process still exits non-zero, so `handle.cancelled` — not the exit
code — decides whether an ending is a cancellation or a failure.

Cancel deliberately leaves partial output files in place, and navigating away
mid-run still lets the script finish. Both are choices, not omissions.

### History

`core/history.py` stores completed runs in `~/scriptorium/history.json`
alongside `config.json`, newest first, capped at `MAX_ENTRIES` (200). It holds
no live process state — a `RunRecord` is a plain value: run id, key, argv,
params, status, exit code, start time, elapsed, the output files detected
(`outputs`, best-effort, from what the script printed) and a `batch_id` that
groups the runs of one per-file fan-out.

`argv` is what actually ran; `params` is what the user typed. Re-run needs the
latter, which is why both are stored.

A corrupt file degrades to an empty history rather than raising, and a single
malformed entry is skipped instead of discarding the rest.

### Re-run

Re-run is a **link**, not an endpoint:
`/scripts/{theme}/{script}?_rerun=1&<params>`. It reuses the query-param
prefill the Drop-to-Discover flow already had; `_applyPrefill()` triggers on
either `_prefill_file` or `_rerun`. It lands on a filled-in form rather than
firing immediately — re-running a long transcode from one unseen click is a
footgun. Stored paths may no longer exist; the script reports that itself.

### Building a standalone app

```sh
bash build.sh
```

A unified build entrypoint in the repo root. It detects the OS via `uname` and
delegates to the platform-specific pipeline. On macOS it auto-installs missing
tools (uv, Homebrew, ffmpeg) before building. On Windows it validates that Inno
Setup is available, then delegates to `packaging/build_installer.bat`.

| Platform | Shell | Output |
|----------|-------|--------|
| macOS | Terminal / zsh | `dist/Scriptorium.app` |
| Windows | Git Bash | `dist/ScriptoriumSetup.exe` |
| Linux | bash | `dist/scriptorium-linux-x86_64.tar.gz` |

A GitHub Actions workflow (`.github/workflows/release.yml`) builds all three
platforms and uploads artifacts to a GitHub Release on tag push (`v*`).

The platform-specific scripts below can still be invoked directly.

#### Spec constraints that apply to all three platforms

A frozen build fails *silently*: `core.registry.discover` skips any script whose
imports raise, so a missing module removes the script from the UI rather than
producing an error. `tests/packaging/test_specs.py` guards the rules below
without needing a build.

- **Scripts and core are collected, never hand-listed.** `collect_submodules`
  in every spec; a literal module list drifts the moment a script is added.
- **`rembg`, `onnxruntime`, `weasyprint` and `pillow_heif` need
  `collect_all`.** Static analysis cannot see their data files and native
  libraries. `webview`, `clr`, `clr_loader` and `pythonnet` are the opposite
  case on Windows — excluded outright, see "Windows app" below.
- **`unittest` must not be excluded.** scipy imports `array_api_compat`, which
  runs `from numpy import *`; `testing` is in numpy's `__all__`, so that fires
  numpy's lazy `__getattr__` into `numpy/testing/__init__.py` and its
  `from unittest import TestCase`. Excluding it breaks `photo.remove_bg`
  (rembg → pymatting → scipy) in the built app only. `numpy.testing` is listed
  in `hiddenimports` for the same reason — the lazy import is invisible to
  static analysis.
- **rembg's dependency metadata is copied recursively.** `pymatting/__init__.py`
  ends with `importlib.metadata.version(__name__)` and does not guard it, so a
  bundle without its `dist-info` raises `PackageNotFoundError` on import.
  `_metadata("rembg")` uses `copy_metadata(..., recursive=True)` to cover the
  whole graph rather than one package at a time.

### macOS app

```sh
bash packaging/build.sh                 # → dist/Scriptorium.app
```

The `.app` bundle uses PyInstaller. On launch it finds a free port, starts
uvicorn, and tries three display tiers in order:
1. **pywebview** native window (WKWebView on macOS, GTK/Qt on Linux; not attempted on Windows)
2. **Chromium `--app` mode** — chromeless window via Chrome/Edge/Chromium
3. **Default browser** fallback — user quits via the sidebar Quit button

Scripts run as subprocesses via the frozen binary's `--run-script` flag (same
binary, different argv). The sidebar hides the CLI usage section and shows a
Quit button when running in frozen mode. A `/api/quit` endpoint (frozen-only)
allows the UI to signal the server to shut down.

#### CLI vs GUI dispatch

One binary serves both modes, so `packaging/entrypoint.py` has to decide which
the user meant. In order:

| Condition | Mode |
|---|---|
| `--run-script <key>` | CLI (internal subprocess dispatch) |
| Any other argument present | CLI |
| Bare launch, stdout is a tty | CLI (lists all scripts) |
| Bare launch, stdout is not a tty | GUI |

The tty check is the load-bearing part, and it must not be weakened back to
`sys.stdout is not None`. Only a Windows windowed build gets `None` streams; a
macOS `.app` launched from Finder inherits valid stdio from launchd pointed at
`/dev/null`, so the `None` check sent every Finder launch into the CLI, which
printed the script list to nowhere and exited — a dock bounce and no window.
`-psn_0_<pid>`, which LaunchServices may append, is stripped before the argument
check so it is not mistaken for a script key.

#### Tray icon threading

`close_behavior = "tray"` keeps the app resident when the window closes. The
threading model is platform-specific by necessity: pystray's macOS backend calls
`-[NSApplication run]` inside `Icon.run`, and AppKit aborts the process with
SIGTRAP if that happens off the main thread — a signal, so no `except` can
contain it.

| Tier | macOS | Linux | Windows |
|---|---|---|---|
| 1 — pywebview | `run_detached()`, serviced by the shared `NSApplication` that `webview.start()` runs | `Icon.run` on a background thread | **not attempted** |
| 2 — Chromium `--app` | no tray (no GUI main loop to service an `NSStatusItem`) | `Icon.run` on a background thread | `Icon.run` on a background thread |

Windows has no tier 1: `_load_webview` returns `None` on `win32` without
importing anything, and the spec excludes `webview`, `clr`, `clr_loader` and
`pythonnet` from the bundle. See BACKLOG.md for why that stack can never start
in a frozen build.

See BACKLOG.md for the tier-2 macOS gap.

Two rules keep the tiers from each showing an icon at once:

- **Tier 1 settles whether it can run before it creates anything.**
  `_load_webview` imports the backend via `webview.guilib.initialize()` up
  front. `webview.start()` would do that itself, but only after a window and a
  tray icon exist, and a failure at that point strands the icon.
- **`_stop_tray` waits for the icon's loop before stopping it.**
  `pystray.Icon.stop()` begins `if self._running:`, and `_running` is only set
  once `Icon.run` has come up on its own thread. Stopping earlier is silently
  discarded and the icon appears afterwards, with nothing left able to remove
  it. `_create_tray_icon_for` therefore publishes a readiness `Event` from its
  `setup` callback — which, being custom, must also set `visible` itself,
  because it replaces the default callback that would have shown the icon.

On startup the app checks GitHub Releases for a newer version and shows a
banner in the sidebar if an update is available.

#### macOS build details

| Item | Value |
|------|-------|
| Build script | `packaging/build.sh` |
| PyInstaller spec | `packaging/scriptorium.spec` |
| Output | `dist/Scriptorium.app` |
| Prerequisites | Python 3.14, uv, Xcode command-line tools |
| Webview backend | pywebview + Cocoa (WKWebView) |

The build script runs three steps: `uv sync --all-extras` (install all optional
dependencies), `uv pip install pyinstaller`, and `pyinstaller packaging/scriptorium.spec`.
The resulting `.app` is unsigned — on a Mac that did not build it, the quarantine
flag must be cleared before launch: `xattr -cr dist/Scriptorium.app`.

### Windows app

```cmd
packaging\build_installer.bat           # → dist\ScriptoriumSetup.exe
```

The Windows build uses PyInstaller in folder-bundle mode (no macOS `BUNDLE`
step). The entry point is the same `packaging/entrypoint.py`, but Windows
skips the pywebview tier entirely (its WinForms backend cannot start in the
frozen build — see "pywebview cannot start in the frozen Windows app" in
BACKLOG.md's Settled section), so the cascade there is two tiers: Chromium
`--app` mode (Edge/Chrome), then the default browser.

#### Windows build details

| Item | Value |
|------|-------|
| Build script | `packaging/build_installer.bat` |
| PyInstaller spec | `packaging/scriptorium-win.spec` |
| Inno Setup script | `packaging/installer.iss` |
| Output | `dist/ScriptoriumSetup.exe` |
| Prerequisites | Python 3.14, uv, Inno Setup 6+ (`iscc` on PATH) |
| Window | Edge or Chrome in `--app` mode; default browser as fallback. pywebview is not used on Windows |

`build_installer.bat` runs the full pipeline: dependency sync, PyInstaller
folder bundle, and Inno Setup compilation — producing a single
`ScriptoriumSetup.exe` in one command.

The installer supports two privilege modes via a dialog shown at launch:

| Mode | Install path | Elevation |
|------|-------------|-----------|
| Install for all users | `C:\Program Files\Scriptorium` | UAC admin prompt |
| Install just for me | `%LOCALAPPDATA%\Programs\Scriptorium` | None |

Both modes create Start Menu shortcuts and optionally add the install directory
to the user's PATH for CLI usage. Silent installs can select mode via
`/allusers` or `/currentuser` command-line switches.

### Linux binary

```sh
bash packaging/build_linux.sh           # → dist/scriptorium-linux-x86_64.tar.gz
```

#### Linux build details

| Item | Value |
|------|-------|
| Build script | `packaging/build_linux.sh` |
| PyInstaller spec | `packaging/scriptorium-linux.spec` |
| Output | `dist/scriptorium-linux-x86_64.tar.gz` |
| Prerequisites | Python 3.14, uv |
| Webview backend | pywebview + GTK (falls back to Chromium `--app` or browser) |

Extract the tarball and run `./scriptorium`. The app detects Chrome, Chromium,
or Edge on PATH for the `--app` mode window. If none are found, it opens the
default browser.

### Programmatic

```python
from scripts.<theme>.<script> import <function>
from core.runner import run_fn

result = run_fn(some_fn, arg1, arg2, kwarg=value)
```

`run_fn` applies the same middleware as the CLI path (timing, future hooks).
Use direct imports only in tests.

---

## Theme package anatomy

Each `scripts/<theme>/` directory is a Python package. Its `__init__.py` must define:

| Name          | Type   | Purpose                                                             |
|---------------|--------|---------------------------------------------------------------------|
| `LABEL`       | `str`  | Display name used in the web UI sidebar and CLI listings            |
| `DESCRIPTION` | `str`  | One-line tagline shown below the theme name in the web UI and at the top of `uv run main.py <theme>` output |
| `HIDDEN`      | `bool` | *(optional, default `False`)* When `True`, the theme is excluded from the UI, CLI listings, and discovery |

The module docstring is conventional documentation — it is not used by the runtime.

```python
"""A/V manipulation scripts backed by ffmpeg."""

LABEL = "A/V"
DESCRIPTION = "Audio and video processing backed by ffmpeg"
```

`theme_labels()` and `theme_descriptions()` in `core/registry.py` read these
attributes at runtime. Both fall back gracefully if an attribute is absent.
Themes with `HIDDEN = True` are filtered out by all registry functions.

---

## inputs / outputs convention

Every theme reads from and writes to a shared layout rooted at the repo:

```
inputs/             # drop source files here (shared across every theme)
    processed/      # successful runs auto-archive their inputs here
outputs/
    <theme>/        # results land here, one subdirectory per theme
```

### Relative paths depend on who is calling

The web UI and a person at a terminal want opposite things from a relative
path, and both reach a script through the same `argv`. The caller is therefore
announced out of band, via `SCRIPTORIUM_CALLER=webapp` in the spawned
environment (`core/invocation.py`), and the two resolvers read it:

| | Bare-filename input | Default output (no `--output`) | Relative path with a directory part |
|---|---|---|---|
| Web UI | `inputs/` | `outputs/<theme>/` | the user's home directory |
| Human CLI | current directory | current directory | current directory |

```sh
# from a terminal — reads ./clip.mp4, writes ./<stamp>.mp3
cd ~/Music && scriptorium formats.convert_audio clip.mp4 --to mp3
```

An **environment variable rather than a flag**, because the two spawn paths do
not share an argv shape: frozen runs go through `--run-script`, but a
development run is `python main.py <key>`, which is exactly what a human types.
There is nothing in the arguments to key off.

Two deliberate exceptions:

- **No argument at all still means `inputs/`, for both callers.** `scriptorium
  photo.remove_bg` with no source means "process the inputs folder". Making it
  mean "process every image in my current directory" is destructive by default
  in a way an explicit path is not.
- **`./name` does not force the cwd.** `Path` normalises the leading `./` away
  at construction, so it is indistinguishable from `name`. Use a real directory
  part if you need to be explicit.

### Nothing user-supplied stays relative

A path typed into the web UI never passes through a shell. Nothing expands `~`
and nothing anchors a relative path, so `~/Downloads/x.txt` arrives as a
*relative* path whose first component is a directory literally named `~` — and
writing to it creates that directory next to wherever the server was started.

`core.outputs.anchor_user_path(raw, theme=...)` is the single place this is
handled, and every resolver runs a value through it before looking at its shape:

| User types | Web UI | Human CLI |
|---|---|---|
| `~/Downloads/x.txt` | `$HOME/Downloads/x.txt` | `$HOME/Downloads/x.txt` |
| `/Volumes/ext/x.txt` | used as-is | used as-is |
| `Downloads/x.txt` | `$HOME/Downloads/x.txt` | `$PWD/Downloads/x.txt` |
| `x.txt` | `outputs/<theme>/x.txt` | `$PWD/x.txt` |

The bare-name row is the one asymmetry, and it is deliberate: a name with no
location in it at all is the only form the managed outputs tree can claim, and
being inside that tree is what puts the file in the UI's results list.

`core.paths.resolve_input` applies the same rules to inputs, except that a bare
name means a file staged in `inputs/` rather than one in the outputs tree.

Scripts must not hand-roll this. `core.paths.resolve_input(source, theme)` is
the single implementation — 18 hand-written copies of a
`if source.parent == Path("."):` check is how the inconsistency arose in the
first place.

### Post-processing: archiving input files

A script that *consumes* a file moves it to `inputs/processed/` after a
successful run, and does so by calling `core.paths.move_to_past_inputs(theme,
source)`. That helper is not a convenience — it is the rule:

**Only files that live inside the shared `inputs/` tree are moved.** A file the
user pointed at somewhere else on the disk is read and left exactly where it
was. Pointing a script at `~/Movies/holiday.mp4` must never relocate it.

The archive is flat, and the original filename is kept:

```
inputs/
    result.json              ← before run
    holiday.mp4
    processed/
        result.json          ← after a successful run
        holiday.mp4
```

A name collision inside `processed/` appends `_YYYYMMDDTHHMMSS` to the stem, so
an earlier archived copy is never overwritten. Files already inside
`processed/` are skipped, so re-running against the archive does not shuffle it.

The return value is ignored by every caller: failing to tidy up is not a reason
to fail a run that already produced its output.

#### Which scripts archive

| Archives | Does not archive | Why not |
|---|---|---|
| `av.dump_frames`, `av.filmstrip`, `av.join`, `av.split`, `av.to_anim`, `av.trim`, `av.video_crop`, `av.volume` | `downloads.download`, `sitemaps.status_check`, `util.notify` | take a URL or a message, not a file |
| | `util.cleanup` | manages the archive itself |
| `av.tag` (only when writing a *new* file) | `av.tag` in read mode and `--in-place` | nothing is consumed; `--in-place` rewrites the input itself |
| `formats.convert_*` (via `_utils.run_convert`) | `gif.make_gif` | reads a *directory* of frames; flattening a frame set into the archive root collides on every `frame_001.png`, and frames get re-rendered at other settings |
| `photo.remove_bg` | `lora.*` | operate on a dataset directory in place — archiving it would destroy the dataset |
| `speech.transcribe` | `telegram.preprocess`, `telegram.embed_messages`, `telegram.chat_analysis` | chained or repeat-read: a later step needs the file the earlier one was given |
| `telegram.group_analysis` | | |

`tests/test_input_archiving.py` pins this inventory, so adding a script forces
the decision rather than letting it inherit whichever behaviour was copied. It
also fails any script that builds its own `processed/` directory — three
separate hand-rolled archivers existed before this was centralised, and one of
them (`av.join`) created `processed/` inside whatever directory it was pointed
at and moved the user's media into it.

### `core.paths` — centralized path resolution

All path resolution goes through `core.paths`, which detects whether the app is
running as a frozen PyInstaller bundle or in development. `inputs_dir()` is
theme-agnostic (every script shares the same inputs folder); `outputs_dir()`
remains keyed by theme; `past_inputs_dir()` always points at the same
`inputs/processed/` archive:

| Mode   | `inputs_dir("av")` | `outputs_dir("av")`         | `past_inputs_dir("av")`        |
|--------|--------------------|-----------------------------|--------------------------------|
| Dev    | `inputs/`          | `outputs/av/`               | `inputs/processed/`            |
| Frozen | `~/scriptorium/inputs/` | `~/scriptorium/outputs/av/` | `~/scriptorium/inputs/processed/` |

Theme helpers delegate to `core.paths`:

```python
from core.paths import inputs_dir, outputs_dir

def av_inputs_dir() -> Path:
    return inputs_dir("av")
```

`core.paths` also provides `templates_dir()`, `static_dir()`, `assets_dir()`,
`logs_dir()`, `outputs_root()`, `drop_session_dir()`, `resolve_input()`,
`move_to_past_inputs()`, `read_version()` and the `FROZEN` boolean. It used to
carry `has_ffmpeg()`; that moved into
`core.capabilities` below, which answers the same question for every dependency
rather than one.

### `core.capabilities` — what this machine can actually do

Scriptorium depends on things Python cannot install: ffmpeg, pandoc, the
pango/cairo/glib stack, an OpenAI key, rembg model weights fetched on first use.
Each used to fail its own way — a bespoke sidebar banner for ffmpeg, a raw
`CalledProcessError` for pandoc, an `OSError` from inside cffi for pango.

`core.capabilities` makes them one shape. A `Capability` carries `name`,
`label`, `present`, `needed_for` (what stops working), `hint` (prose, already
resolved for this platform), `command` (argv the app can run to fix it, or
empty), `env_var` (for a key the user types in), `remedy` and `required`:

| Capability | Probe | Needed by | Required |
|---|---|---|---|
| `ffmpeg` | `ffmpeg` **and** `ffprobe` on PATH | `av.*`, `formats.convert_{audio,video}` | yes |
| `pandoc` | on PATH | `formats.convert_docs` | yes |
| `pango` | real `import weasyprint`, after `core.native_libs` | `telegram.{chat,group}_analysis` | yes |
| `weasyprint-cli` | on PATH | nicer `convert_docs` PDFs | no |
| `gifsicle` | on PATH | `av.to_anim --optimize` | no |
| `openai-key` | `OPENAI_API_KEY` after `load_env()` — the probe loads `.env` itself, so a CLI caller and the webapp agree | `speech.transcribe` | yes |

`required=False` exists so an optional dependency is reported without being
alarming: a missing gifsicle costs a larger GIF, not a script.

Rules worth not rediscovering:

- **Probe results expire** (`CACHE_SECONDS`). The old `has_ffmpeg()` was
  evaluated once at import into a Jinja global, so installing ffmpeg and
  reloading still showed the banner until the app was restarted. The Jinja
  globals are named wrapper functions, not the bound `capabilities.missing` —
  binding the function object directly reintroduces the same early binding in a
  less visible place.
- **A probe never fails a render.** One that raises counts as absent.
- **`pango` is probed by importing weasyprint for real**, not by guessing at
  library filenames. The failure mode *is* that the libraries exist but cannot
  be resolved, so only an actual load settles it — and
  `core.native_libs.ensure_native_lib_resolution()` has to run first, or a
  working Homebrew/MSYS2 install reads as missing.
- **`photo.remove_bg` is not in the registry.** Its dependency is a *per-model*
  weights file, so it goes through `model_weights_present(model)` instead.
- **`command` is separate from `hint`.** The hint is prose for a human; the
  command is argv the app runs itself from the sidebar's Install button, and it
  exists only where one unattended command is the whole fix — winget on
  Windows, brew on macOS. apt needs sudo, pango on Windows needs MSYS2, a key
  needs typing, so those have no command and render a disabled button. winget
  is invoked with every accept/non-interactive flag, since nobody is there to
  answer it. After a successful install `refresh_environment()` re-reads PATH
  from the registry on Windows — a running process otherwise keeps the PATH it
  started with and would report the new binary missing until a restart.
- **The Install button appears in three places**, all driven by the same
  Alpine component: the sidebar banner (every missing required capability), a
  banner at the top of a detail page whose script needs something absent
  (`capability_for_script`), and a fourth onboarding slide rendered only while
  ffmpeg is missing. ffmpeg is deliberately **not bundled** — see HUMAN_TODO.md
  item 1 and the Settled backlog entry for why.
- **A configure remedy is a key, and keys are typed in, not installed.** A
  capability with `env_var` set (`openai-key` → `OPENAI_API_KEY`) renders a
  "Set key" button that opens Settings → Keys. The value goes through
  `core.env.set_env_value` into `~/scriptorium/.env` — the install directory
  is read-only for the packaged app, and `config.json` is not a secrets store
  — and into the process, then the probe cache is dropped. `/api/keys` reports
  set / not set and never returns a value; the field clears itself after
  saving. `load_env()` reads the repo `.env` first and the user one second,
  so a developer's file wins.

The script→capability map lives here, keyed by dotted key first and theme
second. It is deliberately *not* merged with `webapp/_badges.py`'s tool map,
which answers a different question — "what does this script drive", including
yt-dlp, which ships in the bundle and so is never missing.

Two entries the earlier BACKLOG.md notes got wrong: `gif.make_gif` needs no
ffmpeg (it assembles frames with Pillow), and the pango dependency belongs to
the two Telegram scripts that render PDFs, not the whole theme.

### `core.images` — every Pillow script opens the same formats

Pillow does not read HEIC/HEIF, the format every phone camera writes.
`pillow-heif` adds it by registering an opener, and `core.images.ensure_image_formats()`
does that registration once, tolerating the package's absence. Any script that
calls `Image.open` calls it first — `formats.convert_image` and `photo.remove_bg`
today — so `IMAGE_EXTS` and what actually opens cannot drift apart. Two facts
about HEIC that belong in the code rather than in a support thread: a Live Photo
opens as its primary still, and orientation lives in EXIF, so a script writing
to a format without EXIF must bake it in with `ImageOps.exif_transpose`. Both
scripts do, for every input format — which also fixed sideways JPEG-to-PNG
conversions that predate HEIC.

### `core.outputs` — standardized output path resolution

All scripts use `core.outputs` for output file naming and placement. The four
a script reaches for:

| Function | Purpose |
|----------|---------|
| `default_stem()` | Returns `YYYYMMDD_HHmm` timestamp string for default filenames |
| `deduplicate(path)` | Appends `_001`–`_999` suffix if `path` already exists |
| `resolve_output(output, *, theme, ext)` | Resolves a user-provided `--output` value (or `None`) to a concrete file path |
| `resolve_output_dir(output, *, theme)` | Same, but resolves to a directory (for multi-file output scripts) |

Alongside them: `resolve_single_output` (one file in, one file out, honouring an
explicit filename), `names_a_file` (does an `--output` value name a file or a
directory), `anchor_user_path` and `relative_root` (see "Nothing user-supplied
stays relative"), and `find_reported_outputs` (see "Output detection").

The value is first made absolute by `anchor_user_path` (see "Nothing
user-supplied stays relative" above); what is left is a question of shape:

| User provides | Behaviour |
|---------------|-----------|
| Nothing (`None`) | `outputs/<theme>/YYYYMMDD_HHmm.ext` |
| Existing directory | `<dir>/YYYYMMDD_HHmm.ext` |
| Path with a file extension | Used as the output file |
| Path without an extension | Treated as a new directory + `YYYYMMDD_HHmm.ext` |

All scripts expose a single `--output` / `-o` flag (replacing the former
`--outputs` directory flag). Scripts that produce a single file use
`resolve_output()`; scripts that produce multiple files use
`resolve_output_dir()` combined with `default_stem()` for indexed naming
(e.g. `20260620_1706_001.mp4`, `20260620_1706_002.mp4`).

---

## Script anatomy

Every file the registry picks up must expose three names at module level:

| Name          | Type       | Purpose                                      |
|---------------|------------|----------------------------------------------|
| `TITLE`       | `str`      | One-line label shown in `uv run main.py`     |
| `DESCRIPTION` | `str`      | Sentence shown in `--help` and theme listing |
| `run()`       | `Callable` | CLI entrypoint — owns argparse + `sys.exit`  |

### Optional: `ACCEPTS`

Scripts that operate on dropped files declare which file categories they handle:

```python
ACCEPTS: set[str] = {"video", "audio"}
```

Valid categories are defined in `core/categories.py`: `video`, `audio`, `image`,
`tabular`, `document`. When present, the script appears on the Drop-to-Discover
wheel when a user drops a matching file onto the index page. Scripts without
`ACCEPTS` are excluded from drop results.

#### Batch classification

How a script behaves when several files are dropped is **inferred**, not
declared — `webapp._form.batch_mode_for()` reads it off the argument parser:

| Batch mode | Inferred from | Behaviour |
|---|---|---|
| `directory` | file input has widget `file-multi` (an optional `Path` positional), or its dest is `inputs` | one invocation against the drop session directory |
| `per_file` | file input has widget `file` | one invocation per dropped file, in sequence, sharing a `batch_id`; the card says "Runs N times, once per file" |

To make a new script batch-capable, give its source argument `nargs="?"` and
have it accept a directory, as the `formats.convert_*` scripts do. A `per_file`
script is run once per dropped file by a loop in `scriptBrowser.startRun()`;
`RunRecord.batch_id` groups the resulting records.

#### Drop sessions

Every drop or clipboard paste writes into its own directory,
`inputs/drop/<timestamp>-<random>/` (see `core.paths.drop_session_dir`), so a
directory-native script never sees files from an earlier drop. All files in one
drop must share a category; mixed batches are rejected by `/api/drop-upload`.

#### Drop targets

A file drop is accepted anywhere in the window, but what it means depends on
which page you are on:

| Page | Handler | Behaviour |
|---|---|---|
| browser (`/`, `/favourites`) | `scriptBrowser` in `index.html` | stages via `/api/drop-upload`, opens the radial chooser — the script is not yet known |
| script detail | `scriptRunner` in `script.html` | prefills *this* script's file input — the script is already chosen |

The detail page deliberately does **not** reuse the browser's staging. Because
the target script is already known, the useful answer needs no session
directory, no category matching and no chooser — just the upload the form's own
dropzone already did. So the page-wide handler funnels into the same `_send()`
and the form dropzone keeps its inline highlight, with `@drop.prevent.stop` so
one drop is not handled twice.

Type checking is client-side, against the `accept_exts` string already rendered
for the file input (derived from `ACCEPTS` — see `accept_exts_for`). A script
declaring no categories accepts anything. Rejections are explained in a toast
rather than ignored: wrong extension, no file input on this script, or more than
one file for a single-file input.

`preventDefault` is called inside the handlers and only for drags carrying
files, not via Alpine's `.prevent` — the unconditional version would stop text
being dragged into a path field.

**Not covered:** `scripts/av/trim.html` overrides the template with its own
`trimApp` component and so has no window-level drop. A file arriving from the
global drop overlay still *prefills* the page, and since the waveform moved
server-side it now draws for a prefilled file too; what is missing is dropping
onto the detail page itself. See the "Unify the trim.html console" entry in
BACKLOG.md.

### Optional: `get_parser()`

Scripts may also expose:

```python
def get_parser() -> argparse.ArgumentParser: ...
```

When present, the web UI uses it to auto-generate an argument form.
`run()` should call `get_parser().parse_args()` instead of constructing the parser
inline, so the two stay in sync automatically.

| Name           | Type       | Purpose                                                  |
|----------------|------------|----------------------------------------------------------|
| `get_parser()` | `Callable` | Returns the script's `ArgumentParser` without parsing    |

### `run()` — CLI only

- Parses `sys.argv` via `argparse`
- Calls the script's public function(s) with resolved arguments
- Calls `sys.exit(0/1)` to signal success or failure
- Contains no business logic
- Every user-supplied path goes through `core.paths.resolve_input` /
  `core.outputs.anchor_user_path` (see "Nothing user-supplied stays relative"),
  which is what lets a bare filename mean "the one in the shared `inputs/`
  directory". Do not hand-roll a `Path.parent == Path(".")` check.
- `ArgumentParser` must always be constructed with:
  - `prog="uv run main.py <theme>.<script>"` — fixes the usage line shown in `--help`
  - `formatter_class=argparse.RawDescriptionHelpFormatter` — preserves epilog formatting
  - `epilog=_EXAMPLES` — a module-level constant with 2–4 concrete example invocations

### Public functions — programmatic API

- Accept typed `Path` / primitive arguments — no argparse, no `sys.exit`
- Raise exceptions on unrecoverable errors (or return a meaningful value)
- Named for what they do (`validate`, `export`, `import_captions`, …)
- Are the unit under test

### Custom UI labels (`ui_label`)

By default the web UI derives form field labels from the flag name
(`--fade-in` → "Fade in"). When the auto-derived label is misleading or
too terse, pass `ui_label` to `add_argument()` to override it:

```python
parser.add_argument("--audio", action="store_true", ui_label="Audio only")
```

`ScriptoriumParser` from `core.argparse` is the mandatory parser for all
scripts. It is a drop-in replacement for the stdlib `ArgumentParser` that
adds `ui_label` and `ui_advanced` support plus the startup arg banner (see
Runner middleware).

### Advanced arguments (`ui_advanced`)

A script with a dozen knobs presents a wall of fields for a job that usually
needs one decision. `ui_advanced=True` moves an argument behind a collapsed
"Advanced options" disclosure in the web form:

```python
parser.add_argument("--alpha-matting", action="store_true", ui_advanced=True)
```

It changes nothing about the CLI — every argument stays equally visible in
`--help`. The fields also stay in the DOM when collapsed, so their defaults
still submit; only visibility changes.

`photo.remove_bg` is the worked example. A `--preset` (`fast`/`balanced`/`hq`)
bundles a model with its edge treatment, and the expert arguments — including
`--model`, `--alpha-matting` and `--post-process-mask`, which only ever add to
what the preset set — sit behind the disclosure. Prefer this shape when a
script has one obvious decision and a long tail: a preset that covers the
common case, with the full controls one click away. `fast` resolves to the
previous default, so no-argument behaviour is unchanged.

The presets are named for cost, not quality, because no model wins on every
image — u2net regularly beats the larger models on some photos. That is also
why `--all-presets` exists: it runs the three in sequence over the same inputs
into the same output location, prefixing each filename with the preset name,
and archives the inputs only after the last pass so every pass can see them.
One failing preset does not stop the others.

Because every model downloads its weights on first use, the script exposes
`models_for_args(args)` and `weights_url(model)`. The detail page calls
`GET /api/model-weights/photo/remove_bg` with the live form state and shows
which weights the run would fetch, with a size from a cached `HEAD` request
when the server can learn one. During the run, `core.downloads` swaps pooch's
tqdm bar for a `ProgressReporter`, so the download drives the status bar like
a transcode does. Any script that loads model weights can opt in by exposing
the same two functions.

### Minimal example

```python
import argparse
import sys
from pathlib import Path

from core.argparse import ScriptoriumParser

TITLE = "Do a thing"
DESCRIPTION = "Does the thing to a file."

_EXAMPLES = """
examples:
  uv run main.py <theme>.do_thing file.txt
  uv run main.py <theme>.do_thing file.txt --verbose
"""


def do_thing(path: Path) -> int:
    ...
    return count


def get_parser() -> argparse.ArgumentParser:
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py <theme>.do_thing",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", type=Path)
    return parser


def run() -> None:
    args = get_parser().parse_args()
    count = do_thing(args.path)
    sys.exit(0 if count > 0 else 1)
```

---

## Runner middleware

All calls through `run()` or `run_fn()` pass through `_timed` in
`core/runner.py`, which does three things: prints the timing banner to stderr
(so it does not pollute captured stdout, e.g. JSON piped to another process),
appends one JSON line per run to `logs/runs.jsonl` (`ts`, `label`,
`duration_s`, `status`), and — only when `SCRIPTORIUM_NOTIFY` is `1`, `true`
or `yes` — sends a Telegram message through `scripts.util.notify`. The last
two never raise; a failure to log or notify must not fail a run.

Every CLI script prints a startup banner before doing any work:

```
[lora.export_captions] started at 22-05-26 14:30
  inputs = inputs/lora
  output = captions.json
[lora.export_captions] done in 0.012s
```

The first line (timestamp) is emitted by `_timed` in `core/runner.py` — the
single bottleneck all execution paths pass through. The resolved-arguments block
is emitted by `ScriptoriumParser.parse_args()` in `core/argparse.py`, which
prints every argument and its resolved value to stderr immediately after parsing.

All scripts must use `ScriptoriumParser` (from `core.argparse`) instead of the
stdlib `ArgumentParser` so they inherit the startup banner automatically.

To add cross-cutting behaviour (logging, metrics, retries, …): edit `_timed` in
`core/runner.py`. It is the single place.

---

## Private helpers

Files whose names start with `_` are ignored by the registry. Use them for shared
constants or functions within a theme:

```
scripts/lora/_dataset.py   # IMAGE_EXTS, find_images(), find_captions()
scripts/av/_utils.py       # MEDIA_EXTS, run_ffmpeg(), av_inputs_dir(), …
```

Two `IMAGE_EXTS` exist on purpose. `scripts/formats/_utils.py`'s is the
canonical "what is an image" set — it feeds `core.categories`, the drop
overlay, `formats.convert_image` and `photo.remove_bg`, and includes HEIC/HEIF.
`scripts/lora/_dataset.py`'s is narrower by design: it lists what a LoRA
trainer will actually consume, and a `.heic` in a dataset is a mistake to
flag, not a file to accept.

Import them with an absolute path:

```python
from scripts.lora._dataset import find_images
```

---

## Checklist for adding a script

1. Create `scripts/<theme>/<script>.py`
2. Define `TITLE`, `DESCRIPTION`, and `run()` at module level
3. Put all logic in one or more typed public functions; `run()` only parses and
   dispatches
4. Add a module-level `_EXAMPLES` string with 2–4 concrete invocations (include
   all positional args so the reader can copy-paste)
5. Define `get_parser() -> ArgumentParser` that constructs and returns the parser
6. Construct the parser inside `get_parser()` using `ScriptoriumParser` (from
   `core.argparse`) with `prog="uv run main.py <theme>.<script>"`,
   `epilog=_EXAMPLES`, and `formatter_class=argparse.RawDescriptionHelpFormatter`;
   `run()` calls `get_parser().parse_args()`
7. Use `core.outputs.resolve_output()` or `core.outputs.resolve_output_dir()` for
   output paths; use `core.paths.inputs_dir("<theme>")` for input defaults; resolve
   bare filenames inside `run()` before passing to public functions
8. If the script processes user-supplied files, add `ACCEPTS: set[str]` with the
   applicable categories (see `core/categories.py`) so it appears in Drop-to-Discover
9. Verify it appears in `uv run main.py`
9. Verify `uv run main.py <theme>` lists the script with its title and description
10. Verify `uv run main.py <theme>.<script> --help` shows the correct usage line,
    arguments, and examples

---

## Checklist for adding a theme

1. Create `scripts/<theme>/` directory
2. Add `scripts/<theme>/__init__.py` with:
   - A module docstring (conventional, not used at runtime)
   - `LABEL = "..."` — display name for the web UI sidebar and CLI listings
   - `DESCRIPTION = "..."` — one-line tagline for the web UI header and `uv run main.py <theme>`
3. No theme-local `inputs/` or `outputs/` directories are needed — every theme
   shares the repo-root `inputs/` and writes to `outputs/<theme>/` automatically
4. Add a `_utils.py` (or equivalent) that delegates to `core.paths.inputs_dir()`
   and `core.paths.outputs_dir()` if the theme's scripts read from or write to
   local files
5. Verify the theme appears in `uv run main.py` (top-level listing)
6. Verify `uv run main.py <theme>` prints the description followed by the script list
7. Verify the theme appears in the web UI sidebar with the correct label and description
