"""Tests for notes generation, speaker naming, and action-item flattening."""

import pytest

from transcribe import notes as notes_mod
from transcribe.notes import (
    _condense,
    generate_notes,
    notes_action_items,
    resolve_speaker_names,
)
from transcribe.segments import Meeting, Segment


@pytest.fixture
def meeting():
    return Meeting(
        index=1,
        start=0.0,
        end=600.0,
        segments=[
            Segment(start=0, end=30, text="Morning, Arno here.", speaker="Speaker 1"),
            Segment(start=30, end=60, text="Hi Arno, Caleb speaking.", speaker="Speaker 2"),
            Segment(start=60, end=90, text="Let's review the routing.", speaker="Speaker 1"),
        ],
    )


@pytest.fixture
def config():
    return {"llm_provider": "claude", "anthropic_api_key": "sk-ant"}


# --- _condense --------------------------------------------------------------


def test_condense_leaves_short_text_alone():
    assert _condense("short", 1000) == "short"


def test_condense_keeps_head_and_tail():
    text = "A" * 1000 + "B" * 1000 + "C" * 1000
    out = _condense(text, token_budget=100)  # 400-char budget
    assert out.startswith("A")
    assert out.endswith("C")
    assert "omitted for length" in out


# --- notes_action_items -----------------------------------------------------


def test_notes_action_items_formats_owner_prefix():
    notes = {
        "next_steps": [
            {"owner": "Arno", "title": "Update docs", "detail": "Add drift notes."},
            {"owner": "Unassigned", "title": "Chase Rafik", "detail": "No owner."},
            {"owner": "", "title": "Bare item", "detail": ""},
        ]
    }
    assert notes_action_items(notes) == [
        "[Arno] Update docs: Add drift notes.",
        "Chase Rafik: No owner.",
        "Bare item",
    ]


@pytest.mark.parametrize("notes", [None, {}, {"next_steps": []}])
def test_notes_action_items_on_empty_input(notes):
    assert notes_action_items(notes) == []


# --- generate_notes ---------------------------------------------------------


def test_generate_notes_returns_none_without_api_key(meeting):
    assert generate_notes(meeting, {"llm_provider": "claude", "anthropic_api_key": ""}) is None


def test_generate_notes_passes_transcript_and_context(monkeypatch, meeting, config):
    captured = {}

    def fake_complete_json(cfg, system, user, schema, **kwargs):
        captured["system"] = system
        captured["user"] = user
        captured["schema"] = schema
        return {"title": "Routing review", "summary": "s", "sections": [], "details": []}

    monkeypatch.setattr(notes_mod, "complete_json", fake_complete_json)

    result = generate_notes(meeting, config)

    assert result["title"] == "Routing review"
    assert "Let's review the routing." in captured["user"]
    # Timestamps are present so the model can cite them.
    assert "[00:00:00]" in captured["user"]
    # Speaker labels reach the prompt.
    assert "Speaker 1:" in captured["user"]
    # The schema demands the sections the renderer expects.
    assert set(captured["schema"]["required"]) == {"title", "summary", "sections", "details"}


def test_generate_notes_includes_calendar_context(monkeypatch, meeting, config):
    captured = {}
    monkeypatch.setattr(
        notes_mod,
        "complete_json",
        lambda cfg, system, user, schema, **kw: captured.update(user=user) or {"title": "t"},
    )
    meeting.calendar_event = {"title": "S2S/VPN", "attendees": ["Caleb", "Arno"]}
    generate_notes(meeting, config)
    assert "S2S/VPN" in captured["user"]
    assert "Invited: Caleb, Arno" in captured["user"]


def test_generate_notes_returns_none_when_llm_fails(monkeypatch, meeting, config):
    monkeypatch.setattr(notes_mod, "complete_json", lambda *a, **k: None)
    assert generate_notes(meeting, config) is None


# --- resolve_speaker_names --------------------------------------------------


def test_resolve_speaker_names_renames_confident_matches(monkeypatch, meeting, config):
    monkeypatch.setattr(
        notes_mod,
        "complete_json",
        lambda *a, **k: {
            "speakers": [
                {"label": "Speaker 1", "name": "Arno", "confidence": "high"},
                {"label": "Speaker 2", "name": "Caleb", "confidence": "medium"},
            ]
        },
    )
    mapping = resolve_speaker_names(meeting, config)
    assert mapping == {"Speaker 1": "Arno", "Speaker 2": "Caleb"}
    assert [s.speaker for s in meeting.segments] == ["Arno", "Caleb", "Arno"]


def test_resolve_speaker_names_ignores_low_confidence(monkeypatch, meeting, config):
    """A wrong name is worse than no name, so low confidence stays anonymous."""
    monkeypatch.setattr(
        notes_mod,
        "complete_json",
        lambda *a, **k: {
            "speakers": [{"label": "Speaker 1", "name": "Probably Bob", "confidence": "low"}]
        },
    )
    assert resolve_speaker_names(meeting, config) == {}
    assert meeting.segments[0].speaker == "Speaker 1"


def test_resolve_speaker_names_ignores_empty_names(monkeypatch, meeting, config):
    monkeypatch.setattr(
        notes_mod,
        "complete_json",
        lambda *a, **k: {"speakers": [{"label": "Speaker 1", "name": "", "confidence": "high"}]},
    )
    assert resolve_speaker_names(meeting, config) == {}


def test_resolve_speaker_names_passes_known_participants(monkeypatch, meeting, config):
    captured = {}
    monkeypatch.setattr(
        notes_mod,
        "complete_json",
        lambda cfg, system, user, schema, **kw: captured.update(user=user) or {"speakers": []},
    )
    resolve_speaker_names(meeting, config, ["Caleb Sargeant", "Arno"])
    assert "Caleb Sargeant" in captured["user"]


def test_resolve_speaker_names_without_diarization(config):
    """No speaker labels means nothing to resolve."""
    bare = Meeting(index=1, start=0, end=10, segments=[Segment(start=0, end=10, text="hi")])
    assert resolve_speaker_names(bare, config) == {}


def test_resolve_speaker_names_without_api_key(meeting):
    assert resolve_speaker_names(meeting, {"anthropic_api_key": ""}) == {}


# --- _naming_context --------------------------------------------------------


def test_naming_context_keeps_opening_and_closing():
    """Introductions cluster at the start and sign-offs at the end."""
    segments = [Segment(start=t, end=t + 10, text=f"line at {t}") for t in range(0, 2000, 100)]
    meeting = Meeting(index=1, start=0, end=1910, segments=segments)
    context = notes_mod._naming_context(meeting, window=300)
    assert "line at 0" in context  # opening
    assert "line at 1900" in context  # closing
    assert "line at 900" not in context  # middle dropped


def test_naming_context_on_short_meeting_keeps_everything():
    segments = [Segment(start=0, end=10, text="hello"), Segment(start=10, end=20, text="bye")]
    meeting = Meeting(index=1, start=0, end=20, segments=segments)
    context = notes_mod._naming_context(meeting, window=300)
    assert "hello" in context and "bye" in context


def test_naming_context_on_empty_meeting():
    assert notes_mod._naming_context(Meeting(index=1, start=0, end=0, segments=[])) == ""


def test_resolve_speaker_names_sends_a_bounded_prompt(monkeypatch, config):
    """The naming prompt must not carry the whole meeting."""
    captured = {}
    monkeypatch.setattr(
        notes_mod,
        "complete_json",
        lambda cfg, system, user, schema, **kw: captured.update(user=user) or {"speakers": []},
    )
    long_meeting = Meeting(
        index=1,
        start=0,
        end=3600,
        segments=[
            Segment(start=t, end=t + 5, text=f"filler {t}", speaker="Speaker 1")
            for t in range(0, 3600, 5)
        ],
    )
    resolve_speaker_names(long_meeting, config)
    assert "filler 1800" not in captured["user"]  # the middle hour is not sent
    assert "filler 0" in captured["user"]
