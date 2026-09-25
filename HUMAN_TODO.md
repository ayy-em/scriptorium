# Human TODO

Things an agent cannot do for you: artwork to draw or source, licences to
confirm, and checks that need a real desktop session. Ordered roughly by how
much they affect what people see.

Everything here is **optional** — the app ships and looks coherent without any
of it. Item 1 is kept as a record of a decision, not as work.

---

## 1. ffmpeg licensing — resolved

**Decided 2026-09-24: ffmpeg is not bundled.** The app asks for an install
instead: a final onboarding slide and a banner on every media script's page
carry the same one-click Install as the sidebar (winget on Windows, brew on
macOS), so there is no GPL binary in the release and no licence work. The
full reasoning and the bundling alternative, should it ever be wanted, are
under "Runtime dependencies: bundle ffmpeg" in BACKLOG.md's Settled section.

Nothing here is a blocker any more.

---

## 2. pango for PDF output in the installed Windows app

The Telegram PDF reports need pango, cairo and glib, which are not bundled
(decision 2026-09-24: not worth three native dependency graphs for one user).
The packaged app looks for them in exactly two places, from
`core/native_libs.py`: `C:\msys64\ucrt64\bin` first, then
`C:\msys64\mingw64\bin`. So the install has to land in the default MSYS2
location — no custom install directory — and use the UCRT64 environment.

Run once, in a normal Command Prompt (not as administrator):

```
winget install --id MSYS2.MSYS2 --exact --accept-source-agreements --accept-package-agreements
C:\msys64\usr\bin\bash.exe -lc "pacman -S --noconfirm --needed mingw-w64-ucrt-x86_64-pango"
```

Then reload Scriptorium (a restart is not needed; the probe re-runs on each
page). The sidebar entry for "pango / cairo / glib" disappears when it works.
The same two lines are what an Install button would run if one were ever
added; they are not wired up because the second step can prompt to close a
running MSYS2 shell, which an unattended run cannot answer.

- [ ] Run the two lines above on the machine that has the installed app.
- [ ] Open `telegram.chat_analysis` and confirm the banner is gone.

---

## 3. Optional illustrations

Small spot art for empty states. The shared `empty_state()` macro currently
renders a single icon in a lavender rounded square, which is fine — this is
polish, not a gap.

- [ ] No search results
- [ ] No favourites
- [ ] No compatible scripts after a file drop
- [ ] Generic "file dropped" mark

---

## 4. Checks that need a real desktop session

The prettification pass was verified in a headless browser pane. The following
could not be verified there and need a human with the app actually open.

- [ ] **The 20 new glyphs.** The PNG sweep replaced every raster icon with
      inline SVG drawn to the 16×16 house spec, but no renderer was available to
      look at them. Structure is checked by `tests/webapp/test_icons.py`;
      *appearance* is not. Worth one pass down the sidebar (the 9 themes that
      have scripts; empty theme folders are not listed) and
      one file drop of each category, in both light and dark. The three sizes to
      judge are 14px (sidebar), 24px (wheel card) and 72px (file chip) — the
      last uses a lighter stroke and is the most likely to look wrong.
- [ ] **The SVG logo.** `logo.svg` now drives the splash (88×88), the top bar
      (22×22) and the favicon. It is a 129-path trace of the raster mark and no
      SVG renderer was available here, so it was never actually drawn. Worth one
      look at all three sizes — the 22×22 top bar is where a coarse trace would
      show first.
- [ ] **Animation timing.** The verification pane runs with
      `document.hidden === true`, so `requestAnimationFrame` never fires and CSS
      transitions never advance. Every *end state* was verified; the motion
      between states was not. Worth one pass through: modal open/close, the
      segmented-control pill slide, terminal expand/collapse, dropzone
      drag-over, and the splash fade-out.
- [ ] **The Browse button.** `POST /api/browse-folder` only works under the
      pywebview desktop wrapper, where `app.state.webview_window` is set. In dev
      and in Chromium `--app` mode it returns 501 and the button renders
      disabled with an explanatory tooltip — that path is verified. The actual
      native folder dialog is not, and it can only be checked on macOS or
      Linux: pywebview is not used on Windows at all, so there the button is
      always disabled.
- [ ] **macOS and Linux.** All verification was on Windows. Font rendering,
      the tray icon, the folder dialog, and run cancellation are the likely
      divergences.
- [ ] **Close-to-tray, one click.** The tray icon is now created in the Chromium
      fallback tier (verified: the frozen app launches, the icon is created, and
      `close_behavior: "tray"` is read). Confirm there is exactly **one** icon —
      a leak that showed two was fixed on 2026-08-01, but only ever reproduced
      in the frozen build. What could not be verified without a
      human at the machine is the actual interaction — close the window and
      confirm the app stays resident, then use the tray's "Show Scriptorium" to
      bring it back and "Quit" to exit. pywebview is not used on Windows (see
      "pywebview cannot start in the frozen Windows app" in BACKLOG.md's Settled
      section), so this is always the Chromium tier there.
- [ ] **POSIX run cancellation.** The Windows path is verified end to end — a
      real ffmpeg transcode was started through the UI and cancelled, and the
      ffmpeg process count went from 1 to 0 rather than being orphaned. The
      POSIX equivalent (`start_new_session=True` at spawn, then
      `killpg(SIGTERM)` escalating to `SIGKILL`) is unit-tested against stubs
      but has never delivered a real signal. Worth one check on macOS or Linux:
      start a long transcode, hit Cancel, confirm with `ps` that no ffmpeg
      survives.
- [ ] **Reduced motion.** `prefers-reduced-motion: reduce` rules are written but
      were not exercised. Toggle it in your OS settings and confirm nothing
      slides, scales or pulses.

---

## 5. Housekeeping

- [ ] **Alpine is pinned at 3.15.12** in `webapp/static/js/`. It is vendored, so
      updating means re-downloading both `alpinejs.min.js` and
      `alpinejs-focus.min.js` at matching versions.
- [ ] **Fonts are vendored** as Inter and JetBrains Mono variable woff2 (89KB
      total), both SIL OFL 1.1, licences alongside them in
      `webapp/static/fonts/`. No action needed unless you change families.
