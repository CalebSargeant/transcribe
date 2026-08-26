"""Tests for splitting a recording into the meetings it contains."""

from datetime import datetime

import pytest

from transcribe import segmentation
from transcribe.segmentation import (
    find_gaps,
    find_transition_cues,
    split_into_meetings,
    timeline_outline,
)
from transcribe.segments import Segment, format_timestamp


def make_segments(spans):
    """Build segments from ``(start, end, text)`` triples."""
    return [Segment(start=s, end=e, text=t) for s, e, t in spans]


@pytest.fixture
def two_meetings():
    """Two meetings separated by a 10-minute silence."""
    return make_segments(
        [
            (0, 5, "morning everyone lets get started on the routing work"),
            (10, 20, "the camera subnets are still not reachable"),
            (630, 640, "hi all shall we start the budget review"),
            (650, 660, "we need to cut the cloud spend next quarter"),
        ]
    )


# --- format_timestamp -------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00:00"), (61, "00:01:01"), (3661, "01:01:01"), (-5, "00:00:00")],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


# --- find_gaps --------------------------------------------------------------


def test_find_gaps_returns_pauses_over_threshold(two_meetings):
    assert find_gaps(two_meetings, min_gap=180) == [(20, 630)]


def test_find_gaps_ignores_short_pauses(two_meetings):
    assert find_gaps(two_meetings, min_gap=900) == []


def test_find_gaps_on_empty_input():
    assert find_gaps([]) == []


# --- find_transition_cues ---------------------------------------------------


def test_find_transition_cues_spots_openings_and_closings():
    segments = make_segments(
        [
            (0, 5, "so the deploy went out fine"),
            (10, 15, "right thanks guys speak soon"),
            (20, 25, "ok can everyone hear me"),
            (30, 35, "the database migration is next"),
        ]
    )
    assert find_transition_cues(segments) == [1, 2]


def test_find_transition_cues_is_case_insensitive():
    segments = make_segments([(0, 5, "THANKS EVERYONE, bye")])
    assert find_transition_cues(segments) == [0]


# --- split_into_meetings ----------------------------------------------------


def test_split_disabled_returns_single_meeting(two_meetings):
    meetings = split_into_meetings(two_meetings, config={"split_meetings": False})
    assert len(meetings) == 1
    assert meetings[0].start == 0
    assert meetings[0].end == 660


def test_split_on_gaps_without_llm(two_meetings):
    """With no API key, silence gaps are the fallback signal."""
    config = {"meeting_gap_seconds": 180, "min_meeting_seconds": 1, "anthropic_api_key": ""}
    meetings = split_into_meetings(two_meetings, config=config)
    assert len(meetings) == 2
    assert (meetings[0].start, meetings[0].end) == (0, 20)
    assert (meetings[1].start, meetings[1].end) == (630, 660)
    assert [m.index for m in meetings] == [1, 2]


def test_split_drops_meetings_below_minimum(two_meetings):
    """A stretch too short to be a meeting is discarded, not kept as a stub."""
    config = {"meeting_gap_seconds": 180, "min_meeting_seconds": 25, "anthropic_api_key": ""}
    meetings = split_into_meetings(two_meetings, config=config)
    # Both candidate meetings are under 25s, so the longest one survives.
    assert len(meetings) == 1


def test_split_always_returns_at_least_one_meeting():
    segments = make_segments([(0, 5, "just a quick note")])
    meetings = split_into_meetings(segments, config={"anthropic_api_key": ""})
    assert len(meetings) == 1


def test_split_on_empty_segments_returns_nothing():
    assert split_into_meetings([], config={}) == []


def test_llm_boundaries_used_when_configured(monkeypatch, two_meetings):
    """With a key set, the LLM decides boundaries and supplies titles."""
    captured = {}

    def fake_complete_json(config, system, user, schema, **kwargs):
        captured["user"] = user
        return {
            "meetings": [
                {"start_timestamp": "00:00:00", "title": "Camera subnet routing"},
                {"start_timestamp": "00:10:30", "title": "Q3 cloud budget review"},
            ]
        }

    monkeypatch.setattr(segmentation, "complete_json", fake_complete_json)

    config = {"anthropic_api_key": "sk-ant", "min_meeting_seconds": 1}
    meetings = split_into_meetings(two_meetings, config=config)

    assert [m.title for m in meetings] == ["Camera subnet routing", "Q3 cloud budget review"]
    assert (meetings[0].start, meetings[1].start) == (0, 630)
    # The whole transcript is small, so it is sent in full rather than sampled.
    assert "budget review" in captured["user"]


def test_llm_failure_falls_back_to_single_meeting(monkeypatch, two_meetings):
    monkeypatch.setattr(segmentation, "complete_json", lambda *a, **k: None)
    meetings = split_into_meetings(two_meetings, config={"anthropic_api_key": "sk-ant"})
    assert len(meetings) == 1


def test_calendar_boundaries_take_priority(monkeypatch, two_meetings):
    """Calendar events outrank the LLM and carry titles plus attendees."""
    monkeypatch.setattr(
        segmentation,
        "complete_json",
        lambda *a, **k: pytest.fail("LLM should not be consulted when a calendar is available"),
    )
    recording_start = datetime(2026, 8, 25, 9, 0, 0)
    events = [
        {
            "title": "Network sync",
            "start": "2026-08-25T09:00:00",
            "end": "2026-08-25T09:05:00",
            "attendees": ["Caleb", "Arno"],
        },
        {
            "title": "Budget review",
            "start": "2026-08-25T09:10:30",
            "end": "2026-08-25T09:15:00",
            "attendees": ["Caleb", "Llew"],
        },
    ]
    meetings = split_into_meetings(
        two_meetings,
        config={"anthropic_api_key": "sk-ant", "min_meeting_seconds": 1},
        calendar_events=events,
        recording_start=recording_start,
    )
    assert [m.title for m in meetings] == ["Network sync", "Budget review"]
    assert meetings[1].attendees == ["Caleb", "Llew"]


def test_calendar_event_without_nearby_speech_is_ignored(two_meetings):
    """An invite nobody recorded must not manufacture an empty meeting."""
    recording_start = datetime(2026, 8, 25, 9, 0, 0)
    events = [
        {
            "title": "Meeting that was never recorded",
            "start": "2026-08-25T10:30:00",  # 90 min in; recording ends at 11 min
            "end": "2026-08-25T11:00:00",
            "attendees": [],
        }
    ]
    meetings = split_into_meetings(
        two_meetings,
        config={"anthropic_api_key": "", "min_meeting_seconds": 1},
        calendar_events=events,
        recording_start=recording_start,
    )
    # Falls through to gap splitting, with no phantom third meeting.
    assert len(meetings) == 2


# --- timeline_outline -------------------------------------------------------


def test_timeline_outline_marks_silence_gaps(two_meetings):
    outline = timeline_outline(two_meetings, find_gaps(two_meetings, 180))
    assert "SILENCE GAP" in outline
    assert "[00:00:00]" in outline
    assert "[00:10:30]" in outline


def test_timeline_outline_on_empty_segments():
    assert timeline_outline([], []) == ""
