"""Matplotlib chart rendering for chat_analysis.

All charts write PNGs into the supplied ``charts_dir`` and return the path.
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

SELF_COLOR = "#d83a3a"
PARTNER_COLOR = "#3a7ad8"
SHARED_COLOR = "#8c5fb8"
PASSIVE_COLOR = "#cfe8f6"
ACTIVE_COLOR = "#c0392b"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Word-cloud self-vs-partner thresholds: ≥70% self → red, ≤30% self → blue, middle → purple.
SELF_DOMINANT_THRESHOLD = 0.7
PARTNER_DOMINANT_THRESHOLD = 0.3


def _user_color(idx: int) -> str:
    return SELF_COLOR if idx == 0 else PARTNER_COLOR


def _participant_label(analytics: dict[str, Any], uid: str) -> str:
    for p in analytics["participants"]:
        if p["id"] == uid:
            return p["display_name"]
    return uid


def render_monthly_volume(analytics: dict[str, Any], charts_dir: Path) -> Path:
    monthly = analytics["monthly_volume"]
    now = datetime.fromisoformat(analytics["generated_at"])
    current_year = now.year
    current_month = now.month  # 1..12
    current_day = max(now.day, 1)

    fig, ax = plt.subplots(figsize=(8, 4))
    forecast_caption: str | None = None
    year_keys = sorted(monthly.keys())
    for i, year in enumerate(year_keys):
        values = monthly[year]
        alpha = 0.4 + 0.3 * i  # newer years brighter
        if int(year) == current_year:
            display_values, forecast_value = _forecast_current_year_series(
                values, current_month, current_day, current_year
            )
            ax.plot(MONTHS, display_values, label=f"{year}*", marker="o", color=ACTIVE_COLOR, alpha=alpha, linewidth=2)
            # Mark the forecast point with an open marker so it reads as projected, not measured.
            ax.plot(
                [MONTHS[current_month - 1]],
                [forecast_value],
                marker="o",
                markerfacecolor="white",
                markeredgecolor=ACTIVE_COLOR,
                markeredgewidth=1.5,
                linestyle="None",
            )
            actual_this_month = values[current_month - 1]
            forecast_caption = (
                f"* {MONTHS[current_month - 1]} {current_year} is a forecast: "
                f"{actual_this_month} messages over {current_day} day(s) extrapolated "
                f"to {calendar.monthrange(current_year, current_month)[1]} days "
                f"→ ~{forecast_value} (not counted toward totals)."
            )
        else:
            ax.plot(MONTHS, values, label=year, marker="o", color=ACTIVE_COLOR, alpha=alpha, linewidth=2)
    ax.set_title("Messages per month")
    ax.set_ylabel("Messages")
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    ax.legend(title="Year", loc="upper right")
    if forecast_caption:
        fig.text(0.5, 0.01, forecast_caption, ha="center", fontsize=8, color="#555555")
        fig.tight_layout(rect=(0, 0.04, 1, 1))
    else:
        fig.tight_layout()
    path = charts_dir / "monthly_volume.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
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
    cmap = LinearSegmentedColormap.from_list("activity", [PASSIVE_COLOR, ACTIVE_COLOR])
    fig, ax = plt.subplots(figsize=(10, 4))
    im = ax.imshow(matrix, aspect="auto", cmap=cmap)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_yticks(range(7))
    ax.set_yticklabels(days)
    ax.set_xlabel("Hour of day")
    ax.set_title("Activity by day-of-week and hour")
    fig.colorbar(im, ax=ax, label="Messages")
    fig.tight_layout()
    path = charts_dir / "activity_heatmap.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
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
    if sum(values) <= 0:
        ax.text(0.5, 0.5, "No messages", ha="center", va="center")
    else:
        ax.pie(values, labels=labels, colors=colors, wedgeprops={"width": 0.4}, startangle=90)
    ax.set_title("Message share")
    fig.tight_layout()
    path = charts_dir / "message_share.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
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

    fig, ax = plt.subplots(figsize=(7, 4))
    x = range(len(labels))
    width = 0.25
    ax.bar([i - width for i in x], medians_min, width=width, label="Median", color=colors, alpha=0.95)
    ax.bar(list(x), means_min, width=width, label="Mean", color=colors, alpha=0.7)
    ax.bar([i + width for i in x], p90s_min, width=width, label="p90", color=colors, alpha=0.45)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Minutes")
    ax.set_title("Reply latency (minutes)")
    ax.legend()
    fig.tight_layout()
    path = charts_dir / "reply_latency.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
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

    wc = WordCloud(
        width=1600,
        height=900,
        background_color="white",
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
    ax.barh(labels[::-1], counts[::-1], color=ACTIVE_COLOR, alpha=0.85)
    ax.set_title("Top emojis")
    ax.set_xlabel("Count")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"Glyph \d+ .* missing from font.*")
        fig.tight_layout()
        fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _placeholder(path: Path, text: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=14, color="#888")
    ax.set_axis_off()
    fig.savefig(path, dpi=120)
    plt.close(fig)
