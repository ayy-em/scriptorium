# Backlog

Deferred work with enough context to pick up cold.

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

**Status:** deferred (2026-07-27), same revamp.

`batch_mode_for()` plus the (future) fan-out runner are the first real
"plan a multi-file job" logic in the codebase. Extracting a small `BatchPlan`
value type — *which script runs, against which inputs, producing what* — would
make several queued features much cheaper:

- **Re-run from History** — the sidebar already has a History nav item with no
  backing implementation. A stored `BatchPlan` is exactly the record needed.
- **Job queue** — chaining plans, running them in order.
- **`--dry-run`** — render a plan without executing it, so the UI can preview
  "this will produce 8 files in outputs/av/" before the user commits.

Deliberately not built yet: with only one batch class actually wired up, the
abstraction would have a single implementation and nothing to generalise over.
Revisit once per-file fan-out lands, since that is the second implementation
that gives the shape meaning.
