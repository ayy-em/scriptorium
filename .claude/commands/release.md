# Release Workflow

Cut a new release of Scriptorium. Argument: optional version override (e.g. `1.0.0`).
Default: bump the minor version (`M.N.L` → `M.N+1.0`).

**Important**: Use `cmd.exe` for all shell commands (per terminal rules). Run each
step sequentially — do not skip or reorder. Pause and ask for confirmation at every
step marked with **[REVIEW]**.

**The release is published by CI, not by you.** `.github/workflows/release.yml`
triggers on any `v*` tag, builds macOS, Windows and Linux, and publishes the
GitHub Release with all three artifacts attached. Pushing the tag in Step 11 is
what ships the release. Never run `gh release create` — it races the workflow,
and when its own asset upload fails it deletes the release it was pointed at,
taking CI's artifacts with it. That is how the v0.5.3 release was destroyed and
had to be rebuilt from a workflow re-run.

---

## Step 1 — Pre-flight checks

1. Ensure the working tree is clean (`git status`). If there are uncommitted changes,
   stop and ask whether to stash or commit them first.
2. Ensure you are on the `main` branch. If not, stop and ask.
3. Read the current version from `pyproject.toml`.
4. Determine the previous release tag: `git describe --tags --abbrev=0`.
5. Compute the new version:
   - If `$ARGUMENTS` is provided and non-empty, use it as the new version verbatim.
   - Otherwise, bump the minor segment: `M.N.L` → `M.N+1.0`.
6. Print: "Releasing: {old_version} → {new_version}" and continue.

## Step 2 — Code clean-up

1. Run `cmd.exe /c "uv run ruff format ."`.
2. Run `cmd.exe /c "uv run ruff check --fix"`.
3. Review the codebase for any other clean-up opportunities (dead imports, unused
   variables, obvious issues). Fix anything found.
4. If any files changed, stage and commit them:
   `git commit -m "pre-release clean-up"`.

## Step 3 — Tests

1. Run `cmd.exe /c "uv run pytest -q"`.
2. If tests fail, stop and report. Do not continue until tests pass.

## Step 4 — Pre-bump build verification

1. Run `cmd.exe /c "packaging\build_installer.bat"` to verify the build pipeline
   works before touching version numbers.
2. If the build fails, stop and report.

## Step 5 — Bump version

Update the version string in **all three** locations. Use exact string replacement
(Edit tool), not regex:

1. `pyproject.toml` line `version = "{old}"` → `version = "{new}"`
2. `packaging/installer.iss` line `#define MyAppVersion   "{old}"` → `#define MyAppVersion   "{new}"`
3. `packaging/scriptorium.spec` line `"CFBundleShortVersionString": "{old}"` → `"CFBundleShortVersionString": "{new}"`

After editing, verify all three files contain the new version by grepping for it.

## Step 6 — Changelog

1. Run `git log v{old_version}..HEAD --oneline` to get all commits since the last tag.
2. Group commits into categories: **Features**, **Fixes**, **Build / Infra**, **Other**.
   Omit merge commits and trivial formatting-only commits.
3. Draft release notes in this format:

```
## v{new_version}

### Features
- ...

### Bugfixes
- ...

### Build / Infra
- ...
```

4. **[REVIEW]** — Present the draft changelog to the user. Ask if anything should be added, removed, or reworded. Apply feedback before continuing.

## Step 7 — Update README.md

1. Read `README.md`.
2. If a `## Version History` section does not exist yet, create it immediately before the `## More Information` section.
3. Prepend the new version entry (newest first) to the Version History section. Each entry should be a brief TL;DR — 2–5 bullet points covering the headline features of this release. Do not duplicate the full changelog — summarize.
4. **[REVIEW]** — Show the user the new Version History entry. Apply feedback.

## Step 8 — Review SPEC.md

1. Read `SPEC.md` in full.
2. Compare it against the current state of the codebase: repo layout, invocation modes, build pipeline, script anatomy, theme anatomy, inputs/outputs convention.
3. If anything is stale or missing, update it.
4. **[REVIEW]** — If changes were made, summarize them for the user. If no changes needed, say so and continue.

## Step 9 — Rebuild with new version

1. Run `cmd.exe /c "packaging\build_installer.bat"` again. This time the .exe
   will have the new version baked in.
2. If the build fails, stop and report.
3. Confirm the bump reached the bundle:
   `cmd.exe /c "findstr /b version dist\scriptorium\_internal\pyproject.toml"`.

This build is a **local check only** — it proves the pipeline works and the
version is baked in before a tag goes out. The artifacts users download are the
ones CI builds in Step 12. Do not upload anything from `dist/`.

## Step 10 — Final checks

1. Run `cmd.exe /c "uv run ruff format ."`.
2. Run `cmd.exe /c "uv run ruff check --fix"`.
3. Run `cmd.exe /c "uv run pytest -q"`.
4. If anything fails, fix it and re-run.

## Step 11 — Commit, tag, push

1. Stage all changed files (be explicit — list each file, do not use `git add -A`).
2. Commit with message: `release v{new_version}`.
3. Create an annotated tag: `git tag -a v{new_version} -m "v{new_version}"`.
4. Push the commit first, then the tag: `git push && git push --tags`.

Pushing the tag starts the release build. Everything after this point is
watching and verifying, not publishing.

## Step 12 — Wait for CI, then verify

1. Find the run the tag started: `gh run list --limit 3`. The `v{new_version}`
   row is the one. If no run appears within a minute, stop and report — the tag
   did not trigger the workflow, and the release will not exist.
2. Wait for it, rather than polling by hand:
   `gh run watch {run_id} --exit-status --interval 30`.
   It builds three platforms, so allow roughly 10 minutes.
3. If the run fails, stop and report which job failed. Do not hand-build a
   substitute release — fix the cause and re-run with `gh run rerun {run_id}`.
4. Confirm the release exists with all three assets:

```
gh release view v{new_version} --json assets --jq '.assets[] | "\(.name) \(.size) \(.state)"'
```

   Expect `Scriptorium-macOS.dmg`, `ScriptoriumSetup.exe` and
   `scriptorium-linux-x86_64.tar.gz`, each `uploaded`. Fewer than three, or any
   asset not `uploaded`, means the run half-finished — re-run it.
5. The workflow sets `generate_release_notes: true`, so the body is just a
   compare link. Replace it with the changelog approved in Step 6, keeping the
   link as the last line. Write the notes to a file and pass that, so the
   markdown survives the shell:

```
gh release edit v{new_version} --notes-file {path}
```

6. Print the release URL so the user can verify.

### If the release needs to be rebuilt

The tag already exists, so re-tagging is not the fix — `gh run rerun {run_id}`
republishes from the same tag. Only if the tag itself points at the wrong commit
should it be moved, and that needs the user's say-so first.

---

## Abort conditions

At any point, if something fails that you cannot fix automatically, **stop and report the issue clearly**. Do not attempt to work around build failures, test failures, or git conflicts silently.

This applies with particular force after the tag is pushed. A half-published
release is recoverable — a re-run fixes it. Reaching for `gh release create`,
`gh release delete` or a moved tag to force it into shape is what turns a
recoverable state into a destroyed one.
