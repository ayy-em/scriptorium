---
name: New Script
about: Feature request template for a new script to be added
title: "New Script: "
labels: ["new script"]
assignees: "ayy-em"
---

## Short Summary

<!-- Quick description of what the script does and the user problem it solves. -->

## Script Details

### Category

- Existing category: `api` / `av` / `downloads` / `formats` / `homeassistant` / `llm` / `lora` / `photo` / `printing` / `speech` / `tabular` / `web` / other: <!-- choose one -->
- New category needed: yes / no
- New category name: <!-- required if this creates a new scripts/<category>/ package -->
- New category label: <!-- value for LABEL in scripts/<category>/__init__.py -->
- New category description: <!-- value for DESCRIPTION in scripts/<category>/__init__.py -->

### Script Identity

- Script key: `<category>.<script_name>`
- File path: `scripts/<category>/<script_name>.py`
- Script name / title: <!-- value for TITLE; shown in CLI and web UI listings -->
- Help description: <!-- value for DESCRIPTION; shown in --help and theme listings -->
- Primary public function name: <!-- e.g. convert, trim, download -->
- Expected output: <!-- file(s), stdout, metadata, side effects, etc. -->

### Required Arguments

<!-- Positional args and required flags only. Use Path for file/folder inputs so the frontend can render uploads when appropriate. -->

| Argument | Positional or flag | Expected value / validation | Input or output? | UI label | Notes |
| --- | --- | --- | --- | --- | --- |
| `source` | positional | Existing file path or directory path | Input | Source file/folder | Bare filenames should resolve from `scripts/<category>/inputs/` when applicable. |

### CLI Arguments and Options

<!-- Include all optional flags, even if they have defaults. Mention argparse choices/ranges clearly. -->

| CLI argument | Expected values | Default | Required? | UI label | Help text |
| --- | --- | --- | --- | --- | --- |
| `--example` | integer in `0-100` range | `50` | No | Example value | Describe what this option controls. |

### CLI Help and Examples

<!-- `get_parser()` should use prog="uv run main.py <category>.<script_name>", argparse.RawDescriptionHelpFormatter, and a module-level _EXAMPLES string. -->

```sh
uv run main.py <category>.<script_name> --help
uv run main.py <category>.<script_name> input.ext --example 50
```

### Inputs, Outputs and Frontend Behavior

- Input source(s): <!-- upload, existing file, directory, URL, stdin, etc. -->
- Output location: <!-- default should use core.paths.outputs_dir("<category>") or theme helper when applicable -->
- Bare filename handling: <!-- explain which args resolve from inputs_dir("<category>") -->
- Frontend form behavior: <!-- file upload fields, select choices, textarea for nargs, checkbox flags, etc. -->
- Expected stdout/stderr and exit behavior: <!-- what prints on success/failure; exit 0/1 rules -->

### Dependencies and Platform Requirements

- New Python dependencies needed: yes / no
- Dependency group / optional extra: <!-- update pyproject.toml if needed -->
- External tools needed: <!-- e.g. ffmpeg, ffprobe, platform-specific binaries -->
- macOS requirements: <!-- installation/bundling/docs expectations -->
- Windows requirements: <!-- installation/bundling/docs expectations -->
- Packaging updates needed: <!-- include hidden imports in packaging/scriptorium.spec and packaging/scriptorium-win.spec if needed -->

## Risks, Limitations and Corner Cases

<!-- List expected edge cases, failure modes, validation rules and known limitations. -->

- <!-- Unsupported input formats, huge files, empty directories, missing external tools, duplicate outputs, invalid ranges, network failures, partial batch failures, permissions, overwrites, etc. -->

## Implementation Notes

- Put business logic in typed public function(s); keep `run()` limited to parsing, path resolution, dispatch and `sys.exit`.
- Expose `TITLE`, `DESCRIPTION`, `run()` and, unless there is a strong reason not to, `get_parser()`.
- Use `core.paths.inputs_dir()` / `core.paths.outputs_dir()` or existing theme helpers for conventional paths.
- Add private shared helpers under `scripts/<category>/_*.py` only when more than one script needs them.
- Keep tests focused on public functions and CLI/frontend argument behavior; mock external tools and network calls.

## Acceptance Criteria

- [ ] Script is added under `scripts/<category>/<script_name>.py` and appears in `uv run main.py`.
- [ ] Script works via CLI: `uv run main.py <category>.<script_name> [args]`.
- [ ] `uv run main.py <category>` lists the script with the correct title and description.
- [ ] `uv run main.py <category>.<script_name> --help` includes all relevant args/flags, expected types or choices, defaults and copy-pasteable invocation examples.
- [ ] Script works in the frontend, including generated form fields, uploads, submitted args and streamed output.
- [ ] All new functionality is covered by tests under `tests/<category>/` and/or `tests/webapp/` where relevant.
- [ ] New dependencies, optional extras or dependency groups are reflected in `pyproject.toml`.
- [ ] New platform prerequisites or bundled tools needed on macOS or Windows are handled in the build/dist scripts and documented.
- [ ] Packaging specs include the new script/module and any lazily imported libraries needed for frozen builds.
- [ ] `SPEC.md` and `README.md` are updated to reflect the new functionality.
- [ ] `uv run ruff format .` succeeds.
- [ ] `uv run ruff check --fix` succeeds.
- [ ] `uv run pytest -q` succeeds.
- [ ] Commit message references this issue.
- [ ] After implementing and verifying the feature, a short recap comment is added to this issue before closing it, covering the solution design and key implementation details.
- [ ] If the Future Enhancements section contains any items, a follow-up issue titled `new_script: Enhancements post-MVP implementation` is created.

## Future Enhancements / Post-MVP Ideas

<!-- Optional: list useful improvements intentionally left out of this issue. -->

- <!-- Enhancement idea, why it is out of scope, and any dependency on the MVP implementation. -->

If this section contains any items, creating a follow-up issue titled `new_script: Enhancements post-MVP implementation` is part of the acceptance criteria for completing this task.
