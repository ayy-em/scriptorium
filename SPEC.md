# Scriptorium — Technical Spec

## What this is

A single-entrypoint collection of themed utility scripts. All execution — CLI or
programmatic — goes through `core/runner.py`, which provides a uniform middleware
layer (currently: timing). Scripts themselves stay lean: no cross-cutting logic,
no `sys.exit` outside of `run()`.

---

## Repository layout

```
scriptorium/
├── main.py                  # CLI entrypoint
├── core/
│   ├── registry.py          # auto-discovers scripts
│   └── runner.py            # dispatch + middleware (run, run_fn)
└── scripts/
    └── <theme>/
        ├── __init__.py
        ├── _helpers.py      # private shared code (ignored by registry)
        └── <script>.py      # one script per file
```

`inputs/`, `outputs/`, and `past_inputs/` directories are gitignored everywhere
in the repo and are the conventional locations for local data.

---

## Invocation

### CLI

```sh
uv run main.py                          # list all available scripts
uv run main.py <theme>.<script> [args]  # run a script
```

`uv run` is the only supported CLI invocation — use it on all platforms.

### Programmatic

```python
from scripts.<theme>.<script> import <function>
from core.runner import run_fn

result = run_fn(some_fn, arg1, arg2, kwarg=value)
```

`run_fn` applies the same middleware as the CLI path (timing, future hooks).
Use direct imports only in tests.

---

## Script anatomy

Every file the registry picks up must expose three names at module level:

| Name          | Type       | Purpose                                      |
|---------------|------------|----------------------------------------------|
| `TITLE`       | `str`      | One-line label shown in `uv run main.py`     |
| `DESCRIPTION` | `str`      | Sentence shown in `--help`                   |
| `run()`       | `Callable` | CLI entrypoint — owns argparse + `sys.exit`  |

### `run()` — CLI only

- Parses `sys.argv` via `argparse`
- Calls the script's public function(s) with resolved arguments
- Calls `sys.exit(0/1)` to signal success or failure
- Contains no business logic
- Any file/directory input whose `Path.parent == Path(".")` (bare name, no directory
  component) is resolved to `<theme>/inputs/<name>` before being passed to the
  public function. This lets users type just a filename instead of the full path
  when the file lives in the conventional inputs directory.
- `ArgumentParser` must always be constructed with:
  - `prog="uv run main.py <theme>.<script>"` — fixes the usage line shown in `--help`
  - `formatter_class=argparse.RawDescriptionHelpFormatter` — preserves epilog formatting
  - `epilog=_EXAMPLES` — a module-level constant with 2–4 concrete example invocations

### Public functions — programmatic API

- Accept typed `Path` / primitive arguments — no argparse, no `sys.exit`
- Raise exceptions on unrecoverable errors (or return a meaningful value)
- Named for what they do (`validate`, `export`, `import_captions`, …)
- Are the unit under test

### Minimal example

```python
import argparse
import sys
from pathlib import Path

TITLE = "Do a thing"
DESCRIPTION = "Does the thing to a file."


def do_thing(path: Path) -> int:
    ...
    return count


def run() -> None:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    count = do_thing(args.path)
    sys.exit(0 if count > 0 else 1)
```

---

## Runner middleware

All calls through `run()` or `run_fn()` are timed. Output goes to stderr so it
does not pollute captured stdout (e.g. JSON output piped to another process).

```
[lora.export_captions] 0.012s          # CLI label = script key
[lora.export_captions::export] 0.011s  # programmatic label = module::function
```

To add cross-cutting behaviour (logging, metrics, retries, …): edit `_timed` in
`core/runner.py`. It is the single place.

---

## Private helpers

Files whose names start with `_` are ignored by the registry. Use them for shared
constants or functions within a theme:

```
scripts/lora/_dataset.py   # IMAGE_EXTS, find_images(), find_captions()
```

Import them with a relative or absolute path:

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
5. Construct `ArgumentParser` with `prog="uv run main.py <theme>.<script>"`,
   `epilog=_EXAMPLES`, and `formatter_class=argparse.RawDescriptionHelpFormatter`
6. Verify it appears in `uv run main.py`
7. Verify `uv run main.py <theme> --help` lists the script
8. Verify `uv run main.py <theme>.<script> --help` shows correct usage line and
   examples
