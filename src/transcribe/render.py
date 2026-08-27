"""Rendering meeting notes to Markdown, HTML, and plain-text transcripts."""

import html
import re
from datetime import datetime

from .segments import format_timestamp

# Characters that cannot appear in a filename on macOS, plus the ones that make
# paths awkward to handle in shells and URLs.
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")


def safe_folder_name(title, fallback="Meeting", max_length=80):
    """Turn a meeting title into a filesystem-safe folder name."""
    cleaned = _UNSAFE_FILENAME.sub(" ", title or "")
    cleaned = _WHITESPACE.sub(" ", cleaned).strip(" .")
    if not cleaned:
        cleaned = fallback
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" .")
    return cleaned


def _decisions_by_status(notes):
    """Split decisions into aligned and unresolved buckets."""
    aligned, open_items = [], []
    for decision in notes.get("decisions") or []:
        if decision.get("status") == "needs_further_discussion":
            open_items.append(decision)
        else:
            aligned.append(decision)
    return aligned, open_items


def render_markdown(meeting, notes, recording_start=None, source_video=None):
    """Render meeting notes as Markdown."""
    title = notes.get("title") if notes else None
    title = title or meeting.title or f"Meeting {meeting.index}"
    lines = [f"# {title}", ""]

    meta = []
    if recording_start is not None:
        started = recording_start.timestamp() + meeting.start
        meta.append(f"**Date:** {datetime.fromtimestamp(started).strftime('%A, %d %B %Y, %H:%M')}")
    meta.append(f"**Duration:** {meeting.duration / 60:.0f} minutes")
    meta.append(
        f"**Position in recording:** {format_timestamp(meeting.start)}"
        f"-{format_timestamp(meeting.end)}"
    )
    if meeting.attendees:
        meta.append(f"**Invited:** {', '.join(meeting.attendees)}")
    speakers = meeting.speakers()
    if speakers:
        meta.append(f"**Speakers:** {', '.join(speakers)}")
    if source_video:
        meta.append(f"**Recording:** `{source_video}`")
    lines.extend(meta)
    lines.append("")

    if not notes:
        lines.append(
            "_No notes were generated for this meeting. The transcript is complete; "
            "check the run output for why, then re-run to fill this in._"
        )
        return "\n".join(lines) + "\n"

    if notes.get("summary"):
        lines += ["## Summary", "", notes["summary"], ""]

    for section in notes.get("sections") or []:
        lines += [f"### {section.get('heading', 'Untitled')}", "", section.get("body", ""), ""]

    aligned, open_items = _decisions_by_status(notes)
    if aligned or open_items:
        lines += ["## Decisions", ""]
        if aligned:
            lines += ["### Aligned", ""]
            for decision in aligned:
                lines.append(f"- **{decision.get('title')}** — {decision.get('detail')}")
            lines.append("")
        if open_items:
            lines += ["### Needs further discussion", ""]
            for decision in open_items:
                lines.append(f"- **{decision.get('title')}** — {decision.get('detail')}")
            lines.append("")

    next_steps = notes.get("next_steps") or []
    if next_steps:
        lines += ["## Next steps", ""]
        for step in next_steps:
            owner = step.get("owner") or "Unassigned"
            lines.append(f"- **[{owner}] {step.get('title')}** — {step.get('detail')}")
        lines.append("")

    details = notes.get("details") or []
    if details:
        lines += ["## Details", ""]
        for entry in details:
            stamps = " ".join(f"({stamp})" for stamp in entry.get("timestamps") or [])
            heading = entry.get("heading", "")
            body = entry.get("body", "")
            lines.append(f"- **{heading}:** {body} {stamps}".rstrip())
        lines.append("")

    lines += [
        "---",
        "",
        "_Transcribed locally with Whisper and summarized by an LLM. "
        "Check anything important against the recording._",
        "",
    ]
    return "\n".join(lines)


def render_transcript(meeting, with_speakers=True):
    """Render a readable timestamped transcript, grouping consecutive turns."""
    lines = []
    current_speaker = object()  # sentinel distinct from any real speaker or None
    for segment in meeting.segments:
        if with_speakers and segment.speaker != current_speaker:
            current_speaker = segment.speaker
            lines.append("")
            lines.append(f"{segment.speaker or 'Unknown speaker'}:")
        lines.append(f"[{format_timestamp(segment.start)}] {segment.text}")
    return "\n".join(lines).strip() + "\n"


_HTML_STYLES = """
:root {
  --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0;
  --accent: #1a56db; --chip-bg: #f6f8fa; --card: #f6f8fa;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #2f3742;
    --accent: #6b9fff; --chip-bg: #161b22; --card: #161b22;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2.5rem 1.25rem; background: var(--bg); color: var(--fg);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
main { max-width: 46rem; margin: 0 auto; }
h1 { font-size: 1.9rem; line-height: 1.25; margin: 0 0 .75rem; letter-spacing: -.02em; }
h2 {
  font-size: 1.15rem; margin: 2.25rem 0 .85rem; padding-bottom: .4rem;
  border-bottom: 1px solid var(--line); letter-spacing: -.01em;
}
h3 { font-size: 1rem; margin: 1.5rem 0 .5rem; }
p { margin: 0 0 .9rem; }
.meta {
  display: flex; flex-wrap: wrap; gap: .4rem;
  margin: 0 0 1.5rem; padding: 0; list-style: none;
}
.meta li {
  background: var(--chip-bg); border: 1px solid var(--line); border-radius: 999px;
  padding: .2rem .7rem; font-size: .8rem; color: var(--muted);
}
.summary {
  background: var(--card); border: 1px solid var(--line);
  border-radius: .6rem; padding: 1rem 1.15rem;
}
ul.items { list-style: none; padding: 0; margin: 0; }
ul.items li { padding: .55rem 0; border-bottom: 1px solid var(--line); }
ul.items li:last-child { border-bottom: 0; }
.owner {
  display: inline-block; background: var(--chip-bg); border: 1px solid var(--line);
  border-radius: .35rem; padding: .05rem .45rem; margin-right: .4rem;
  font-size: .8rem; color: var(--accent); font-weight: 600; white-space: nowrap;
}
.stamp {
  color: var(--muted); font-size: .82rem;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.name { font-weight: 600; }
footer { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--line);
         color: var(--muted); font-size: .82rem; }
"""


def render_html(meeting, notes, recording_start=None, source_video=None):
    """Render meeting notes as a self-contained, theme-aware HTML page."""
    esc = html.escape
    title = (notes.get("title") if notes else None) or meeting.title or f"Meeting {meeting.index}"

    chips = []
    if recording_start is not None:
        started = datetime.fromtimestamp(recording_start.timestamp() + meeting.start)
        chips.append(started.strftime("%a, %d %b %Y · %H:%M"))
    chips.append(f"{meeting.duration / 60:.0f} min")
    chips.append(f"{format_timestamp(meeting.start)}-{format_timestamp(meeting.end)}")
    for attendee in meeting.attendees:
        chips.append(attendee)

    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(title)}</title>",
        f"<style>{_HTML_STYLES}</style>",
        "</head><body><main>",
        f"<h1>{esc(title)}</h1>",
        '<ul class="meta">' + "".join(f"<li>{esc(str(chip))}</li>" for chip in chips) + "</ul>",
    ]

    if not notes:
        parts.append(
            "<p><em>No notes were generated for this meeting. The transcript is "
            "complete; check the run output for why, then re-run to fill this in.</em></p>"
        )
    else:
        if notes.get("summary"):
            parts.append(f'<div class="summary"><p>{esc(notes["summary"])}</p></div>')

        for section in notes.get("sections") or []:
            parts.append(f"<h3>{esc(section.get('heading', ''))}</h3>")
            parts.append(f"<p>{esc(section.get('body', ''))}</p>")

        aligned, open_items = _decisions_by_status(notes)
        if aligned or open_items:
            parts.append("<h2>Decisions</h2>")
            for label, group in (("Aligned", aligned), ("Needs further discussion", open_items)):
                if not group:
                    continue
                parts.append(f"<h3>{label}</h3><ul class='items'>")
                for decision in group:
                    parts.append(
                        f"<li><span class='name'>{esc(decision.get('title', ''))}</span> — "
                        f"{esc(decision.get('detail', ''))}</li>"
                    )
                parts.append("</ul>")

        next_steps = notes.get("next_steps") or []
        if next_steps:
            parts.append("<h2>Next steps</h2><ul class='items'>")
            for step in next_steps:
                owner = esc(step.get("owner") or "Unassigned")
                parts.append(
                    f"<li><span class='owner'>{owner}</span>"
                    f"<span class='name'>{esc(step.get('title', ''))}</span> — "
                    f"{esc(step.get('detail', ''))}</li>"
                )
            parts.append("</ul>")

        details = notes.get("details") or []
        if details:
            parts.append("<h2>Details</h2><ul class='items'>")
            for entry in details:
                stamps = " ".join(
                    f"<span class='stamp'>({esc(stamp)})</span>"
                    for stamp in entry.get("timestamps") or []
                )
                parts.append(
                    f"<li><span class='name'>{esc(entry.get('heading', ''))}</span> — "
                    f"{esc(entry.get('body', ''))} {stamps}</li>"
                )
            parts.append("</ul>")

    source_note = f" Source: <code>{esc(str(source_video))}</code>." if source_video else ""
    parts += [
        f"<footer>Transcribed locally with Whisper and summarized by an LLM. "
        f"Check anything important against the recording.{source_note}</footer>",
        "</main></body></html>",
    ]
    return "\n".join(parts)
