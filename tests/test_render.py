"""Tests for Markdown / HTML / transcript rendering and folder naming."""

from datetime import datetime

import pytest

from transcribe.render import (
    render_html,
    render_markdown,
    render_transcript,
    safe_folder_name,
)
from transcribe.segments import Meeting, Segment


@pytest.fixture
def notes():
    return {
        "title": "Camera subnet routing fixes",
        "summary": "The team resolved routing for three camera subnets.",
        "sections": [{"heading": "Network configuration", "body": "NAT rules were corrected."}],
        "decisions": [
            {
                "title": "Terraform docs",
                "detail": "All changes get documented.",
                "status": "aligned",
            },
            {
                "title": "Network scope",
                "detail": "Still undecided.",
                "status": "needs_further_discussion",
            },
        ],
        "next_steps": [
            {
                "owner": "Arno",
                "title": "Update Terraform docs",
                "detail": "Add the new config to the drift doc.",
            },
            {"owner": "Unassigned", "title": "Chase Rafik", "detail": "No owner named."},
        ],
        "details": [
            {
                "heading": "Address list",
                "body": "Caleb showed the subnets.",
                "timestamps": ["00:06:27", "00:04:55"],
            },
        ],
    }


@pytest.fixture
def meeting():
    return Meeting(
        index=1,
        start=60.0,
        end=3660.0,
        segments=[
            Segment(start=60.0, end=65.0, text="Morning all.", speaker="Caleb"),
            Segment(start=65.0, end=70.0, text="Let's start.", speaker="Caleb"),
            Segment(start=70.0, end=75.0, text="Sure.", speaker="Arno"),
        ],
        attendees=["Caleb Sargeant", "Arno"],
    )


# --- safe_folder_name -------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Normal Title", "Normal Title"),
        ("With/Slash", "With Slash"),
        ("Colon: Here", "Colon Here"),
        ("a\\b|c?d*e", "a b c d e"),
        ("  padded  ", "padded"),
        ("trailing dots...", "trailing dots"),
        ("", "Meeting"),
        (None, "Meeting"),
    ],
)
def test_safe_folder_name(title, expected):
    assert safe_folder_name(title) == expected


def test_safe_folder_name_truncates():
    assert len(safe_folder_name("x" * 200)) == 80


def test_safe_folder_name_strips_control_characters():
    assert safe_folder_name("bad\x00name\x1f") == "bad name"


# --- render_markdown --------------------------------------------------------


def test_render_markdown_includes_every_section(meeting, notes):
    out = render_markdown(meeting, notes, datetime(2026, 8, 25, 9, 0, 0), "rec.mov")
    assert out.startswith("# Camera subnet routing fixes")
    assert "## Summary" in out
    assert "### Network configuration" in out
    assert "### Aligned" in out
    assert "### Needs further discussion" in out
    assert "## Next steps" in out
    assert "**[Arno] Update Terraform docs**" in out
    assert "## Details" in out
    assert "(00:06:27)" in out
    assert "**Invited:** Caleb Sargeant, Arno" in out
    assert "`rec.mov`" in out


def test_render_markdown_offsets_date_by_meeting_start(meeting, notes):
    # Recording starts 09:00; the meeting starts 60s in, so 09:01.
    out = render_markdown(meeting, notes, datetime(2026, 8, 25, 9, 0, 0))
    assert "09:01" in out


def test_render_markdown_without_notes(meeting):
    out = render_markdown(meeting, None)
    assert "No notes were generated" in out
    assert out.startswith("# Meeting 1")


def test_render_markdown_omits_empty_sections(meeting):
    out = render_markdown(meeting, {"title": "T", "summary": "S"})
    assert "## Decisions" not in out
    assert "## Next steps" not in out
    assert "## Details" not in out


def test_render_markdown_lists_detected_speakers(meeting, notes):
    out = render_markdown(meeting, notes)
    # Caleb speaks 10s, Arno 5s, so Caleb is listed first.
    assert "**Speakers:** Caleb, Arno" in out


# --- render_html ------------------------------------------------------------


def test_render_html_is_self_contained_and_escaped(meeting):
    hostile = {
        "title": "<script>alert(1)</script>",
        "summary": "5 > 3 & 2 < 4",
        "sections": [],
        "details": [],
    }
    out = render_html(meeting, hostile, datetime(2026, 8, 25, 9, 0, 0))
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out
    assert "5 &gt; 3 &amp; 2 &lt; 4" in out
    # No external requests: everything is inline.
    assert "http://" not in out and "https://" not in out
    assert "<style>" in out


def test_render_html_supports_both_themes(meeting, notes):
    out = render_html(meeting, notes)
    assert "prefers-color-scheme: dark" in out
    assert "--bg:" in out


def test_render_html_renders_owners_and_timestamps(meeting, notes):
    out = render_html(meeting, notes)
    assert "Arno" in out
    assert "00:06:27" in out
    assert "<title>Camera subnet routing fixes</title>" in out


def test_render_html_without_notes(meeting):
    assert "No notes were generated" in render_html(meeting, None)


# --- render_transcript ------------------------------------------------------


def test_render_transcript_groups_consecutive_turns(meeting):
    out = render_transcript(meeting)
    # Caleb's two consecutive lines share one speaker header.
    assert out.count("Caleb:") == 1
    assert out.count("Arno:") == 1
    assert "[00:01:00] Morning all." in out


def test_render_transcript_labels_unattributed_speech():
    meeting = Meeting(index=1, start=0, end=5, segments=[Segment(start=0, end=5, text="Hello")])
    assert "Unknown speaker:" in render_transcript(meeting)
