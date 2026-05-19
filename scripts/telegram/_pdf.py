"""WeasyPrint-backed PDF rendering for chat_analysis.

The story-building style of the original ReportLab implementation gave way to
an HTML+CSS template (``templates/report.html.jinja2`` + ``report.css``) so the
design can be expressed in real CSS — gradients, frosted cards, multi-column
grids, custom fonts via ``@font-face``. The Jinja2 template is rendered to an
HTML string, then WeasyPrint converts it to PDF.

The public ``render_pdf(analytics, chart_paths, out_path) -> Path`` signature
is unchanged so ``chat_analysis.py`` is untouched.
"""

# The cffi monkey-patch MUST run before WeasyPrint is imported.
from scripts.telegram._runtime import ensure_native_lib_resolution

ensure_native_lib_resolution()

from datetime import datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402
from weasyprint import HTML  # noqa: E402

from core.paths import assets_dir  # noqa: E402

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_BG_IMAGE_NAME = "telegram-pdf-bg.png"
_TOP_DOMAIN_COUNT = 5


def render_pdf(analytics: dict[str, Any], chart_paths: dict[str, Path], out_path: Path) -> Path:
    """Render the chat-analytics report to ``out_path`` and return the path."""
    self_p, partner_p = _resolve_participants(analytics)
    ctx = _build_context(analytics, chart_paths, self_p, partner_p)
    html_str = _render_template(ctx)
    HTML(string=html_str, base_url=str(_TEMPLATE_DIR)).write_pdf(str(out_path))
    return out_path


def _resolve_participants(analytics: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    participants = analytics["participants"]
    self_p = next((p for p in participants if p["is_self"]), participants[0])
    partner_p = next((p for p in participants if not p["is_self"]), participants[-1])
    return self_p, partner_p


def _build_context(
    analytics: dict[str, Any],
    chart_paths: dict[str, Path],
    self_p: dict[str, Any],
    partner_p: dict[str, Any],
) -> dict[str, Any]:
    self_id = self_p["id"]
    partner_id = partner_p["id"]
    self_name = self_p["display_name"]
    partner_name = partner_p["display_name"]

    leader_id = _argmax(analytics["share_by_user"]) or self_id
    initiator_id = max(
        (k for k in analytics["initiation_share"] if k != "sessions_total"),
        key=lambda k: analytics["initiation_share"][k],
        default=self_id,
    )
    doubletexter_id = max(
        analytics["double_text_rate"].keys(),
        key=lambda k: analytics["double_text_rate"][k]["count"],
        default=self_id,
    )
    doubletexter_total = sum(v["count"] for v in analytics["double_text_rate"].values())

    vocab_self_ratio = analytics["vocabulary_richness"].get(self_id, {}).get("ratio", 0.0)
    vocab_partner_ratio = analytics["vocabulary_richness"].get(partner_id, {}).get("ratio", 0.0)
    if vocab_self_ratio >= vocab_partner_ratio:
        vocab_winner_id, vocab_loser_id = self_id, partner_id
    else:
        vocab_winner_id, vocab_loser_id = partner_id, self_id

    by_user_links = analytics["external_links"]["by_user"]
    linker_id = max(by_user_links.keys(), key=lambda k: by_user_links[k], default=self_id)
    non_linker_id = partner_id if linker_id == self_id else self_id

    top_domains_raw = analytics["external_links"]["by_domain"]
    top_domains = list(top_domains_raw.items())[:_TOP_DOMAIN_COUNT]

    generated_at = datetime.fromisoformat(analytics["generated_at"])

    return {
        "a": analytics,
        "self_id": self_id,
        "partner_id": partner_id,
        "self_name": self_name,
        "partner_name": partner_name,
        "leader_id": leader_id,
        "leader_name": _name(analytics, leader_id),
        "leader_role": "self" if leader_id == self_id else "partner",
        "initiator_id": initiator_id,
        "initiator_name": _name(analytics, initiator_id),
        "initiator_role": "self" if initiator_id == self_id else "partner",
        "doubletexter_id": doubletexter_id,
        "doubletexter_name": _name(analytics, doubletexter_id),
        "doubletexter_role": "self" if doubletexter_id == self_id else "partner",
        "doubletexter_total": doubletexter_total,
        "vocab_winner_id": vocab_winner_id,
        "vocab_winner_name": _name(analytics, vocab_winner_id),
        "vocab_winner_role": "self" if vocab_winner_id == self_id else "partner",
        "vocab_loser_id": vocab_loser_id,
        "vocab_loser_name": _name(analytics, vocab_loser_id),
        "vocab_loser_role": "self" if vocab_loser_id == self_id else "partner",
        "linker_id": linker_id,
        "linker_name": _name(analytics, linker_id),
        "linker_role": "self" if linker_id == self_id else "partner",
        "non_linker_id": non_linker_id,
        "top_domains": top_domains,
        "current_year": generated_at.year,
        "charts": {key: Path(p).as_uri() for key, p in chart_paths.items()},
    }


def _render_template(ctx: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "jinja2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["humanize"] = _humanize  # accessible as `humanize(...)` via globals too
    env.globals.update(
        humanize=_humanize,
        pct=_pct,
        format_seconds=_format_seconds,
        font_url=_font_url,
        bg_url=_bg_url(),
    )
    css_tpl = env.get_template("report.css")
    rendered_css = css_tpl.render(font_url=_font_url, bg_url=_bg_url())
    html_tpl = env.get_template("report.html.jinja2")
    return html_tpl.render(css=rendered_css, **ctx)


def _name(analytics: dict[str, Any], uid: str) -> str:
    for p in analytics["participants"]:
        if p["id"] == uid:
            return p["display_name"]
    return uid


def _argmax(d: dict[str, float]) -> str | None:
    if not d:
        return None
    return max(d.keys(), key=lambda k: d[k])


_THOUSAND = 1_000
_MILLION = 1_000_000
_BILLION = 1_000_000_000


def _humanize(n: int) -> str:
    """Compact integer formatter — 169816 -> '169.8k', 1500000 -> '1.5M'."""
    if n is None:
        return "—"
    if abs(n) < _THOUSAND:
        return f"{n:,}"
    if abs(n) < _MILLION:
        return f"{n / _THOUSAND:.1f}k"
    if abs(n) < _BILLION:
        return f"{n / _MILLION:.1f}M"
    return f"{n / _BILLION:.1f}B"


def _pct(frac: float) -> str:
    if frac is None:
        return "—"
    return f"{frac * 100:.0f}%"


def _format_seconds(s: float) -> str:
    if s is None or s <= 0:
        return "n/a"
    td = timedelta(seconds=int(s))
    hours, rem = divmod(td.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    days = td.days
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _font_url(rel: str) -> str:
    """Return a file:// URL for a font asset under the shared assets directory."""
    return (assets_dir() / "fonts" / rel).as_uri()


def _bg_url() -> str:
    return (assets_dir() / "img" / _BG_IMAGE_NAME).as_uri()
