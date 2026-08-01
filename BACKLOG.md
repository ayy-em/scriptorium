# Backlog

Deferred work with enough context to pick up cold.

Everything above the **Settled** heading is open work. Below it are closed
entries, kept because the reasoning is worth not having to reconstruct.

## Remaining run-lifecycle work

**Status:** partially delivered (2026-07-28). Cancellation, the `RunHandle`
value type, persisted history and re-run all shipped. One item of real work is
left; the rest moved to **Settled** below.

- **Progress reporting.** The status strip's bar is indeterminate because no
  script emits progress. A `RunRecord` is somewhere to put structured progress
  events if scripts ever grow them; ffmpeg's `-progress` output is the obvious
  first source.

## Runtime dependencies need one coherent story

**Status:** open (2026-07-30). Rough note — needs a proper design pass, not
piecemeal fixes.

The `.app` bundles its Python dependencies but not the heavy native ones, and
each missing piece currently fails in its own unrelated way. Nothing states, in
one place, what a clean Mac actually needs. Verified against
`/Applications/Scriptorium.app` (0.5.2):

| Dependency | Bundled? | Needed by | Behaviour when absent |
|---|---|---|---|
| ffmpeg / ffprobe | no | ~15 scripts (`av.*`, `gif.*`, `formats.convert_{audio,video}`) | detected; sidebar banner with an install hint |
| pango / cairo / glib | no | `formats.convert_docs`, `telegram.*` PDF output | Homebrew-only; `scripts/telegram/_runtime.py` patches `cffi.FFI.dlopen` to search `/opt/homebrew/lib` and `/usr/local/lib`. No Homebrew, no PDF |
| rembg model weights | no | `photo.remove_bg` | silent 167–170MB download per model on first use, into `~/.u2net/` |
| `OPENAI_API_KEY` | n/a | `speech.transcribe` | needs `.env`; no equivalent of the ffmpeg banner |

Three things to decide together rather than one at a time:

1. **Bundle or require?** Bundling ffmpeg and the pango/cairo/glib stack makes
   the `.app` genuinely self-contained and removes the Homebrew assumption,
   at a large size cost and real relocation/signing work. Requiring them is
   the status quo and needs honest first-run docs instead.
2. **Uniform detection.** `core.paths.has_ffmpeg()` is the only capability check
   that exists, it is evaluated once at import (`webapp/app.py:68`, so installing
   ffmpeg mid-session does not clear the banner until restart), and nothing
   equivalent covers pango, model weights, or API keys. One mechanism, surfaced
   the same way for every dependency, beats four bespoke failure modes.
3. **First-run cost should be visible.** A 167MB download with no progress and
   no warning is the worst case (see the streaming issue: the tqdm bar goes to
   stderr and is not shown until the run ends). Options: ship the default model,
   pre-fetch on first launch with visible progress, or confirm before download.

Also fix while here: `remove_bg.py:253` claims "Non-default models download
weights on first use". The default `u2net` downloads too — nothing pre-seeds the
cache. And README.md's build table says macOS prerequisites are "None (tools are
auto-installed)", which is true of the *build* (`build.sh` installs uv, Homebrew,
ffmpeg) but not of the shipped `.app` on someone else's Mac; SPEC.md lists build
prerequisites only. Runtime prerequisites are documented nowhere.

## Favourites are per browser profile

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

## Global drop overlay on script detail pages

**Status:** deferred (2026-07-28), during the UI prettification pass.

Drop-to-Discover works on the main screen only. Dragging a file onto a script
detail page does nothing at the window level — the page's own dropzone works,
but there is no app-wide overlay.

The blocker is structural, not cosmetic: the drag handlers, upload staging,
category matching and the radial chooser all live inside the single
`scriptBrowser()` Alpine component that wraps `index.html`. Making the overlay
app-wide means lifting that state into an Alpine store shared with `base.html`,
and deciding what a drop on a detail page should even do — route back to the
wheel on `/`, or prefill the current script's file input if the type matches
(the more useful answer, and the one that needs `ACCEPTS` checked client-side).

## Recent outputs panel

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

## Photos.Remove_bg user friendliness

Args of two types: simple (just select a model by choosing "fast" or "high quality") and advanced (full args like they currently are).

# Settled

Closed, and kept only for the reasoning — either delivered, or considered and
deliberately not built. Nothing here is queued work.

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
