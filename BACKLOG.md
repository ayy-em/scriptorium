# Backlog

Deferred work with enough context to pick up cold.

Everything above the **Settled** heading is open work. Below it are closed
entries, kept because the reasoning is worth not having to reconstruct.

## Runtime dependencies: bundle ffmpeg

**Status:** open (2026-08-04), decision made, not yet built. The detection half
of the original entry is delivered — see "Runtime dependencies needed one
coherent story" under Settled for the reasoning and the corrected dependency
table.

**Decided:** bundle a **GPL** ffmpeg build and comply, rather than LGPL.

The usual way to avoid GPL obligations is an LGPL build, and it does not work
here: LGPL ffmpeg ships without libx264/libx265, and `formats.convert_video`
encodes H.264 by default — `--quality max` is documented as "CRF 0, lossless
H.264". An LGPL build cannot do that. openh264 is not a clean swap either; it is
a different encoder with different quality behaviour.

So the obligations are real, because releases are published on GitHub:

- Ship ffmpeg's licence text inside the bundle.
- Provide a source offer for the exact build shipped.
- See HUMAN_TODO.md — this needs a human decision, not an agent's.

**What to build:**

1. Fetch a **shared** GPL build per platform at build time, not a static one.
   The static Windows pair measured **370MB** (185MB each, everything embedded
   twice) against a current `dist/` of 657MB. Shared builds put the codecs in
   DLLs both executables share. The saving is expected but **unverified** —
   measure before committing to it.
2. Add the binaries to `binaries=` in all three specs.
3. Resolve them at runtime. Every invocation goes through
   `scripts/av/_utils.py` (`run_ffmpeg`, `run_ffmpeg_with_progress`,
   `run_ffmpeg_stderr`, `run_ffprobe`), which currently spawns the bare name
   `"ffmpeg"` and relies on PATH. That is the one chokepoint to change —
   prefer the bundled binary, fall back to PATH.
4. `core.capabilities`' `ffmpeg` probe must then check the bundled location
   too, or the banner will claim ffmpeg is missing inside a bundle that
   contains it.

**Note:** `gif.make_gif` is *not* affected. It assembles frames with Pillow; the
original entry listing `gif.*` as an ffmpeg consumer was wrong.

## Visible first-run cost for rembg model weights

**Status:** open (2026-08-04), decided and designed, not built.

**Decided:** do *not* bundle model weights — they are per-option, and
`birefnet-general` alone is ~950MB. Instead tell the user before the download
starts and show progress while it runs.

The groundwork is done: `core.capabilities.model_weights_present(model)` answers
"will selecting this model trigger a download" without importing rembg, so a
form can warn *before* the run rather than after.

**How the progress part works** — verified against the installed sources, not
assumed:

- rembg fetches weights with `pooch.retrieve(..., progressbar=True)` in each
  session class's `download_models()`.
- pooch accepts a **custom** progressbar object instead of `True`: anything with
  `.total` (settable), `.update(n)`, `.reset()` and `.close()`
  (`pooch/downloaders.py`, the `elif self.progressbar:` branch). tqdm's default
  writes to stderr, which is why the existing bar is invisible until the run
  ends.
- So a ~15-line adapter over `core.progress.ProgressReporter` makes the download
  drive the same status bar transcodes already use.
- rembg hardcodes `progressbar=True`, so this needs a contained wrap of
  `pooch.retrieve`. Precedent: `core/native_libs.py` patches `cffi.FFI.dlopen`.

**One open question:** where the size in the warning comes from. A `HEAD` request
to the model's release URL is accurate and self-maintaining but means the form
page makes an outbound request; a hardcoded table is offline but goes stale.
Leaning `HEAD`, cached, with no number shown on failure.

## Bundle the pango/cairo/glib stack

**Status:** open (2026-08-04). Deliberately deferred in favour of detection.

Detection shipped instead: a missing pango stack is now named in the sidebar with
a per-platform install command, and only the two Telegram scripts that render
PDFs are affected. That is enough that PDF output no longer fails with a raw
`OSError` from inside cffi.

Bundling it properly would make PDF output work on a machine with neither
Homebrew nor MSYS2. It is the most painful of the native dependencies:

- Three separate stacks to lay out — Homebrew dylibs, MSYS2/UCRT DLLs, Linux
  shared objects — each with its own transitive graph (pango → harfbuzz →
  freetype → fontconfig → glib → cairo → pixman …).
- macOS dylibs need relocating and re-signing after being moved into the bundle,
  or Gatekeeper rejects them.
- `core/native_libs.py` already has the runtime half: it prepends
  `sys._MEIPASS/lib` to the cffi dlopen fallback search path, so bundled libs
  are found first. The missing part is purely build-time layout.

Worth doing if the app is ever handed to someone who will not install anything.
Not worth it while the audience is one person with Homebrew and MSYS2 already
installed.

# Settled

Closed, and kept only for the reasoning — either delivered, or considered and
deliberately not built. Nothing here is queued work.

## Runtime dependencies needed one coherent story

**Status:** the detection half resolved 2026-08-04. Bundling and the model
download UX are the two open entries above; this covers what was learned and what
the original table got wrong.

`core/capabilities.py` replaces the bespoke checks with one value type — see
SPEC.md "`core.capabilities`". The old `core.paths.has_ffmpeg()` is gone.

**The original table was wrong in four ways**, all found by probing rather than
reading:

| Claim | Reality |
|---|---|
| four dependencies | **seven**. `pandoc` is a hard requirement of `formats.convert_docs` and was not listed at all; `gifsicle` and the weasyprint CLI are optional ones nothing tracked |
| `gif.*` needs ffmpeg | it does not — `make_gif` assembles frames with Pillow and shells out to nothing |
| `pango` is needed by `formats.convert_docs` | `convert_docs` needs **pandoc**, and uses the weasyprint *CLI* only to improve PDFs. The pango *library* is needed by `telegram.{chat,group}_analysis`, which import weasyprint in-process |
| Homebrew-only, "no Homebrew, no PDF" | `core/native_libs.py` already handled Windows/MSYS2 as well as Homebrew. A bare `import weasyprint` fails on Windows, but the patched import the app actually performs succeeds |

That last one is worth dwelling on: **testing a dependency the way the app does
not use it produced a confident, wrong answer.** The pango probe imports
weasyprint for real, after applying the dlopen patch, precisely because
guessing at library filenames or checking an unpatched import both lie.

**Two bugs the pass surfaced**, neither of them the stated task:

- The `openai-key` probe reported a false negative unless `core.env.load_env()`
  had already run. The webapp does it at import; a CLI caller does not. The probe
  now loads `.env` itself — a probe whose answer depends on who called first is
  worse than no probe.
- Binding `capabilities.missing` straight into `templates.env.globals` captures
  the function object at import. That is the *same* early-binding mistake that
  made the old ffmpeg banner need a restart, hidden one level down, and it
  silently defeated the fix — the tests only caught it because patching the
  module attribute had no effect. The globals are named wrappers now.

**Deliberately not merged:** `webapp/_badges.py` keeps its own tool map. It
answers "what does this script drive" — including yt-dlp, which ships in the
bundle and is therefore never missing. Forcing an always-present tool into a
"might be absent" registry would be worse than two three-line maps.

## Global drop overlay on script detail pages

**Status:** resolved 2026-08-03. A drop anywhere on a detail page now prefills
that script's file input. See SPEC.md "Drop targets".

**The stated blocker turned out not to be one.** The original note assumed the
overlay needed `scriptBrowser`'s state — drag handlers, upload staging, category
matching, the radial chooser — lifted into an Alpine store shared with
`base.html`. That is true only for the *other* option, routing a detail-page drop
back to the wheel on `/`. Once the chosen behaviour is "prefill this script's
input", the target script is already known, and every one of those pieces exists
to answer a question that is no longer being asked. What was actually needed:
window-level drag handlers on `scriptRunner`, an extension check, and a call into
the `_send()` the form's own dropzone already used. No store, no lifting.

Worth remembering as a pattern: the blocker was real for the design in the note,
and evaporated when the product decision changed. Re-derive the blocker after
settling behaviour, not before.

What the shared `_drop_hint.html` macros do and do not cover: the hint overlay
and the rejection toast are genuinely identical between the two pages, so they
are macros taking an Alpine expression. The upload spinner stayed in
`_drop_overlay.html` — the detail page's dropzone reports upload state inline,
and a full-screen spinner over it would be a regression.

Two things deliberately left:

- **`scripts/av/trim.html` has no window-level drop.** It overrides the template
  with its own `trimApp` component, so it shares none of `scriptRunner`. Fixing
  it means porting that component, which is the "Unify the trim.html console"
  entry below — not worth a second copy of this logic in the meantime.
- **The client-side decision logic has no committed test.** The repo is
  pytest-only and a JS harness is a dependency decision, not a drive-by. The
  server-rendered seams are covered in `TestWindowLevelDrop`
  (`tests/webapp/test_serve.py`): handlers present, accept list correct per
  script, `.stop` on the form dropzone, browser overlay unaffected by the macro
  extraction.

Two fixes fell out of the same pass, both unrelated to drops:

- `script.html` passed `recentUrl` in its markup but never read it into the
  component, so `_loadRecentOutputs` fetched `undefined` and the Recent outputs
  panel was **always empty** since it shipped in `d1526f1`. Guarded by
  `test_recent_outputs_url_is_read_into_the_component`.
- A multi-file drop on a single-file input silently kept the first file and
  discarded the rest, which looks like the drop worked. `_send` now refuses it
  and says so. Only a drop could cause this; the OS picker cannot.

## Remaining run-lifecycle work

**Status:** resolved 2026-08-03. Cancellation, the `RunHandle` value type,
persisted history and re-run shipped 2026-07-28; progress reporting was the last
open item and is now delivered. See SPEC.md "Progress reporting" for the
contract as built.

The original note guessed that `RunRecord` was "somewhere to put structured
progress events". It was the wrong home. A `RunRecord` is written **once, when a
run ends** — it is the historical record of a finished invocation, and history is
deliberately free of live process state. Progress is the opposite: many events
during a run, interesting only while it is in flight, worthless afterwards.
Nothing persists it, and nothing should.

What it needed instead was a channel, and the only channel a subprocess has is
its own stdout — so a `::progress::` sentinel line, pulled out of the stream by
`_stream_script` and re-emitted as `event: progress`.

Three things worth knowing for whoever touches this next:

- **A sentinel convention was rejected for output detection** (see "Recent
  outputs panel" below) because a stdout heuristic covered every script without
  touching any. That reasoning does not transfer. There is nothing to infer
  progress *from* — a script that does not say how far along it is simply is not
  observable — so here the convention is the mechanism.
- **Two axes, never mixed.** For one long ffmpeg pass, position within the
  output. For many short calls (`av.split`, `av.filmstrip`, `av.join`), calls
  completed. Using ffmpeg's own progress for the second kind sends the bar
  backwards at every file boundary, because each call reports against a
  different total.
- **Throttling belongs to the producer.** ffmpeg reports ~2/second; an
  hour-long run would otherwise put thousands of messages on the stream to say
  what a half-second-stale bar already says.

Deliberately not built: nothing consumes progress except the live UI. No
per-run progress history, no ETA extrapolation from observed rate, no
aggregate bar across a fan-out beyond the "File 3 of 8" counter that already
existed. Each wants a design decision that nothing currently demands.

## Cancel does not clean up partial output

Half a transcode is sometimes useful, and deleting a user's file on their behalf
is a bigger decision than it looks. Revisit only if it becomes annoying in
practice.

## Navigating away mid-run lets the script finish

The run completes and writes its output. Cancel is the explicit way to stop one.

## History has no search or filter

Capped at 200 entries, which is scannable without pagination. Add filtering if
the cap ever needs raising.

## macOS: no tray icon in the Chromium fallback tier

**Status:** open (2026-07-29). Deliberately skipped, not broken.

`Icon.run()` in pystray's macOS backend calls `-[NSApplication run]`, and AppKit
aborts the process with SIGTRAP ("NSUpdateCycleInitialize() is called off the
main thread") if that happens on any thread but the main one. A signal is not an
exception, so no `try`/`except` in `_start_gui` can contain it — the app dies
outright.

Tier 1 is fine: `_create_tray_icon` passes `detached=True` on macOS, so
`run_detached()` attaches the status item to the shared `NSApplication` that
`webview.start()` then runs. Both libraries use
`NSApplication.sharedApplication()`, so one loop drives both.

Tier 2 has no GUI main loop at all — it waits on a browser process — so there is
nothing to service an `NSStatusItem`. `_chromium_app_window` skips the tray on
macOS and logs why, which means `close_behavior = "tray"` is inert there. If a
Mac user ever lands in tier 2 (no working WebKit window) and wants the setting,
the fix is to run an `NSApplication` loop on the main thread and wait on the
browser process from a background thread instead.

## Unify the trim.html console

**Status:** deferred (2026-07-28), during the UI prettification pass.

`scripts/av/trim.html` is a hand-written template with its own ~600 lines of
vanilla JS, streaming into `#output` / `#run-result` rather than the new
`_terminal.html` component. It was restyled to match — same dark panel, mono
font and status colours — but it has no header row, no Live indicator, no
timestamps, no Clear, no collapse and no "Jump to latest".

Unifying means porting its waveform editor onto the `scriptRunner()` Alpine
component in `script.html`. Worth doing when that file is next opened for
another reason; not worth a dedicated pass.

The gap widened on 2026-08-03: `scriptRunner` gained progress reporting and a
window-level drop target, and `trimApp` has neither. So `av.trim` alone has an
indeterminate bar and a detail page where a drop outside the dropzone does
nothing. Both come free with the port; neither justifies reimplementing in
`trimApp`.

## BatchPlan abstraction

**Status:** deferred (2026-07-27), same revamp. Partly superseded 2026-07-28.

`batch_mode_for()` plus the (future) fan-out runner are the first real
"plan a multi-file job" logic in the codebase. Extracting a small `BatchPlan`
value type — *which script runs, against which inputs, producing what* — would
make several queued features much cheaper:

- ~~**Re-run from History**~~ — delivered. `core.history.RunRecord` is the
  single-invocation version of this shape: script key, argv, params, outcome.
- **Job queue** — chaining plans, running them in order.
- **`--dry-run`** — render a plan without executing it, so the UI can preview
  "this will produce 8 files in outputs/av/" before the user commits.

`RunRecord` describes *one* invocation; a batch is *N invocations over a file
set*. The cheapest bridge is an optional `batch_id` on `RunRecord`, letting
per-file fan-out group its runs without a second type — worth deciding when
fan-out is actually built rather than speculatively now.

**Decided 2026-08-02, when fan-out landed:** `batch_id` was the whole of it. No
`BatchPlan` type was needed. The fan-out loop is a dozen lines of client-side
sequencing over a list of paths, and a value type describing "which script,
which inputs, what output" would have had nothing to generalise over that the
existing `RunRecord` plus a shared id does not already cover. Revisit only if a
job queue or `--dry-run` is actually wanted; both still want a plan object, and
neither exists.

Deliberately not built yet: with only one batch class actually wired up, the
abstraction would have a single implementation and nothing to generalise over.
Revisit once per-file fan-out lands, since that is the second implementation
that gives the shape meaning.

## CLI invocations should honour the current directory

**Status:** delivered 2026-08-01. Kept for the reasoning; see SPEC.md
"Relative paths depend on who is calling" for the rule as shipped.

`core/invocation.py` marks webapp-spawned runs with
`SCRIPTORIUM_CALLER=webapp`; `core.paths.resolve_input` and the defaults in
`core/outputs.py` read it. The 18 hand-written redirects are gone.

Two departures from the sketch below. The marker is an **environment variable,
not `--run-script`** — that flag only exists on the frozen path, and a
development run is `python main.py <key>`, argv-identical to what a human types.
And **a missing source argument still means `inputs/` for both callers**:
`scriptorium photo.remove_bg` with no arguments meaning "every image in my cwd"
is destructive in a way an explicit path is not.

Original write-up follows.

---

**Status:** open (2026-07-30). Reported from real use on macOS after the frozen
app was put on `PATH`.

Not a macOS issue despite where it surfaced — the behaviour is identical for the
Linux binary and `scriptorium.exe` on Windows. Do not implement it as a
`sys.platform == "darwin"` special case.

**What happens.** With the binary symlinked onto `PATH`
(`~/.local/bin/scriptorium` → `Scriptorium.app/Contents/MacOS/scriptorium`),
running it from an arbitrary directory does not behave like a normal CLI tool:

```sh
cd ~/Movies/holiday
scriptorium av.trim thing.mp4 00:12 01:07
# error: ffmpeg ... exit status 254
#   because it looked for ~/scriptorium/inputs/thing.mp4
```

Two separate causes:

1. **Relative inputs are redirected.** 18 scripts contain some spelling of

   ```python
   if source.parent == Path("."):
       source = <theme>_inputs_dir() / source.name
   ```

   so a bare filename resolves against `~/scriptorium/inputs/<theme>/`, not the
   cwd. `./thing.mp4` does not escape it either — `Path("./thing.mp4").parent`
   is also `Path(".")`. The failure surfaces as a raw ffmpeg exit code, with the
   substituted path visible only inside the quoted command.

2. **Outputs ignore the cwd.** `resolve_output`, `resolve_output_dir` and
   `resolve_single_output` in `core/outputs.py` default to
   `outputs_dir(theme)` — `~/scriptorium/outputs/<theme>/` when frozen. Writing
   next to the input requires an explicit `--output "$PWD/clip.mp4"`.

Both are *correct for the web UI*, which uploads into the inputs dir and shows
results from the outputs dir. Neither is correct for a human in a terminal. The
two callers are currently indistinguishable at the point of resolution.

**Suggested approach.** `--run-script` is already the marker for "the webapp
spawned this" (`webapp/app.py`, frozen branch) and is stripped by
`entrypoint.main` before dispatch. Turn that into an explicit mode — an env var
or a module-level flag set in that branch — and have both resolvers consult it:

| Caller | Relative input | Default output |
|---|---|---|
| webapp (`--run-script`) | `inputs_dir(theme)` — unchanged | `outputs_dir(theme)` — unchanged |
| human CLI | cwd | cwd |

Do not key this off `_wants_cli()`: it answers a different question (should this
process show a window) and is deliberately blind to who the caller is.

**Scope.** 18 script modules, the three resolvers in `core/outputs.py`, and
their tests. Worth one pass rather than script-by-script drift — and worth a
shared helper, since 18 hand-written copies of the same `parent == Path(".")`
check is how the inconsistency arose. Document the final rule in SPEC.md and the
`PATH` setup itself in README.md, which currently only covers double-clicking.

## pywebview cannot start in the frozen Windows app

**Status:** resolved 2026-08-01 by dropping tier 1 on Windows (option 2 below).

`_load_webview` returns `None` on `win32` without importing anything, and
`scriptorium-win.spec` excludes `webview`, `clr`, `clr_loader` and `pythonnet`
rather than bundling them. Chromium `--app` is the supported tier there — it
already worked, already had the tray, and needs no .NET. What this removes: a
guaranteed-failing import, a stack trace in every launch log, and the pythonnet
stack from the bundle. What it costs: Edge or Chrome must be present, which was
already true in practice since tier 1 never once started.

Original write-up follows.

---

**Status:** open (2026-07-28). Worked around, not fixed.

`ScriptoriumApp.exe` never gets a native window. pywebview's WinForms backend
imports `clr`, which raises:

```
RuntimeError: Failed to initialize Python.Runtime.dll
```

so `_start_gui` silently falls through to tier 2, the Chromium `--app` window.
Bundling `clr_loader` and `pythonnet` via `collect_all` (both *are* in the
bundle now — verified) is **not** sufficient: pythonnet also needs its managed
`Python.Runtime.dll` assembly and a .NET runtime config that `clr_loader` can
resolve at runtime, and PyInstaller does not lay those out correctly on its own.

**Consequence, now mitigated:** the tray only existed in the pywebview tier, so
"minimize to tray" did nothing for every real user. Tier 2 now creates its own
tray icon and reopens the window on demand, so the setting is honoured either
way — see `_chromium_app_window` in `packaging/entrypoint.py`.

That mitigation briefly made the failure visible: tier 1 creates its icon
*before* `webview.start()`, because the closing handler needs it, and the error
path did not take it down again — so on Windows every launch showed two tray
icons, the first wired to a window that never opened. `_start_gui` now stops the
tier-1 icon before falling through (`_stop_tray`), guarded by
`TestTrayIconIsNotLeakedBetweenTiers`. This only ever reproduced where
`webview.start()` fails, i.e. the frozen Windows build.

**Options, if a native window is wanted:**

1. Lay out `Python.Runtime.dll` plus a `runtimeconfig.json` by hand in the spec
   and point `clr_loader` at it. Fiddly and version-sensitive.
2. Drop pywebview on Windows and treat the Chromium tier as *the* supported
   path. It already works, has the tray, and needs no .NET at all — the main
   loss is that Edge/Chrome must be present.
3. Replace pywebview with a WebView2-native wrapper that does not go through
   pythonnet.

Option 2 is the cheapest and closest to how the app actually behaves today.

## Favourites are per browser profile

**Status:** resolved 2026-08-01. Favourites and sort order moved into
`UserConfig`, so all three launch tiers share one set.

`base.html` seeds `window.__PREFS__` from a per-render Jinja global rather than
fetching, so the first paint already has the right stars, and each toggle POSTs
to `/api/preferences`. Anything a previous version left in `localStorage` is
lifted once on load and then removed — only when the server has nothing yet, so
it cannot resurrect favourites the user has since unstarred.

Two things worth knowing for the next person in this file. `post_settings`
rebuilds `UserConfig` from the request body, so it now explicitly carries
favourites and sort order over; without that, saving the settings modal wiped
them (`test_saving_settings_does_not_wipe_favourites`). And `config.json` is
user-editable, so `clean_favourites`/`clean_sort_order` validate on the way in.

`theme` still also lives in `localStorage` — the inline anti-flash script runs
before Alpine and cannot wait for a fetch. That duplication is deliberate.

Original write-up follows.

---

**Status:** known limitation, accepted 2026-07-28 when favourites shipped.

Favourites and sort order live in `localStorage`, so they belong to whichever
browser profile is running the UI. The packaged app has three launch tiers and
they do not share storage:

| Tier | Storage |
|---|---|
| pywebview (WebView2 / WebKit) | its own profile |
| Chromium `--app` | `~/scriptorium/.browser-profile` |
| default-browser fallback | the user's normal browser profile |

So a user who normally opens the desktop app but occasionally hits
`localhost:8000` in Chrome will see two different sets of favourites. Clearing
browser data also wipes them.

**The fix if this becomes annoying:** move them into `UserConfig`
(`core/config.py`) alongside `theme`, `outputs_dir` and `close_behavior`, which
is server-side and therefore shared across every tier. That means a
`favourites: list[str]` field, a POST on each toggle, and the favourites page
could then filter server-side instead of client-side. Roughly an hour's work;
deliberately not done up front because localStorage needed no backend at all.

## Photos.Remove_bg user friendliness

**Status:** resolved 2026-08-02.

`--quality {fast,balanced,best}` is the whole basic form now, alongside source
and output. The ten expert arguments — `--model` among them, as an override —
sit behind a collapsed "Advanced options" disclosure.

The mechanism is general, not a remove_bg special case: `ui_advanced=True` on
`ScriptoriumParser.add_argument` marks any argument as expert-level, and
`_script_form.html` splits the grid on it. Nothing changes for the CLI.

`balanced` maps to `u2net`, the previous default, so a no-argument run behaves
exactly as before. The presets deliberately skip `birefnet-general`: at ~950MB
it is not something a one-click preset should start downloading. Someone who
wants it can still ask for it by name.

Original note follows.

---

Args of two types: simple (just select a model by choosing "fast" or "high quality") and advanced (full args like they currently are).

## Recent outputs panel

**Status:** resolved 2026-08-02 with option 1, the server-side heuristic.

`core.outputs.find_reported_outputs` reads a run's stdout and keeps whatever
turns out to be a real file inside the outputs root. Two candidates per line:
the whole line, which covers `print(path)` including paths with spaces in them,
and each whitespace-separated token, which covers a path inside a sentence.
Anything outside the root is dropped, so a script echoing its input is not
credited with having written it.

Results are stored on `RunRecord.outputs`, so the script page shows both what
the run just produced and what earlier runs of the same script left behind.
Files deleted since the run are filtered out on read.

Notes for whoever picks this up next:

- Only successful runs are credited. A cancelled transcode leaves a truncated
  file, and offering that as a result is worse than showing nothing.
- Detection reads raw stdout, collected before HTML escaping — a path with an
  ampersand in it stops being a path once escaped.
- `/api/reveal-output` re-checks containment against the outputs root. Detection
  only ever produces in-tree paths, but the endpoint is reachable directly.

Option 2, the `::output::` convention, was not built and is not needed: the
heuristic covers every script that prints anything, and one that prints nothing
simply reports nothing rather than being wrong.

Original write-up follows.

---

**Status:** deferred (2026-07-28), during the UI prettification pass.

A "last few outputs, with timestamps and an open action" panel for the script
page's context column. Run history now exists (`core.history`), so the only
missing half is output detection.

**Output detection is the harder half.** Scripts report what they wrote
inconsistently — `av.filmstrip` does `print(out)`, `gif.make_gif` does
`print(f"wrote {result}")`, others say nothing. The script page currently
sidesteps this: on success it offers "Open outputs folder" and states plainly
that individual files are not detected. Options, cheapest first:

1. Server-side heuristic — scan stdout for paths under `outputs_root()` and
   `stat()` the ones that exist. No script changes, ~90% accurate.
2. A convention, e.g. a final `::output::<path>` line the runner middleware
   understands. Accurate, but touches all 27 scripts.

## Per-file batch fan-out

**Status:** resolved 2026-08-02.

Every script now accepts a batch. Directory-native ones still take the whole
drop session in one invocation; single-file ones are run once per file,
sequentially, by a loop in `scriptBrowser.startRun()`. The dimmed "Single file
only" card is gone — a card now says how many times it will run instead.

The three open decisions, settled:

- **A mid-batch failure does not stop the rest.** All files are attempted and
  the result reads "3 of 4 succeeded, 1 failed". One corrupt file should not
  cost you the other seven.
- **Outputs go to the normal theme directory**, relying on the existing
  `_001`..`_999` collision avoidance rather than a per-batch subdirectory.
  Consistent with a single run, and the Recent outputs panel lists them all.
- **Cancel stops between files, not mid-file.** The in-flight invocation is
  allowed to finish and write its output; the rest are skipped. Nothing is left
  half-written, which killing the process mid-transcode would guarantee.

`RunRecord.batch_id` groups the records of one fan-out. It is passed as a
`_batch_id` query param, which the run endpoint pops before `build_argv` — left
in place it would reach the record's params and then a re-run's prefilled form.

Original write-up follows.

---

**Status:** deferred (2026-07-27), during the Drop-to-Discover wheel revamp.

When a batch of files is dropped on the main screen, only *directory-native*
scripts can act on it today. Scripts that take a single file are shown on the
wheel but dimmed, with a "single file only" hint.

The two classes are derived at runtime by `webapp._form.batch_mode_for()`:

| Class | Detection | Batch behaviour | Scripts |
|---|---|---|---|
| `directory` | file input has widget `file-multi`, or `dest == "inputs"` | one invocation against the drop session directory | `av.join`, `formats.convert_{audio,video,image,docs,tabular}`, `photo.remove_bg` |
| `per_file` | file input has widget `file` | **not yet implemented** | `av.{trim,volume,split,tag,dump_frames,filmstrip,to_anim,video_crop}`, `gif.make_gif`, `speech.transcribe` |

**What to build:** run the script once per file in the batch, sequentially,
reporting combined progress. The client already talks to the SSE endpoint at
`GET /scripts/{theme}/{script_name}/run`, so the cheapest version is a
client-side loop issuing N sequential requests and concatenating the streams.

**Decisions still open:**

- Should a mid-batch failure abort the remaining files or continue and report a
  summary? (Leaning: continue, then report `N succeeded / M failed`.)
- Where do outputs land — one directory per batch, or the normal per-theme
  outputs directory with deduplicated names? Note commit `ef580a7` already
  addressed output contamination for multi-file uploads; reuse that approach.
- Should the UI expose a cancel control that stops after the in-flight file?

**Where to start:** `webapp/templates/index.html` (the `runScript` path in the
Alpine component) and `webapp/_form.py` (`batch_mode_for`). Removing the dimmed
state means deleting the `is_disabled` branch in `_drop_chooser.html`.
