"""Matplotlib chart rendering for group_analysis.

All charts write transparent PNGs into the supplied ``charts_dir`` and return
the path. The palette sits on the deep purple/blue PDF backdrop — no white
backgrounds, white axis text, no chart-junk spines.
"""

import calendar
from collections import Counter
from datetime import datetime
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
import matplotlib.patheffects as path_effects  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
from wordcloud import WordCloud  # noqa: E402

from core.paths import assets_dir  # noqa: E402

_DPI = 200
_MIN_EDGES_FOR_LABELS = 6
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

COLOR_GOLD = "#FBBF24"
COLOR_SKY = "#38BDF8"
COLOR_CORAL = "#FF6585"
COLOR_CRIMSON = "#EF4444"
COLOR_NEON_PURP = "#A855F7"
COLOR_HERO = "#FFEB3B"
WHITE_100 = (1.0, 1.0, 1.0, 1.0)
WHITE_90 = (1.0, 1.0, 1.0, 0.90)
WHITE_60 = (1.0, 1.0, 1.0, 0.60)
WHITE_25 = (1.0, 1.0, 1.0, 0.25)

_TOP_BAR_COLORS = [COLOR_GOLD, "#C0C0C0", "#CD7F32"] + [COLOR_SKY] * 7
_PROFANITY_CMAP = LinearSegmentedColormap.from_list("profanity", [COLOR_CRIMSON, "#FF8C00"])
_NEON_PALETTE = [
    COLOR_SKY,
    COLOR_CORAL,
    COLOR_NEON_PURP,
    COLOR_GOLD,
    COLOR_CRIMSON,
    "#22D3EE",
    "#FB923C",
    "#34D399",
    "#F472B6",
    "#818CF8",
]


def _register_ubuntu_font() -> None:
    """Make Ubuntu available to matplotlib so chart labels match the PDF body font."""
    ubuntu_dir = assets_dir() / "fonts" / "Ubuntu"
    if not ubuntu_dir.is_dir():
        return
    for ttf in ubuntu_dir.glob("Ubuntu-*.ttf"):
        font_manager.fontManager.addfont(str(ttf))
    plt.rcParams["font.family"] = "Ubuntu"


_register_ubuntu_font()


def _style_axes(ax: plt.Axes, label_color: tuple[float, ...] = WHITE_90) -> None:
    """Strip frame, white tick labels — designed for dark backdrop."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=label_color, which="both", length=0)
    for lbl in (*ax.get_xticklabels(), *ax.get_yticklabels()):
        lbl.set_color(label_color)
    ax.xaxis.label.set_color(label_color)
    ax.yaxis.label.set_color(label_color)
    ax.title.set_color(label_color)
    ax.grid(False)


def _save_transparent(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=_DPI, transparent=True, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)


_LABEL_WRAP_WIDTH = 12


def _name(analytics: dict[str, Any], uid: str) -> str:
    for p in analytics["participants"]:
        if p["id"] == uid:
            return p["display_name"]
    return uid


def _wrap_label(name: str, width: int = _LABEL_WRAP_WIDTH) -> str:
    """Wrap a display name onto multiple lines if it exceeds *width* chars."""
    if len(name) <= width:
        return name
    parts = name.split()
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = part
    if current:
        lines.append(current)
    return "\n".join(lines) if lines else name


def _placeholder(path: Path, text: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 3))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=14, color=WHITE_60)
    ax.set_axis_off()
    _save_transparent(fig, path)


# ---- Chart 1: Monthly volume ----


def render_monthly_volume(analytics: dict[str, Any], charts_dir: Path) -> Path:
    """Line chart of monthly message volume for the last 3 years."""
    monthly = analytics["monthly_volume"]
    now = datetime.fromisoformat(analytics["generated_at"])
    current_year = now.year
    current_month = now.month
    current_day = max(now.day, 1)

    fig, ax = plt.subplots(figsize=(9, 4.0))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    year_keys = sorted(monthly.keys())[-3:]
    n_years = len(year_keys)
    for i, year in enumerate(year_keys):
        values = monthly[year]
        alpha = 1.0 if n_years == 1 else 0.35 + 0.65 * (i / max(n_years - 1, 1))
        is_current = int(year) == current_year
        color = COLOR_HERO if is_current else COLOR_SKY

        if is_current:
            display_values, forecast_value = _forecast_current_year(values, current_month, current_day, current_year)
            (line,) = ax.plot(
                MONTHS,
                display_values,
                label=year,
                marker="o",
                color=color,
                alpha=alpha,
                linewidth=3.5,
                markersize=7,
                markeredgewidth=0,
                zorder=5,
            )
            line.set_path_effects(
                [
                    path_effects.Stroke(linewidth=9, foreground=color, alpha=0.35),
                    path_effects.Normal(),
                ]
            )
            ax.plot(
                [MONTHS[current_month - 1]],
                [forecast_value],
                marker="o",
                markerfacecolor="none",
                markeredgecolor=color,
                markeredgewidth=2.5,
                markersize=12,
                linestyle="None",
                zorder=6,
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
    ax.margins(x=0.02)
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=n_years,
        frameon=False,
        labelcolor=WHITE_100,
        fontsize=10,
        handlelength=1.6,
        columnspacing=2.0,
        borderaxespad=0.0,
    )
    _style_axes(ax, label_color=WHITE_100)

    path = charts_dir / "monthly_volume.png"
    _save_transparent(fig, path)
    return path


def _forecast_current_year(
    values: list[int],
    current_month: int,
    current_day: int,
    current_year: int,
) -> tuple[list[float], int]:
    """Return (12-element series, current-month forecast)."""
    days_in_month = calendar.monthrange(current_year, current_month)[1]
    actual = values[current_month - 1]
    forecast = int(round(actual * days_in_month / current_day))
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


# ---- Chart 2: Heavy hitters (top 10 users) ----


def render_user_share_top10(analytics: dict[str, Any], charts_dir: Path) -> Path:
    """Horizontal bar chart of top 10 users by message count."""
    share = analytics["share_by_user"]
    total = analytics["totals"]["messages_all_time"]
    sorted_users = sorted(share.items(), key=lambda x: x[1], reverse=True)[:10]

    if not sorted_users:
        path = charts_dir / "user_share_top10.png"
        _placeholder(path, "No active users")
        return path

    names = [_name(analytics, uid) for uid, _ in sorted_users]
    counts = [int(frac * total) for _, frac in sorted_users]
    colors = _TOP_BAR_COLORS[: len(sorted_users)]

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    y_pos = range(len(names))
    bars = ax.barh(
        [n[:20] for n in reversed(names)],
        list(reversed(counts)),
        color=list(reversed(colors)),
        edgecolor="none",
        height=0.6,
    )
    for bar, count in zip(bars, reversed(counts), strict=False):
        ax.text(
            bar.get_width() + max(counts) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"{count:,}",
            va="center",
            ha="left",
            color=WHITE_100,
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xlabel("Messages")
    ax.xaxis.grid(True, linestyle="-", linewidth=0.4, color=WHITE_25, alpha=1.0)
    ax.set_axisbelow(True)
    _style_axes(ax, label_color=WHITE_100)

    path = charts_dir / "user_share_top10.png"
    _save_transparent(fig, path)
    return path


# ---- Chart 3: Activity heatmap ----


def render_activity_heatmap(analytics: dict[str, Any], charts_dir: Path) -> Path:
    """7x24 heatmap of group activity."""
    heatmap = analytics["activity_heatmap"]
    matrix = heatmap["matrix"]
    days = heatmap["days"]

    cmap = LinearSegmentedColormap.from_list(
        "activity_neon",
        [
            (0.00, (0.12, 0.23, 0.54, 0.0)),
            (0.15, (0.22, 0.49, 0.97, 0.55)),
            (0.55, (0.75, 0.30, 0.97, 0.85)),
            (1.00, (1.00, 0.10, 0.42, 1.0)),
        ],
    )

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    im = ax.imshow(matrix, aspect="auto", cmap=cmap, interpolation="nearest")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)], fontsize=10)
    ax.set_yticks(range(7))
    ax.set_yticklabels(days, fontsize=10)
    ax.set_xlabel("Hour of day", fontsize=10)

    cbar = fig.colorbar(im, ax=ax, label="Messages", pad=0.02, shrink=0.85)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(colors=WHITE_100, length=0, labelsize=9)
    for lbl in cbar.ax.get_yticklabels():
        lbl.set_color(WHITE_100)
    cbar.ax.yaxis.label.set_color(WHITE_100)

    _style_axes(ax, label_color=WHITE_100)

    path = charts_dir / "activity_heatmap.png"
    _save_transparent(fig, path)
    return path


# ---- Chart 4: Reply network ----


def render_reply_network(analytics: dict[str, Any], charts_dir: Path) -> Path:
    """Directed graph of reply interactions — circular layout, color-coded edges."""
    path = charts_dir / "reply_network.png"
    matrix = analytics["reply_matrix"]
    if not matrix:
        _placeholder(path, "No reply data")
        return path

    g = nx.DiGraph()
    for sender, targets in matrix.items():
        for recipient, count in targets.items():
            g.add_edge(sender, recipient, weight=count)

    min_network_nodes = 2
    if len(g.nodes) < min_network_nodes:
        _placeholder(path, "Not enough reply data")
        return path

    fig, ax = plt.subplots(figsize=(10, 10))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    pos = nx.circular_layout(g)

    node_colors = [_NEON_PALETTE[i % len(_NEON_PALETTE)] for i in range(len(g.nodes))]
    node_sizes = []
    for node in g.nodes:
        degree = g.in_degree(node, weight="weight") + g.out_degree(node, weight="weight")
        node_sizes.append(max(500, min(4000, degree * 10)))

    nx.draw_networkx_nodes(
        g,
        pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        alpha=0.90,
        edgecolors="white",
        linewidths=2.0,
    )

    edges = list(g.edges(data=True))
    if edges:
        weights = [d["weight"] for _, _, d in edges]
        max_w = max(weights) if weights else 1
        edge_cmap = LinearSegmentedColormap.from_list("edge_heat", [COLOR_SKY, COLOR_NEON_PURP, COLOR_CORAL])

        for u, v, d in edges:
            norm_w = d["weight"] / max_w
            width = 1.0 + norm_w * 6.0
            alpha = 0.35 + norm_w * 0.60
            color = edge_cmap(norm_w)
            nx.draw_networkx_edges(
                g,
                pos,
                ax=ax,
                edgelist=[(u, v)],
                width=width,
                alpha=alpha,
                edge_color=[color],
                arrows=True,
                arrowsize=18,
                arrowstyle="-|>",
                connectionstyle="arc3,rad=0.15",
                min_source_margin=20,
                min_target_margin=20,
            )

    labels = {node: _name(analytics, node)[:15] for node in g.nodes}
    nx.draw_networkx_labels(
        g,
        pos,
        labels,
        ax=ax,
        font_size=10,
        font_color="white",
        font_weight="bold",
        font_family="Ubuntu",
    )

    if len(edges) >= _MIN_EDGES_FOR_LABELS:
        sorted_edges = sorted(edges, key=lambda e: e[2]["weight"])
        labeled_edges = sorted_edges[:3] + sorted_edges[-3:]
    elif edges:
        labeled_edges = edges
    else:
        labeled_edges = []

    for u, v, d in labeled_edges:
        is_strong = d["weight"] >= sorted_edges[-3][2]["weight"] if len(edges) >= _MIN_EDGES_FOR_LABELS else True
        mid_x = (pos[u][0] + pos[v][0]) / 2
        mid_y = (pos[u][1] + pos[v][1]) / 2
        offset_x = (pos[v][1] - pos[u][1]) * 0.08
        offset_y = (pos[u][0] - pos[v][0]) * 0.08
        label_color = COLOR_HERO if is_strong else COLOR_CORAL
        ax.text(
            mid_x + offset_x,
            mid_y + offset_y,
            str(d["weight"]),
            ha="center",
            va="center",
            fontsize=8,
            fontweight="bold",
            color=label_color,
            path_effects=[
                path_effects.Stroke(linewidth=3, foreground=(0, 0, 0, 0.7)),
                path_effects.Normal(),
            ],
        )

    ax.set_axis_off()
    _save_transparent(fig, path)
    return path


# ---- Chart 5: Profanity podium ----


def render_profanity_podium(analytics: dict[str, Any], charts_dir: Path) -> Path:
    """Vertical bar chart of top users by profanity rate."""
    path = charts_dir / "profanity_podium.png"
    rates = analytics["profanity_analytics"]["user_rates"]
    sorted_users = sorted(
        ((uid, data) for uid, data in rates.items() if data["profanity_percentage"] > 0),
        key=lambda x: x[1]["profanity_percentage"],
        reverse=True,
    )[:10]

    if not sorted_users:
        _placeholder(path, "No profanity detected")
        return path

    names = [_wrap_label(_name(analytics, uid)) for uid, _ in sorted_users]
    pcts = [d["profanity_percentage"] for _, d in sorted_users]

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    n = len(names)
    colors = [_PROFANITY_CMAP(i / max(n - 1, 1)) for i in range(n)]

    bars = ax.bar(names, pcts, color=colors, edgecolor="none", width=0.6)
    for bar, pct in zip(bars, pcts, strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.1,
            f"{pct:.1f}%",
            ha="center",
            va="bottom",
            color=WHITE_100,
            fontsize=10,
            fontweight="bold",
        )

    ax.set_ylabel("Profanity Rate (%)")
    ax.yaxis.grid(True, linestyle="-", linewidth=0.4, color=WHITE_25, alpha=1.0)
    ax.set_axisbelow(True)
    plt.xticks(rotation=30, ha="right")
    _style_axes(ax, label_color=WHITE_100)

    _save_transparent(fig, path)
    return path


# ---- Chart 6: Word cloud ----


def render_word_cloud(
    word_counts: Counter,
    per_user_counts: dict[str, Counter],
    analytics: dict[str, Any],
    charts_dir: Path,
) -> Path:
    """Group frequency word cloud, colored by dominant user per word."""
    path = charts_dir / "word_cloud.png"
    if not word_counts:
        _placeholder(path, "No words to display")
        return path

    users_ranked = sorted(per_user_counts.keys(), key=lambda u: sum(per_user_counts[u].values()), reverse=True)[:8]
    user_color_map: dict[str, str] = {}
    for i, uid in enumerate(users_ranked):
        user_color_map[uid] = _NEON_PALETTE[i % len(_NEON_PALETTE)]

    word_owner: dict[str, str] = {}
    for word in word_counts:
        best_uid = max(
            (uid for uid in per_user_counts if word in per_user_counts[uid]),
            key=lambda u: per_user_counts[u][word],
            default=None,
        )
        word_owner[word] = best_uid or ""

    def color_func(word: str, **_) -> str:
        uid = word_owner.get(word, "")
        return user_color_map.get(uid, "#AAAAAA")

    wc = WordCloud(
        width=2000,
        height=900,
        background_color=None,
        mode="RGBA",
        color_func=color_func,
        prefer_horizontal=0.9,
        max_words=200,
    )
    wc.generate_from_frequencies(dict(word_counts))

    fig, ax = plt.subplots(figsize=(18, 10))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))
    ax.imshow(wc, interpolation="bilinear")
    ax.set_axis_off()

    legend_handles = []
    for uid in users_ranked:
        color = user_color_map[uid]
        label = _name(analytics, uid)[:18]
        handle = plt.Line2D([0], [0], marker="s", color="none", markerfacecolor=color, markersize=10, label=label)
        legend_handles.append(handle)

    if legend_handles:
        fig.legend(
            handles=legend_handles,
            loc="lower center",
            ncol=min(len(legend_handles), 4),
            frameon=False,
            fontsize=11,
            labelcolor="white",
            handletextpad=0.5,
            columnspacing=2.0,
            borderaxespad=0.0,
        )
        fig.subplots_adjust(bottom=0.08)

    _save_transparent(fig, path)
    return path


# ---- Chart 7: Yearly volume (stacked bar for current year) ----


def render_yearly_volume(analytics: dict[str, Any], charts_dir: Path) -> Path:
    """Bar chart of total messages per year, current year stacked actuals + forecast."""
    monthly = analytics["monthly_volume"]
    now = datetime.fromisoformat(analytics["generated_at"])
    current_year = now.year
    current_month = now.month
    current_day = max(now.day, 1)

    path = charts_dir / "yearly_volume.png"
    if not monthly:
        _placeholder(path, "No data")
        return path

    years = sorted(monthly.keys())
    actuals: list[int] = []
    forecasts: list[int] = []

    for y_str in years:
        values = monthly[y_str]
        y = int(y_str)
        if y == current_year:
            actual_total = sum(values[: current_month - 1]) + values[current_month - 1]
            days_in_month = calendar.monthrange(current_year, current_month)[1]
            current_month_forecast = int(round(values[current_month - 1] * days_in_month / current_day))
            remaining_months_avg = (
                sum(values[: current_month - 1]) / max(current_month - 1, 1)
                if current_month > 1
                else current_month_forecast
            )
            forecast_remainder = current_month_forecast - values[current_month - 1]
            forecast_remainder += int(remaining_months_avg * (12 - current_month))
            actuals.append(actual_total)
            forecasts.append(max(forecast_remainder, 0))
        else:
            actuals.append(sum(values))
            forecasts.append(0)

    fig, ax = plt.subplots(figsize=(9, 2.8))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    x = range(len(years))
    bar_colors = [COLOR_HERO if int(y) == current_year else COLOR_SKY for y in years]

    bars_actual = ax.bar(x, actuals, color=bar_colors, edgecolor="none", width=0.55, label="Actual")
    bars_forecast = ax.bar(
        x,
        forecasts,
        bottom=actuals,
        color=[COLOR_HERO + "55" if int(y) == current_year else COLOR_SKY for y in years],
        edgecolor=[COLOR_HERO if int(y) == current_year else "none" for y in years],
        linewidth=[1.5 if int(y) == current_year else 0 for y in years],
        width=0.55,
        label="Forecast",
    )

    for bar_a, bar_f, y_str in zip(bars_actual, bars_forecast, years, strict=False):
        total = bar_a.get_height() + bar_f.get_height()
        ax.text(
            bar_a.get_x() + bar_a.get_width() / 2,
            total + max(actuals) * 0.02,
            f"{int(total):,}",
            ha="center",
            va="bottom",
            color=WHITE_100,
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xticks(list(x))
    ax.set_xticklabels(years, fontsize=10)
    ax.set_ylabel("Messages")
    ax.yaxis.grid(True, linestyle="-", linewidth=0.4, color=WHITE_25, alpha=1.0)
    ax.set_axisbelow(True)
    ax.margins(x=0.15)
    _style_axes(ax, label_color=WHITE_100)

    _save_transparent(fig, path)
    return path


# ---- Chart 8: Sentiment flow ----


def render_sentiment_flow(analytics: dict[str, Any], charts_dir: Path) -> Path:
    """Area chart of monthly engagement score (avg text length x message count)."""
    path = charts_dir / "sentiment_flow.png"
    flow = analytics["sentiment_flow"]
    if not flow:
        _placeholder(path, "No text data")
        return path

    months_sorted = sorted(flow.keys())
    labels = months_sorted
    scores = [flow[m]["engagement_score"] for m in months_sorted]

    fig, ax = plt.subplots(figsize=(9, 3.5))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((0, 0, 0, 0))

    ax.fill_between(range(len(labels)), scores, alpha=0.4, color=COLOR_NEON_PURP)
    ax.plot(range(len(labels)), scores, color=COLOR_NEON_PURP, linewidth=2.5, alpha=0.9)

    n_ticks = min(12, len(labels))
    if n_ticks > 0:
        step = max(1, len(labels) // n_ticks)
        tick_pos = list(range(0, len(labels), step))
        ax.set_xticks(tick_pos)
        ax.set_xticklabels([labels[i] for i in tick_pos], rotation=45, ha="right", fontsize=8)

    ax.set_ylabel("Engagement")
    ax.yaxis.grid(True, linestyle="-", linewidth=0.4, color=WHITE_25, alpha=1.0)
    ax.set_axisbelow(True)
    ax.margins(x=0.02)
    _style_axes(ax, label_color=WHITE_100)

    _save_transparent(fig, path)
    return path
