@.claude/skills/terminal/terminal.md
@.claude/skills/task-workflow/task-workflow.md
@.claude/skills/code-style/code-style.md
@.claude/skills/dependencies/dependencies.md


## What this repo is

Scriptorium — a personal toolkit of themed Python scripts (audio/video, images,
file conversion, LoRA datasets, Telegram export analysis, and more), usable three
ways from one codebase:

- **CLI** — `uv run main.py <theme>.<script>`
- **Local web UI** — auto-generated forms and streaming output
- **Packaged desktop app** — a PyInstaller bundle that needs no Python on the host

Everything is local and single-user. There is no server, no account, no network
dependency at runtime beyond what individual scripts choose to fetch.

## Where the details live

Do not duplicate these here — update them at the source:

- **[SPEC.md](SPEC.md)** — technical spec: repo layout, tech stack, the script
  module contract, path/output conventions, web endpoints, packaging and
  platform-specific build notes.
- **[PRODUCT.md](PRODUCT.md)** — product spec: who it is for, brand voice,
  visual identity, design tokens and UI principles.
- **[BACKLOG.md](BACKLOG.md)** — deferred work, each entry written to be picked
  up cold.
- **[HUMAN_TODO.md](HUMAN_TODO.md)** — tasks that need a human (assets to draw,
  licences to confirm, things an agent cannot do).
- **[README.md](README.md)** — user-facing install and usage.

## Working in this repo

- A script is any module under `scripts/<theme>/` exposing `TITLE`,
  `DESCRIPTION` and `run()`. Discovery is automatic — see the checklist at the
  bottom of SPEC.md before adding one.
- The web UI reads argparse parsers to build its forms. Changing a script's
  `get_parser()` changes its web form; there is no second definition to update.
- The UI layer is deliberately build-step-free: Jinja templates, one stylesheet,
  and Alpine.js. Do not introduce a bundler or a component framework without
  discussing it first.
- Anything user-visible must work in **both** light and dark themes. Tokens are
  defined in pairs at the top of `webapp/static/style.css`.
- Controls that are not wired up yet are rendered disabled with a "Coming soon!"
  tooltip and a BACKLOG.md entry — never as live controls that do nothing.
