"""WeasyPrint-backed PDF rendering for group_analysis.

Renders a 7-page A4 report from a Jinja2 HTML+CSS template. The public
``render_group_pdf(analytics, chart_paths, out_path) -> Path`` signature
mirrors the 1:1 chat ``render_pdf`` so the orchestrator stays clean.
"""

from scripts.telegram._runtime import ensure_native_lib_resolution

ensure_native_lib_resolution()

from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402
from weasyprint import HTML  # noqa: E402

from core.paths import assets_dir  # noqa: E402

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_BG_IMAGE_NAME = "telegram-pdf-bg.png"


def render_group_pdf(
    analytics: dict[str, Any],
    chart_paths: dict[str, Path],
    out_path: Path,
) -> Path:
    """Render the group-analytics report to ``out_path`` and return the path."""
    ctx = _build_context(analytics, chart_paths)
    html_str = _render_template(ctx)
    HTML(string=html_str, base_url=str(_TEMPLATE_DIR)).write_pdf(str(out_path))
    return out_path


def _build_context(
    analytics: dict[str, Any],
    chart_paths: dict[str, Path],
) -> dict[str, Any]:
    """Build the Jinja2 template context from the analytics dict."""
    return {
        "a": analytics,
        "group_name": analytics["source"]["group_name"],
        "charts": {key: Path(p).as_uri() for key, p in chart_paths.items()},
    }


def _render_template(ctx: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "jinja2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals.update(
        humanize=_humanize,
        pct=_pct,
        pct_float=_pct_float,
        format_seconds=_format_seconds,
        gmt1_hour=_gmt1_hour,
        font_url=_font_url,
        bg_url=_bg_url(),
        name=_make_name_fn(ctx["a"]),
    )
    css_tpl = env.get_template("group_report.css")
    rendered_css = css_tpl.render(font_url=_font_url, bg_url=_bg_url())
    html_tpl = env.get_template("group_report.html.jinja2")
    return html_tpl.render(css=rendered_css, **ctx)


def _make_name_fn(analytics: dict[str, Any]):
    """Return a closure that looks up display names from the participants list."""
    lookup = {p["id"]: p["display_name"] for p in analytics["participants"]}

    def name_fn(uid: str | None) -> str:
        if uid is None:
            return "No winner"
        return lookup.get(uid, uid)

    return name_fn


_THOUSAND = 1_000
_MILLION = 1_000_000
_BILLION = 1_000_000_000


def _humanize(n: int | None) -> str:
    """Compact integer formatter — 169816 -> '169.8k'."""
    if n is None:
        return "—"
    if abs(n) < _THOUSAND:
        return f"{n:,}"
    if abs(n) < _MILLION:
        return f"{n / _THOUSAND:.1f}k"
    if abs(n) < _BILLION:
        return f"{n / _MILLION:.1f}M"
    return f"{n / _BILLION:.1f}B"


def _pct(frac: float | None) -> str:
    """Format a fraction as a percentage string."""
    if frac is None:
        return "—"
    return f"{frac * 100:.0f}%"


def _pct_float(frac: float | None) -> str:
    """Format a fraction as a comma-separated 2-decimal percentage (e.g. '2,42%')."""
    if frac is None:
        return "—"
    return f"{frac * 100:,.2f}%".replace(",", " ").replace(".", ",").replace(" ", ".")


def _gmt1_hour(hour: int) -> str:
    """Convert a chat-local hour to GMT+1 display string (assumes chat = GMT+1)."""
    return f"{hour:02d}:00 GMT+1"


def _format_seconds(s: float | None) -> str:
    """Convert seconds to 'Xd Yh Zm' human format."""
    if s is None or s <= 0:
        return "n/a"
    td = timedelta(seconds=int(s))
    hours, rem = divmod(td.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    days = td.days
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{int(s)}s")
    return " ".join(parts)


def _font_url(rel: str) -> str:
    """Return a file:// URL for a font asset under the shared assets directory."""
    return (assets_dir() / "fonts" / rel).as_uri()


def _bg_url() -> str:
    return (assets_dir() / "img" / _BG_IMAGE_NAME).as_uri()
