---
register: product
---

# Scriptorium

**Product purpose**: Personal desktop utility for discovering and running themed Python scripts. Self-hosted developer tool — the UI provides auto-generated forms and streaming output without touching the CLI.

**Users**: Primary: one developer (owner/operator). Secondary: non-technical users running the packaged desktop app — they interact only through the UI and never touch the CLI. The UI serves navigation speed for the primary user and basic discoverability for the secondary.

**Brand voice**: Technical, concise, zero marketing copy. Labels and hints are literal and functional.

**Anti-references**: Consumer SaaS, dashboard hero metrics, marketing landing pages.

**Strategic principles**:
- Access speed over discoverability friction — the primary user knows what they want
- CLI equivalence: anything the UI does, `uv run main.py <key>` can too. The script page proves it with a live command preview.
- Self-contained: the packaged app works without Python, uv, CLI knowledge, or an internet connection
- Personal tool aesthetics: precise, quiet, no empty ceremony

## Visual identity

Small, polished desktop utility. Calm and useful, not dashboard theater.

- Off-white app background, white cards and panels, subtle lavender/purple accent
- Rounded corners, soft shadows, generous but not airy spacing
- **Inter** for UI text, **JetBrains Mono** for script keys, CLI snippets, command previews, paths, badges and terminal output. Both self-hosted, so the packaged app renders correctly offline.
- Green is reserved for the Run action and success; red for failure; amber for warnings. The accent purple never means "status".
- The output console is dark in both themes — logs should read as a console, not as page content.

## Light and dark are equal

Neither theme is primary. Every design token is defined in pairs at the top of `webapp/static/style.css`; adding one to `:root` without a matching `html.dark` entry is a bug. Anything user-visible must be checked in both.

## UI principles

- **Never ship a control that lies.** Features that are not built yet are rendered disabled with a "Coming soon!" tooltip and a BACKLOG.md entry — not as live controls that silently do nothing. As of v0.5.2 every visible control is real, so the pattern has no current users; the `soon_button()` macro stays because the rule still applies to the next unbuilt thing. Cancel was held to it longest: killing the Python parent while ffmpeg carried on would have been exactly the kind of lie this forbids.
- **Don't claim what isn't known.** The UI states plainly that individual output files are not detected rather than guessing at them, and the progress bar is indeterminate because no script reports progress.
- **Destructive choices belong to the user.** Cancelling a run stops the work but leaves whatever it already wrote on disk; the app does not delete files on the user's behalf.
- **Motion is subtle and optional.** Transitions are 120–260ms and carry meaning (a pill sliding, a drawer opening). `prefers-reduced-motion: reduce` removes every scale, slide and pulse; colour changes carry the meaning instead.
- **Keyboard first-class.** Modals trap focus and close on `Esc`; icon-only buttons carry `aria-label`; every interactive element has a visible focus ring in the accent colour.
- **No build step.** Jinja templates, one stylesheet, Alpine.js. Shared UI is a macro (`_components.html`, `_icons.html`) or a CSS class, never a bundled component.
