"""Splitting one recording into the separate meetings it actually contains.

Leaving a recorder running across a morning produces a single file holding
several unrelated meetings. Three signals identify the seams, in order of trust:

1. Calendar events overlapping the recording -- authoritative when available,
   since they carry real boundaries, titles, and attendees.
2. Silence gaps between speech, which is where meetings almost always break.
3. The LLM, which decides whether a given gap is a genuine change of meeting or
   just a pause, and names whatever segments come out.

Each signal degrades to the next, so this works with no calendar and no API key
-- it just gets less precise.
"""

from datetime import timedelta
from itertools import pairwise

from .calendars import event_offsets
from .llm import complete_json, is_configured
from .segments import Meeting, Segment, format_timestamp

# A pause shorter than this is a lull in one meeting, not a boundary between two.
DEFAULT_GAP_SECONDS = 180

# Ignore stretches of speech too short to be a meeting in their own right.
DEFAULT_MIN_MEETING_SECONDS = 120

# Roughly four characters per token. Used to decide whether the whole transcript
# fits in one boundary-detection call, which is far more accurate than sampling.
CHARS_PER_TOKEN = 4
DEFAULT_BOUNDARY_TOKEN_BUDGET = 120_000

# Wording that tends to bracket a meeting. Deliberately generic: these only
# nominate a passage as worth showing the LLM, they never decide a split alone.
TRANSITION_PHRASES = (
    "thanks guys",
    "thanks everyone",
    "thank you everyone",
    "see you later",
    "see you next",
    "speak soon",
    "have a good",
    "have a great",
    "cheers guys",
    "bye bye",
    "good bye",
    "let's get started",
    "shall we start",
    "should we start",
    "can everyone hear",
    "can you hear me",
    "let's kick off",
    "welcome to",
    "joining us",
    "end the meeting",
    "wrap this up",
    "wrap it up",
    "that's it from",
    "any other business",
    "leave the call",
    "drop off",
    "next meeting",
)

BOUNDARY_SCHEMA = {
    "type": "object",
    "properties": {
        "meetings": {
            "type": "array",
            "description": "The distinct meetings found in the recording, in order.",
            "items": {
                "type": "object",
                "properties": {
                    "start_timestamp": {
                        "type": "string",
                        "description": "Start of this meeting as HH:MM:SS, taken from the "
                        "timeline markers provided.",
                    },
                    "title": {
                        "type": "string",
                        "description": "A specific 3-8 word title describing what this "
                        "meeting was about.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "One short sentence on why this is a separate meeting.",
                    },
                },
                "required": ["start_timestamp", "title"],
            },
        }
    },
    "required": ["meetings"],
}


def find_gaps(segments, min_gap=DEFAULT_GAP_SECONDS):
    """Return ``(gap_start, gap_end)`` pairs where speech pauses for ``min_gap``."""
    gaps = []
    for previous, current in pairwise(segments):
        if current.start - previous.end >= min_gap:
            gaps.append((previous.end, current.start))
    return gaps


def _split_at(segments, boundaries):
    """Group segments into buckets divided at the given boundary times."""
    ordered = sorted(boundaries)
    buckets = [[] for _ in range(len(ordered) + 1)]
    for segment in segments:
        index = 0
        while index < len(ordered) and segment.start >= ordered[index]:
            index += 1
        buckets[index].append(segment)
    return [bucket for bucket in buckets if bucket]


def _build_meetings(buckets):
    """Turn buckets of segments into ``Meeting`` objects."""
    meetings = []
    for index, bucket in enumerate(buckets, start=1):
        meetings.append(
            Meeting(
                index=index,
                start=bucket[0].start,
                end=bucket[-1].end,
                segments=bucket,
            )
        )
    return meetings


def _drop_short(meetings, minimum):
    """Merge away meetings too short to stand alone, keeping at least one."""
    if len(meetings) <= 1:
        return meetings
    kept = [meeting for meeting in meetings if meeting.duration >= minimum]
    if not kept:
        kept = [max(meetings, key=lambda meeting: meeting.duration)]
    for index, meeting in enumerate(kept, start=1):
        meeting.index = index
    return kept


def find_transition_cues(segments):
    """Find segments whose wording sounds like a meeting opening or closing.

    On back-to-back calls the recorder never stops, so meetings run together with
    no silence between them. What does survive is the language people use at a
    seam -- sign-offs, greetings, "shall we get started" -- and that is often the
    only acoustic-free evidence a boundary exists at all.
    """
    cues = []
    for index, segment in enumerate(segments):
        lowered = segment.text.lower()
        if any(phrase in lowered for phrase in TRANSITION_PHRASES):
            cues.append(index)
    return cues


def timeline_outline(segments, gaps, sample_seconds=120, snippet_chars=260):
    """Render a compact timeline of the recording for the LLM to reason over.

    Used when the full transcript is too large to send. Samples periodic
    snippets, plus the speech surrounding every silence gap and every transition
    cue -- the two places boundary evidence actually lives.
    """
    if not segments:
        return ""

    wanted = set()
    next_sample = segments[0].start
    for segment in segments:
        if segment.start >= next_sample:
            wanted.add(id(segment))
            next_sample = segment.start + sample_seconds

    def widen(index, before=2, after=3):
        for neighbour in segments[max(index - before, 0) : index + after]:
            wanted.add(id(neighbour))

    gap_starts = {gap[0] for gap in gaps}
    gap_ends = {gap[1] for gap in gaps}
    for index, segment in enumerate(segments):
        if segment.end in gap_starts or segment.start in gap_ends:
            widen(index)
    for index in find_transition_cues(segments):
        widen(index)

    lines = []
    previous_end = None
    for segment in segments:
        if id(segment) not in wanted:
            continue
        if previous_end is not None and segment.start - previous_end >= DEFAULT_GAP_SECONDS:
            minutes = (segment.start - previous_end) / 60
            lines.append(f"--- SILENCE GAP of {minutes:.1f} minutes ---")
        lines.append(f"[{format_timestamp(segment.start)}] {segment.text[:snippet_chars]}")
        previous_end = segment.end
    return "\n".join(lines)


def _parse_timestamp(value):
    """Parse ``HH:MM:SS`` (or ``MM:SS``) into seconds, or None if malformed."""
    try:
        parts = [int(part) for part in str(value).strip().split(":")]
    except (ValueError, AttributeError):
        return None
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return None


def _boundaries_from_calendar(events, recording_start, segments):
    """Derive split points from calendar events overlapping the recording.

    Returns ``(boundaries, titles_by_start)``. A boundary is only kept when the
    event actually starts inside the recording and there is speech near it, so a
    declined or never-recorded invite does not manufacture an empty meeting.
    """
    if not events or recording_start is None or not segments:
        return [], {}

    recording_end = segments[-1].end
    boundaries = []
    titles = {}
    for event in events:
        start_offset, _ = event_offsets(event, recording_start)
        # An event already under way when recording began titles the first
        # meeting rather than splitting the recording.
        if start_offset <= 60:
            titles.setdefault(0.0, event)
            continue
        if start_offset >= recording_end:
            continue
        nearest = min(segments, key=lambda seg: abs(seg.start - start_offset))
        if abs(nearest.start - start_offset) > 600:
            continue  # no speech within 10 minutes: the meeting was not recorded
        boundaries.append(nearest.start)
        titles[nearest.start] = event
    return boundaries, titles


def _boundary_input(segments, gaps, config):
    """Return the transcript view to reason over, preferring the full text.

    Boundaries between back-to-back meetings are often a single sentence
    ("thanks everyone" / "right, next one"), which sampling can miss entirely.
    Send the whole transcript whenever it fits the budget; only fall back to a
    sampled outline for recordings too long for one call.
    """
    budget = int(config.get("boundary_token_budget", DEFAULT_BOUNDARY_TOKEN_BUDGET))
    full = "\n".join(f"[{format_timestamp(segment.start)}] {segment.text}" for segment in segments)
    if len(full) <= budget * CHARS_PER_TOKEN:
        return full
    return timeline_outline(segments, gaps)


def _llm_boundaries(segments, gaps, config, calendar_events):
    """Ask the LLM where the recording changes from one meeting to the next."""
    outline = _boundary_input(segments, gaps, config)
    if not outline:
        return None

    calendar_hint = ""
    if calendar_events:
        listed = "\n".join(
            f"- {event['title']} ({event['start']} to {event['end']})" for event in calendar_events
        )
        calendar_hint = (
            "\n\nCalendar events overlapping this recording (strong evidence for how "
            f"many meetings there are and what they were called):\n{listed}"
        )

    gap_hint = (
        "\n".join(
            f"- gap from {format_timestamp(start)} to {format_timestamp(end)} "
            f"({(end - start) / 60:.1f} minutes)"
            for start, end in gaps
        )
        or "- none"
    )

    system = (
        "You identify where one long recording contains several separate meetings.\n\n"
        "Evidence for a boundary:\n"
        "- People say goodbye, thank each other, and then a different conversation "
        "starts. Back-to-back calls often have no silence between them at all, so "
        "this wording is frequently the only signal.\n"
        "- The set of participants changes, or people re-introduce themselves.\n"
        "- The subject changes completely, with no reference back to what came before.\n"
        "- A long silence followed by an unrelated conversation.\n\n"
        "NOT a boundary: a pause for a demo or screen share, someone stepping away, "
        "a tangent, or moving to the next agenda item within the same meeting.\n\n"
        "Prefer fewer, larger meetings when the evidence is weak. Every "
        "start_timestamp must be copied verbatim from a [HH:MM:SS] marker in the "
        "transcript, and the first meeting must start at 00:00:00."
    )
    user = (
        f"Below is a transcript of one recording, timestamped from its start.\n\n"
        f"Silence gaps found:\n{gap_hint}{calendar_hint}\n\n"
        f"Transcript:\n{outline}\n\n"
        "Identify each distinct meeting, giving its start timestamp and a specific "
        "title describing its actual subject."
    )

    # The answer itself is tiny, but reasoning models bill their chain of
    # thought as completion tokens and return nothing at all if they run out.
    result = complete_json(
        config,
        system,
        user,
        BOUNDARY_SCHEMA,
        max_tokens=int(config.get("boundary_max_tokens", 8000)),
    )
    if not result or not result.get("meetings"):
        return None

    found = []
    for entry in result["meetings"]:
        seconds = _parse_timestamp(entry.get("start_timestamp"))
        if seconds is not None:
            found.append((seconds, entry.get("title")))
    return sorted(found) or None


def split_into_meetings(segments, config=None, calendar_events=None, recording_start=None):
    """Split transcript segments into the meetings they represent.

    Always returns at least one meeting. When splitting is disabled, or there is
    nothing to split on, the whole recording comes back as a single meeting.
    """
    config = config or {}
    if not segments:
        return []

    min_meeting = float(config.get("min_meeting_seconds", DEFAULT_MIN_MEETING_SECONDS))

    if not config.get("split_meetings", True):
        return _build_meetings([list(segments)])

    gaps = find_gaps(segments, float(config.get("meeting_gap_seconds", DEFAULT_GAP_SECONDS)))

    # 1. Calendar boundaries win when we have them.
    calendar_boundaries, calendar_titles = _boundaries_from_calendar(
        calendar_events, recording_start, segments
    )

    # 2. Otherwise ask the LLM to judge the candidate gaps.
    llm_titles = {}
    boundaries = list(calendar_boundaries)
    if not boundaries and is_configured(config):
        decided = _llm_boundaries(segments, gaps, config, calendar_events)
        if decided:
            for seconds, title in decided:
                if seconds > 0:
                    boundaries.append(seconds)
                llm_titles[seconds] = title

    # 3. With neither, fall back to the raw silence gaps.
    if not boundaries and not is_configured(config):
        boundaries = [gap[1] for gap in gaps]

    meetings = _drop_short(_build_meetings(_split_at(segments, boundaries)), min_meeting)

    # Attach whatever titles and attendees the evidence gave us.
    for meeting in meetings:
        event = _nearest_value(calendar_titles, meeting.start)
        if event:
            meeting.title = event["title"]
            meeting.attendees = list(event.get("attendees") or [])
            meeting.calendar_event = event
        else:
            title = _nearest_value(llm_titles, meeting.start)
            if title:
                meeting.title = title
    return meetings


def _nearest_value(mapping, target, tolerance=120):
    """Look up ``mapping`` by the key closest to ``target`` within ``tolerance``."""
    if not mapping:
        return None
    key = min(mapping, key=lambda candidate: abs(candidate - target))
    return mapping[key] if abs(key - target) <= tolerance else None


def meeting_clock_time(meeting, recording_start):
    """Wall-clock start time of a meeting, or None without a recording start."""
    if recording_start is None:
        return None
    return recording_start + timedelta(seconds=meeting.start)


__all__ = [
    "Meeting",
    "Segment",
    "find_gaps",
    "meeting_clock_time",
    "split_into_meetings",
    "timeline_outline",
]
