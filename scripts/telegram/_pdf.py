"""ReportLab PDF generation for chat_analysis."""

from datetime import timedelta
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

PAGE_MARGIN = 1.6 * cm
TWO_PARTICIPANTS = 2
# Length-comparison threshold: only call out a difference if it exceeds 5%.
LENGTH_DIFF_THRESHOLD = 0.05


def render_pdf(analytics: dict[str, Any], chart_paths: dict[str, Path], out_path: Path) -> Path:
    """Write the multi-page PDF report to ``out_path``."""
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title=f"Chat analytics — {analytics['source']['chat_name']}",
    )
    styles = _styles()
    story: list[Any] = []
    _page_headline(story, styles, analytics, chart_paths)
    _page_who_talks_more(story, styles, analytics, chart_paths)
    _page_when_you_talk(story, styles, analytics, chart_paths)
    _page_dynamics(story, styles, analytics, chart_paths)
    _page_style(story, styles, analytics)
    _page_streaks(story, styles, analytics)
    _page_word_cloud(story, styles, analytics, chart_paths)
    _page_emoji(story, styles, analytics, chart_paths)
    doc.build(story)
    return out_path


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontSize=24,
            leading=28,
            spaceAfter=14,
            textColor=colors.HexColor("#1a1a1a"),
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=16,
            spaceBefore=10,
            spaceAfter=8,
            textColor=colors.HexColor("#333333"),
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontSize=11,
            leading=15,
            spaceAfter=8,
            textColor=colors.HexColor("#222222"),
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base["BodyText"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#555555"),
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#888888"),
        ),
    }


def _name(analytics: dict[str, Any], uid: str) -> str:
    for p in analytics["participants"]:
        if p["id"] == uid:
            return p["display_name"]
    return uid


def _user_ids(analytics: dict[str, Any]) -> tuple[str, str | None]:
    ids = [p["id"] for p in analytics["participants"]]
    return ids[0], (ids[1] if len(ids) > 1 else None)


def _img(path: Path, max_width_cm: float = 17) -> Image:
    img = Image(str(path))
    iw, ih = img.imageWidth, img.imageHeight
    target_w = max_width_cm * cm
    scale = target_w / iw
    img.drawWidth = target_w
    img.drawHeight = ih * scale
    return img


def _page_headline(
    story: list[Any], styles: dict[str, ParagraphStyle], analytics: dict[str, Any], charts: dict[str, Path]
) -> None:
    totals = analytics["totals"]
    name = analytics["source"]["chat_name"]
    story.append(Paragraph(f"Chat recap — {name}", styles["title"]))
    blurb = (
        f"You've exchanged <b>{totals['messages_all_time']:,}</b> messages over time "
        f"(an average of <b>{totals['avg_messages_per_day']}</b> each day) "
        f"and <b>{totals['messages_ytd']:,}</b> so far this year!"
    )
    story.append(Paragraph(blurb, styles["body"]))
    if totals["date_range"]["start"]:
        story.append(
            Paragraph(
                f"From <b>{totals['date_range']['start']}</b> to <b>{totals['date_range']['end']}</b> "
                f"({totals['date_range']['days']:,} days).",
                styles["caption"],
            )
        )
    story.append(Spacer(1, 0.4 * cm))
    if "monthly_volume" in charts:
        story.append(_img(charts["monthly_volume"]))
    story.append(_footer(styles))
    story.append(PageBreak())


def _page_who_talks_more(
    story: list[Any], styles: dict[str, ParagraphStyle], analytics: dict[str, Any], charts: dict[str, Path]
) -> None:
    share = analytics["share_by_user"]
    avg = analytics["avg_messages_per_month_by_user"]
    story.append(Paragraph("Who talks more", styles["title"]))
    sorted_share = sorted(share.items(), key=lambda kv: -kv[1])
    if sorted_share:
        top_uid, top_share = sorted_share[0]
        story.append(
            Paragraph(
                f"<b>{_name(analytics, top_uid)}</b> drives the conversation, "
                f"having sent <b>{top_share:.0%}</b> of all messages.",
                styles["body"],
            )
        )
    if len(avg) >= TWO_PARTICIPANTS:
        ids = list(avg.keys())
        story.append(
            Paragraph(
                f"In an average month, <b>{_name(analytics, ids[0])}</b> sent "
                f"<b>{int(avg[ids[0]])}</b> messages. "
                f"<b>{_name(analytics, ids[1])}</b> strikes back with <b>{int(avg[ids[1]])}</b>.",
                styles["body"],
            )
        )
    if "message_share" in charts:
        story.append(_img(charts["message_share"], max_width_cm=12))
    story.append(_footer(styles))
    story.append(PageBreak())


def _page_when_you_talk(
    story: list[Any], styles: dict[str, ParagraphStyle], analytics: dict[str, Any], charts: dict[str, Path]
) -> None:
    story.append(Paragraph("When you talk", styles["title"]))
    story.append(
        Paragraph(
            "Each cell is the total number of messages sent during that hour-of-day, across all the days you chatted.",
            styles["body"],
        )
    )
    if "activity_heatmap" in charts:
        story.append(_img(charts["activity_heatmap"]))
    story.append(_footer(styles))
    story.append(PageBreak())


def _page_dynamics(
    story: list[Any], styles: dict[str, ParagraphStyle], analytics: dict[str, Any], charts: dict[str, Path]
) -> None:
    init = analytics["initiation_share"]
    latency = analytics["reply_latency_seconds"]
    dt = analytics["double_text_rate"]
    story.append(Paragraph("Conversation dynamics", styles["title"]))

    init_pairs = [(uid, frac) for uid, frac in init.items() if uid != "sessions_total"]
    if init_pairs:
        top_uid, top_frac = max(init_pairs, key=lambda kv: kv[1])
        story.append(
            Paragraph(
                f"<b>{_name(analytics, top_uid)}</b> initiated <b>{top_frac:.0%}</b> "
                f"of the {init.get('sessions_total', 0):,} sessions.",
                styles["body"],
            )
        )

    if latency:
        for uid, stats in latency.items():
            story.append(
                Paragraph(
                    f"<b>{_name(analytics, uid)}</b> replies in a median of "
                    f"<b>{_format_seconds(stats['median'])}</b> "
                    f"(mean {_format_seconds(stats['mean'])}, p90 {_format_seconds(stats['p90'])}, "
                    f"{stats['samples']:,} samples).",
                    styles["body"],
                )
            )

    dt_pairs = [(uid, info["share"], info["count"]) for uid, info in dt.items()]
    dt_pairs.sort(key=lambda t: -t[1])
    if dt_pairs and dt_pairs[0][2] > 0:
        top_uid, top_share, top_count = dt_pairs[0]
        story.append(
            Paragraph(
                f"Cringe: <b>{_name(analytics, top_uid)}</b> accounted for "
                f"<b>{top_share:.0%}</b> of all double-texts ({top_count:,} in total).",
                styles["body"],
            )
        )

    if "reply_latency" in charts:
        story.append(_img(charts["reply_latency"]))
    story.append(_footer(styles))
    story.append(PageBreak())


def _page_style(story: list[Any], styles: dict[str, ParagraphStyle], analytics: dict[str, Any]) -> None:
    length = analytics["median_message_length"]
    vocab = analytics["vocabulary_richness"]
    links = analytics["external_links"]
    story.append(Paragraph("Style", styles["title"]))

    ids = list(length.keys())
    if len(ids) == TWO_PARTICIPANTS:
        a, b = ids
        ratio = ""
        if length[b]["chars"] > 0:
            diff = (length[a]["chars"] - length[b]["chars"]) / length[b]["chars"]
            if diff > LENGTH_DIFF_THRESHOLD:
                ratio = f" — {abs(diff):.0%} longer than {_name(analytics, b)}"
            elif diff < -LENGTH_DIFF_THRESHOLD:
                ratio = f" — {abs(diff):.0%} shorter than {_name(analytics, b)}"
        story.append(
            Paragraph(
                f"<b>{_name(analytics, a)}</b>'s median message is "
                f"<b>{length[a]['chars']}</b> characters ({length[a]['words']} words){ratio}.",
                styles["body"],
            )
        )
        story.append(
            Paragraph(
                f"<b>{_name(analytics, b)}</b>'s median message is "
                f"<b>{length[b]['chars']}</b> characters ({length[b]['words']} words).",
                styles["body"],
            )
        )

    if len(ids) == TWO_PARTICIPANTS:
        a, b = ids
        story.append(
            Paragraph(
                f"Vocabulary richness — <b>{_name(analytics, a)}</b>: "
                f"<b>{vocab[a]['ratio']:.2%}</b> ({vocab[a]['unique']:,}/{vocab[a]['total']:,}). "
                f"<b>{_name(analytics, b)}</b>: <b>{vocab[b]['ratio']:.2%}</b> "
                f"({vocab[b]['unique']:,}/{vocab[b]['total']:,}).",
                styles["body"],
            )
        )

    by_user = links["by_user"]
    if by_user:
        sorted_links = sorted(by_user.items(), key=lambda kv: -kv[1])
        top_uid, top_count = sorted_links[0]
        story.append(
            Paragraph(
                f"<b>{_name(analytics, top_uid)}</b> shared <b>{top_count:,}</b> external links — "
                f"top domains: {', '.join(list(links['by_domain'].keys())[:5]) or '—'}.",
                styles["body"],
            )
        )
    story.append(_footer(styles))
    story.append(PageBreak())


def _page_streaks(story: list[Any], styles: dict[str, ParagraphStyle], analytics: dict[str, Any]) -> None:
    streaks = analytics["streaks"]
    story.append(Paragraph("Streaks", styles["title"]))
    silence = streaks["longest_silence"]
    if silence["days"]:
        story.append(
            Paragraph(
                f"Dry spell: <b>{silence['start']}</b> to <b>{silence['end']}</b>, "
                f"<b>{silence['days']:,}</b> days of silence.",
                styles["body"],
            )
        )
    else:
        story.append(Paragraph("No silence longer than one day — impressive.", styles["body"]))

    streak = streaks["longest_streak"]
    if streak["days"]:
        story.append(
            Paragraph(
                f"Hot streak: <b>{streak['start']}</b> to <b>{streak['end']}</b>, "
                f"<b>{streak['days']:,}</b> days of non-stop communication.",
                styles["body"],
            )
        )
    story.append(_footer(styles))
    story.append(PageBreak())


def _page_word_cloud(
    story: list[Any], styles: dict[str, ParagraphStyle], analytics: dict[str, Any], charts: dict[str, Path]
) -> None:
    story.append(Paragraph("Word cloud", styles["title"]))
    self_id, partner_id = _user_ids(analytics)
    legend = (
        f"<font color='#d83a3a'><b>Red</b></font> = primarily {_name(analytics, self_id)}, "
        f"<font color='#3a7ad8'><b>Blue</b></font> = primarily "
        f"{_name(analytics, partner_id) if partner_id else 'partner'}, "
        f"<font color='#8c5fb8'><b>Purple</b></font> = shared."
    )
    story.append(Paragraph(legend, styles["caption"]))
    if "word_cloud" in charts:
        story.append(_img(charts["word_cloud"]))
    story.append(_footer(styles))
    story.append(PageBreak())


def _page_emoji(
    story: list[Any], styles: dict[str, ParagraphStyle], analytics: dict[str, Any], charts: dict[str, Path]
) -> None:
    story.append(Paragraph("Emojis and stickers", styles["title"]))
    for uid, items in analytics["top_emojis"].items():
        top = ", ".join(f"{e['emoji']} ({e['count']})" for e in items[:8]) or "—"
        story.append(Paragraph(f"<b>{_name(analytics, uid)}</b>'s top emojis: {top}", styles["body"]))
    for uid, items in analytics["top_stickers"].items():
        top = ", ".join(f"{e['sticker_emoji']} ({e['count']})" for e in items[:8]) or "—"
        story.append(Paragraph(f"<b>{_name(analytics, uid)}</b>'s top stickers: {top}", styles["body"]))
    if "emoji_cloud" in charts:
        story.append(_img(charts["emoji_cloud"]))
    story.append(_footer(styles))


def _footer(styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(
        "Generated by Scriptorium · timestamps interpreted as the chat's local time.",
        styles["footer"],
    )


def _format_seconds(s: float) -> str:
    if s <= 0:
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
