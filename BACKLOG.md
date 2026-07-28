# Backlog

Deferred work with enough context to pick up cold.

## Remaining run-lifecycle work

**Status:** partially delivered (2026-07-28). Cancellation, the `RunHandle`
value type, persisted history and re-run all shipped. What is left:

- **Progress reporting.** The status strip's bar is indeterminate because no
  script emits progress. A `RunRecord` is somewhere to put structured progress
  events if scripts ever grow them; ffmpeg's `-progress` output is the obvious
  first source.
- **Cancel does not clean up partial output.** Deliberate — half a transcode is
  sometimes useful, and deleting a user's file on their behalf is a bigger
  decision than it looks. Revisit only if it becomes annoying in practice.
- **Navigating away mid-run lets the script finish.** Also deliberate: the run
  completes and writes its output. Cancel is the explicit way to stop.
- **History has no search or filter.** Capped at 200 entries, which is scannable
  without pagination. Add filtering if the cap ever needs raising.
- **POSIX `killpg` is unverified on real hardware.** Unit-tested against stubs;
  see HUMAN_TODO.md.

## PNG icon sweep

**Status:** deferred (2026-07-28), scoped out of the UI prettification pass to
keep that change reviewable.

The UI runs two icon systems side by side:

| System | Where | Count | Weight |
|---|---|---|---|
| Inline SVG (`webapp/templates/_icons.html`) | settings modal, terminal, run controls, status strip, empty states | ~40 | negligible |
| PNG (`webapp/static/icons/`) | theme icons in `_macros.html`, sidebar categories, top bar, drop chooser | 20 | ~2.4MB |

The PNGs are the problem: several exceed 250KB each, they cannot take
`currentColor` so hover and active states can't tint them, and dark mode fakes
it with `filter: invert(1)` (see `html.dark .sidebar-github-logo` and
`html.dark .settings-link-icon`). The sidebar's "category icons go purple when
active" rule is written and works — but only for the themes already on inline
SVG.

**What to do:** extend `_icons.html` to cover the theme and category glyphs,
replace the `<img>` branches in `_macros.html`, convert `webapp/_icons.py` to
return icon *names* rather than `/static/...` URLs, and delete
`webapp/static/icons/*.png` plus `webapp/static/img/github.png`.

**Watch out for:**

- `webapp/_icons.py` feeds `/api/drop-upload`'s JSON (`icon`, `category_icon`).
  Changing it to names is an API shape change — `tests/webapp/test_drop.py`
  asserts on it.
- `packaging/entrypoint.py::_load_tray_icon()` loads `icon-night.png` and needs
  a raster. Repoint it at a logo PNG before deleting the icons directory.
- Icon licensing is unresolved — see HUMAN_TODO.md, which must be settled first.

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
