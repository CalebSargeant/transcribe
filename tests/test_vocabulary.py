"""Tests for building the Whisper prompt from context rather than a kept list."""

import json

import pytest

from transcribe.vocabulary import (
    build_prompt,
    extract_terms,
    load_glossary,
    mine_notes,
    record_terms,
    terms_from_calendar,
)

# --- what counts as a term ---------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["We use Kubernetes", "the AWS VPC", "MikroTik routers", "GitFlow branching", "tag RC2"],
)
def test_domain_terms_are_extracted(text):
    assert extract_terms(text)


def test_bare_version_numbers_are_not_terms():
    """Whisper handles digits fine, and a one-off version never recurs."""
    assert extract_terms("we shipped 1.3.83 yesterday") == {}


@pytest.mark.parametrize(
    "text",
    [
        "the team agreed on the plan",
        "This That These Those",
        "we should have been there before",
    ],
)
def test_ordinary_words_are_not_terms(text):
    """Whisper already knows ordinary English; priming it would waste the budget."""
    assert extract_terms(text) == {}


def test_pipeline_artifacts_are_excluded():
    """'Speaker' appears in every set of notes with unnamed voices."""
    terms = extract_terms("Speaker 1 and Speaker 2 discussed it. Unassigned owner.")
    assert "Speaker" not in terms
    assert "Unassigned" not in terms


def test_repeated_terms_are_counted():
    assert extract_terms("Kubernetes and Kubernetes again")["Kubernetes"] == 2


# --- calendar ----------------------------------------------------------------


def test_calendar_supplies_title_and_attendee_terms():
    events = [{"title": "Janeway hosting review", "attendees": ["Sam Okoro", "Priya Nair"]}]
    terms = terms_from_calendar(events)
    assert "Janeway" in terms
    assert "Okoro" in terms and "Priya" in terms
    # "hosting" and "review" are ordinary words and not worth budget.
    assert "hosting" not in terms


def test_calendar_terms_are_deduped():
    events = [
        {"title": "Janeway sync", "attendees": ["Sam Okoro"]},
        {"title": "Janeway retro", "attendees": ["Sam Okoro"]},
    ]
    assert terms_from_calendar(events).count("Janeway") == 1


def test_no_calendar_events_is_fine():
    assert terms_from_calendar(None) == []


# --- glossary ----------------------------------------------------------------


def test_record_terms_accumulates(tmp_path):
    path = tmp_path / "glossary.json"
    record_terms({"Kubernetes": 1}, path=path)
    record_terms({"Kubernetes": 2, "Janeway": 1}, path=path)
    glossary = load_glossary(path)
    assert glossary["Kubernetes"]["count"] == 3
    assert glossary["Janeway"]["count"] == 1


def test_record_terms_accepts_a_plain_list(tmp_path):
    path = tmp_path / "glossary.json"
    record_terms(["Nomad", "Flux"], path=path)
    assert set(load_glossary(path)) == {"Nomad", "Flux"}


def test_load_glossary_survives_corruption(tmp_path):
    path = tmp_path / "glossary.json"
    path.write_text("{not json")
    assert load_glossary(path) == {}


def test_mine_notes_reads_past_meetings(tmp_path):
    folder = tmp_path / "2026-04-14 1000 Some meeting"
    folder.mkdir()
    (folder / "notes.json").write_text(
        json.dumps(
            {
                "notes": {
                    "title": "Kubernetes migration",
                    "summary": "We discussed Kubernetes and MikroTik.",
                    "sections": [{"heading": "x", "body": "The VDC uplink was the issue."}],
                    "details": [{"heading": "y", "body": "Janeway hosting came up."}],
                }
            }
        )
    )
    mined = mine_notes(tmp_path)
    assert "Kubernetes" in mined and "MikroTik" in mined
    assert "VDC" in mined and "Janeway" in mined


def test_mine_notes_on_a_missing_directory():
    assert mine_notes("/nonexistent/path/for/tests") == {}


# --- assembling the prompt ---------------------------------------------------


def test_prompt_puts_calendar_terms_first(tmp_path):
    """Calendar terms describe the meeting at hand, so they outrank everything."""
    config = {"destination_directory": str(tmp_path), "whisper_prompt": "Terraform, Ansible"}
    prompt = build_prompt(
        config,
        [{"title": "Janeway review", "attendees": []}],
        glossary_path=tmp_path / "g.json",
    )
    terms = prompt.split(", ")
    assert terms[0] == "Janeway"
    assert "Terraform" in terms


def test_prompt_includes_the_learned_glossary(tmp_path):
    path = tmp_path / "g.json"
    record_terms({"MikroTik": 5}, path=path)
    prompt = build_prompt({"destination_directory": str(tmp_path)}, [], glossary_path=path)
    assert "MikroTik" in prompt


def test_prompt_respects_the_token_budget(tmp_path):
    """Whisper truncates past n_text_ctx/2, so overflow must be dropped, not sent."""
    path = tmp_path / "g.json"
    record_terms({f"Term{i}Word": 1 for i in range(400)}, path=path)
    config = {"destination_directory": str(tmp_path), "whisper_prompt_token_budget": 40}
    prompt = build_prompt(config, [], glossary_path=path)
    assert 0 < len(prompt.split(", ")) < 40


def test_auto_prompt_can_be_disabled(tmp_path):
    config = {
        "whisper_auto_prompt": False,
        "whisper_prompt": "just this",
        "destination_directory": str(tmp_path),
    }
    assert build_prompt(config, [{"title": "Janeway"}]) == "just this"


def test_prompt_with_nothing_configured_is_empty(tmp_path):
    assert build_prompt({"destination_directory": str(tmp_path)}, []) == ""
