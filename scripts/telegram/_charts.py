"""Matplotlib chart rendering for chat_analysis.

All charts write transparent PNGs into the supplied ``charts_dir`` and return
the path. The palette is tuned to sit on the deep purple/blue PDF backdrop —
no white backgrounds, white axis text, no chart-junk spines.
"""

import calendar
from collections import Counter
from datetime import datetime
import math
from pathlib import Path
from typing import Any
import warnings

import matplotlib

matplotlib.use("Agg")  # headless backend; must be set before pyplot import
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from wordcloud import WordCloud  # noqa: E402

# matplotlib's default DejaVu font lacks glyphs for many emoji; we accept the
# visual gap in bar-chart labels rather than chase a system emoji font that may
# not exist on every platform. Warnings are suppressed at the call site below.

SELF_COLOR = "#38BDF8"  # bright sky — matches --self in report.css
PARTNER_COLOR = "#FF4D6D"  # electric coral — matches --partner
SHARED_COLOR = "#C084FC"  # lavender — matches --shared
HERO_COLOR = "#FFEB3B"  # vivid yellow — matches --hero
HEATMAP_COLD = "#1E3A8A"  # deep indigo, low alpha at the cold end
HEATMAP_HOT = "#FF1A6B"  # hot pink at the busy end
WHITE_90 = (1.0, 1.0, 1.0, 0.90)
WHITE_60 = (1.0, 1.0, 1.0, 0.60)
WHITE_25 = (1.0, 1.0, 1.0, 0.25)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Word-cloud self-vs-partner thresholds: ≥70% self → self color, ≤30% self → partner, middle → shared.
SELF_DOMINANT_THRESHOLD = 0.7
PARTNER_DOMINANT_THRESHOLD = 0.3

_DPI = 200


def _user_color(idx: int) -> str:
    return SELF_COLOR if idx == 0 else PARTNER_COLOR


def _participant_label(analytics: dict[str, Any], uid: str) -> str:
    for p in analytics["participants"]:
        if p["id"] == uid:
            return p["display_name"]
    return uid


def _style_axes(ax: plt.Axes) -> None:
    """Strip frame, light grid, white tick labels — designed for dark backdrop."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=WHITE_90, which="both", length=0)
    for lbl in (*ax.get_xticklabels(), *ax.get_yticklabels()):
        lbl.set_color(WHITE_90)
    ax.xaxis.label.set_color(WHITE_90)
    ax.yaxis.label.set_color(WHITE_90)
    ax.title.set_color(WHITE_90)
    ax.grid(False)


def _save_transparent(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=_DPI, transparent=True, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)


def render_monthly_volume(analytics: dict[str, Any], charts_dir: Path) -> Path:
    monthly = analytics["monthly_volume"]
    now = datetime.fromisoformat(analytics["generated_at"])
    current_year = now.year
    current_month = now.month
    current_day = max(now.day, 1)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    forecast_caption: str | None = None
    year_keys = sorted(monthly.keys())
    n_years = len(year_keys)
    for i, year in enumerate(year_keys):
        values = monthly[year]
        # Older years dimmer, current year brightest. Single year → full strength.
        alpha = 1.0 if n_years == 1 else 0.35 + 0.65 * (i / max(n_years - 1, 1))
        is_current = int(year) == current_year
        color = HERO_COLOR if is_current else SELF_COLOR

        if is_current:
            display_values, forecast_value = _forecast_current_year_series(
                values, current_month, current_day, current_year
            )
            ax.plot(
                MONTHS,
                display_values,
                label=f"{year}*",
                marker="o",
                color=color,
                alpha=alpha,
                linewidth=2.5,
                markersize=6,
                markeredgewidth=0,
            )
            ax.plot(
                [MONTHS[current_month - 1]],
                [forecast_value],
                marker="o",
                markerfacecolor="none",
                markeredgecolor=color,
                markeredgewidth=2,
                markersize=10,
                linestyle="None",
            )
            actual_this_month = values[current_month - 1]
            forecast_caption = (
                f"* {MONTHS[current_month - 1]} {current_year} forecast: "
                f"{actual_this_month} msgs in {current_day} day(s) → "
                f"~{forecast_value} for the full month"
            )
        else:
            ax.plot(
                MONTHS,
                values,
                label=year,
                marker="o",
                color=color,
                alpha=alpha,
                linewidth=2,
                markersize=5,
                markeredgewidth=0,
            )

    ax.set_ylabel("Messages")
    ax.yaxis.grid(True, linestyle="-", linewidth=0.4, color=WHITE_25, alpha=1.0)
    ax.set_axisbelow(True)

    leg = ax.legend(
        title="Year",
        loc="upper left",
        frameon=False,
        labelcolor=WHITE_90,
        fontsize=9,
        title_fontsize=9,
    )
    if leg is not None:
        leg.get_title().set_color(WHITE_90)

    _style_axes(ax)

    if forecast_caption:
        fig.text(0.5, 0.0, forecast_caption, ha="center", fontsize=8, color=WHITE_60)

    path = charts_dir / "monthly_volume.png"
    _save_transparent(fig, path)
    return path


def _forecast_current_year_series(
    values: list[int], current_month: int, current_day: int, current_year: int
) -> tuple[list[float], int]:
    """Return (12-element series for the current-year line, current-month forecast).

    Months after the current month are NaN so they don't render. The current
    month is replaced with a day-of-month extrapolation. Months before the
    current month show actual counts.
    """
    days_in_month = calendar.monthrange(current_year, current_month)[1]
    actual_this_month = values[current_month - 1]
    forecast = int(round(actual_this_month * days_in_month / current_day))
    series: list[float] = []
    for idx, v in enumerate(values):
        month = idx + 1
        if month < current_month:
            series.append(float(v))
        elif month == current_month:
            series.append(float(forecast))
        else:
            series.append(math.nan)
    return series, forecast


def render_activity_heatmap(analytics: dict[str, Any], charts_dir: Path) -> Path:
    heatmap = analytics["activity_heatmap"]
    matrix = heatmap["matrix"]
    days = heatmap["days"]

    # Cold end transparent so the gradient shows through; hot end opaque pink.
    cmap = LinearSegmentedColormap.from_list(
        "activity_neon",
        [
            (0.00, (0.12, 0.23, 0.54, 0.0)),  # transparent indigo
            (0.15, (0.22, 0.49, 0.97, 0.55)),  # sky
            (0.55, (0.75, 0.30, 0.97, 0.85)),  # lavender→magenta
            (1.00, (1.00, 0.10, 0.42, 1.0)),  # hot pink
        ],
    )

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    im = ax.imshow(matrix, aspect="auto", cmap=cmap, interpolation="nearest")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_yticks(range(7))
    ax.set_yticklabels(days)
    ax.set_xlabel("Hour of day")

    cbar = fig.colorbar(im, ax=ax, label="Messages", pad=0.02, shrink=0.85)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(colors=WHITE_90, length=0)
    for lbl in cbar.ax.get_yticklabels():
        lbl.set_color(WHITE_90)
    cbar.ax.yaxis.label.set_color(WHITE_90)

    _style_axes(ax)

    path = charts_dir / "activity_heatmap.png"
    _save_transparent(fig, path)
    return path


def render_message_share(analytics: dict[str, Any], charts_dir: Path) -> Path:
    share = analytics["share_by_user"]
    labels: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    for i, (uid, frac) in enumerate(share.items()):
        labels.append(f"{_participant_label(analytics, uid)} ({frac:.0%})")
        values.append(frac)
        colors.append(_user_color(i))

    fig, ax = plt.subplots(figsize=(5, 5))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    if sum(values) <= 0:
        ax.text(0.5, 0.5, "No messages", ha="center", va="center", color=WHITE_90)
    else:
        wedges, texts = ax.pie(
            values,
            labels=labels,
            colors=colors,
            wedgeprops={"width": 0.35, "edgecolor": "none"},
            startangle=90,
            textprops={"color": WHITE_90, "fontsize": 11},
        )

    ax.set_axis_off()
    path = charts_dir / "message_share.png"
    _save_transparent(fig, path)
    return path


def render_reply_latency(analytics: dict[str, Any], charts_dir: Path) -> Path:
    latency = analytics["reply_latency_seconds"]
    labels: list[str] = []
    means_min: list[float] = []
    medians_min: list[float] = []
    p90s_min: list[float] = []
    colors: list[str] = []
    for i, (uid, stats) in enumerate(latency.items()):
        labels.append(_participant_label(analytics, uid))
        means_min.append(stats["mean"] / 60)
        medians_min.append(stats["median"] / 60)
        p90s_min.append(stats["p90"] / 60)
        colors.append(_user_color(i))

    fig, ax = plt.subplots(figsize=(8, 3.8))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    x = range(len(labels))
    width = 0.25
    ax.bar([i - width for i in x], medians_min, width=width, label="Median", color=colors, alpha=1.0, edgecolor="none")
    ax.bar(list(x), means_min, width=width, label="Mean", color=colors, alpha=0.65, edgecolor="none")
    ax.bar([i + width for i in x], p90s_min, width=width, label="p90", color=colors, alpha=0.35, edgecolor="none")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Minutes")
    ax.yaxis.grid(True, linestyle="-", linewidth=0.4, color=WHITE_25, alpha=1.0)
    ax.set_axisbelow(True)

    leg = ax.legend(loc="upper right", frameon=False, labelcolor=WHITE_90, fontsize=9)
    _style_axes(ax)

    path = charts_dir / "reply_latency.png"
    _save_transparent(fig, path)
    return path


def render_word_cloud(
    word_counts: Counter,
    word_shares: dict[str, float],
    charts_dir: Path,
) -> Path:
    path = charts_dir / "word_cloud.png"
    if not word_counts:
        _placeholder(path, "No words to display")
        return path

    def color_func(word: str, **_: Any) -> str:
        share = word_shares.get(word, 0.5)
        if share >= SELF_DOMINANT_THRESHOLD:
            return SELF_COLOR
        if share <= PARTNER_DOMINANT_THRESHOLD:
            return PARTNER_COLOR
        return SHARED_COLOR

    # mode="RGBA" + background_color=None gives a transparent canvas; the PDF
    # backdrop shows through, so the cloud doesn't carry its own white block.
    wc = WordCloud(
        width=1600,
        height=900,
        background_color=None,
        mode="RGBA",
        color_func=color_func,
        prefer_horizontal=0.9,
        max_words=200,
    )
    wc.generate_from_frequencies(dict(word_counts))
    wc.to_file(str(path))
    return path


def render_emoji_cloud(analytics: dict[str, Any], charts_dir: Path) -> Path:
    """Emoji 'cloud' rendered as a bar chart of top emojis per user.

    Per the locked decisions, a true emoji wordcloud requires a Unicode emoji
    font, which is fragile across platforms — fall back to a clean bar chart.
    """
    path = charts_dir / "emoji_cloud.png"
    combined: Counter[str] = Counter()
    for uid_emojis in analytics["top_emojis"].values():
        for entry in uid_emojis:
            combined[entry["emoji"]] += entry["count"]
    if not combined:
        _placeholder(path, "No emojis used")
        return path
    top = combined.most_common(15)
    labels = [e for e, _ in top]
    counts = [c for _, c in top]

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    bars = ax.barh(labels[::-1], counts[::-1], color=HERO_COLOR, alpha=0.95, edgecolor="none")
    ax.set_xlabel("Count")
    ax.xaxis.grid(True, linestyle="-", linewidth=0.4, color=WHITE_25, alpha=1.0)
    ax.set_axisbelow(True)
    _style_axes(ax)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"Glyph \d+ .* missing from font.*")
        _save_transparent(fig, path)
    return path


def _placeholder(path: Path, text: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 3))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=14, color=WHITE_60)
    ax.set_axis_off()
    _save_transparent(fig, path)
