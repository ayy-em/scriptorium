# Human TODO

Things an agent cannot do for you: artwork to draw or source, licences to
confirm, and checks that need a real desktop session. Ordered roughly by how
much they affect what people see.

Everything here is **optional** — the app ships and looks coherent without any
of it. Nothing below is a blocker.

---

## 1. App logo set

**Status:** the app currently reuses `webapp/static/logo.webp` (10KB) everywhere,
including the new splash screen at 88×88. It is a raster and it is the only
logo asset the UI has.

What to supply, into `webapp/static/logo/`:

| File | Used by | Notes |
|---|---|---|
| `logo.svg` | splash, top bar, future favicon | The important one. Vector means the splash logo stops looking soft. |
| `logo-64.png` | tray icon | pystray needs a raster; currently downsamples `logo.png` (512px) on every launch. |
| `logo-128.png` | installers, docs | |
| `logo-256.png` | Windows installer | |
| `logo-512.png` | macOS `.icns` source | |
| `favicon.ico` | browser tab | `webapp/static/favicon.ico` exists; replace if the mark changes. |

Once `logo.svg` exists, point these at it:
- `webapp/templates/_splash.html` → `.splash-logo` `src`
- `webapp/templates/base.html` → `.topnav-brand img` `src`
- `packaging/entrypoint.py` → `_load_tray_icon()` (needs the PNG, not the SVG)
- `packaging/logo.ico` / `packaging/logo.icns` for the installers

---

## 2. Optional illustrations

Small spot art for empty states. The shared `empty_state()` macro currently
renders a single icon in a lavender rounded square, which is fine — this is
polish, not a gap.

- [ ] No search results
- [ ] No favourites (once favourites exist)
- [ ] No compatible scripts after a file drop
- [ ] Generic "file dropped" mark

---

## 3. Checks that need a real desktop session

The prettification pass was verified in a headless browser pane. The following
could not be verified there and need a human with the app actually open.

- [ ] **The 20 new glyphs.** The PNG sweep replaced every raster icon with
      inline SVG drawn to the 16×16 house spec, but no renderer was available to
      look at them. Structure is checked by `tests/webapp/test_icons.py`;
      *appearance* is not. Worth one pass down the sidebar (all 16 themes) and
      one file drop of each category, in both light and dark. The three sizes to
      judge are 14px (sidebar), 24px (wheel card) and 72px (file chip) — the
      last uses a lighter stroke and is the most likely to look wrong.
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
      native folder dialog is not.
- [ ] **macOS and Linux.** All verification was on Windows. Font rendering,
      the tray icon, the folder dialog, and run cancellation are the likely
      divergences.
- [ ] **Close-to-tray, one click.** The tray icon is now created in the Chromium
      fallback tier (verified: the frozen app launches, the icon is created, and
      `close_behavior: "tray"` is read). What could not be verified without a
      human at the machine is the actual interaction — close the window and
      confirm the app stays resident, then use the tray's "Show Scriptorium" to
      bring it back and "Quit" to exit. pywebview's native window still fails to
      start in the frozen build; see BACKLOG.md.
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

## 4. Housekeeping

- [ ] **Alpine is pinned at 3.15.12** in `webapp/static/js/`. It is vendored, so
      updating means re-downloading both `alpinejs.min.js` and
      `alpinejs-focus.min.js` at matching versions.
- [ ] **Fonts are vendored** as Inter and JetBrains Mono variable woff2 (89KB
      total), both SIL OFL 1.1, licences alongside them in
      `webapp/static/fonts/`. No action needed unless you change families.
