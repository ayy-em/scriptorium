---
register: product
---

# Scriptorium

**Product purpose**: Personal web UI for discovering and running themed Python scripts. Self-hosted developer tool — the web layer provides auto-generated forms and streaming output without touching the CLI.

**Users**: Primary: one developer (owner/operator). Secondary: non-technical users running the macOS `.app` bundle — they interact only through the web UI and never touch the CLI. The UI serves navigation speed for the primary user and basic discoverability for the secondary.

**Brand voice**: Technical, concise, zero marketing copy. Labels and hints are literal and functional.

**Theme**: Dark mode is primary. Developer at a desk, often late, multiple monitors. Scene forces dark.

**Anti-references**: Consumer SaaS, dashboard hero metrics, marketing landing pages.

**Strategic principles**:
- Access speed over discoverability friction — the primary user knows what they want
- CLI equivalence: anything the web UI does, `uv run main.py <key>` can too (dev mode)
- Self-contained: the macOS `.app` works without Python, uv, or CLI knowledge
- Personal tool aesthetics: precise, quiet, no empty ceremony
