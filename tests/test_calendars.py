"""Tests for calendar lookup: windowing, graceful degradation, offsets."""

from datetime import datetime

import pytest

from transcribe import calendars
from transcribe.calendars import (
    CalendarUnavailable,
    event_offsets,
    events_for_recording,
    load_source,
)

# --- load_source ------------------------------------------------------------


def test_load_source_returns_macos_fetcher():
    assert load_source("macos") is calendars.fetch_macos_events


def test_load_source_rejects_unknown_source():
    with pytest.raises(CalendarUnavailable, match="Unknown calendar_source"):
        load_source("google")


# --- events_for_recording ---------------------------------------------------


def test_events_for_recording_pads_the_window(monkeypatch):
    """People start recording before a meeting opens and stop after it ends."""
    captured = {}

    def fake_fetch(window_start, window_end, config):
        captured["start"] = window_start
        captured["end"] = window_end
        return []

    monkeypatch.setattr(calendars, "_SOURCES", {"macos": fake_fetch})

    started = datetime(2026, 8, 25, 9, 34, 0)
    events_for_recording(started, 3600, {"calendar_margin_minutes": 15})

    assert captured["start"] == datetime(2026, 8, 25, 9, 19, 0)
    assert captured["end"] == datetime(2026, 8, 25, 10, 49, 0)


def test_events_for_recording_disabled_returns_empty():
    assert events_for_recording(datetime.now(), 60, {"calendar_enabled": False}) == []


def test_events_for_recording_without_start_time_returns_empty():
    assert events_for_recording(None, 60, {}) == []


def test_events_for_recording_degrades_when_unavailable(monkeypatch, capsys):
    """A missing dependency or denied permission must not fail the run."""

    def unavailable(*args, **kwargs):
        raise CalendarUnavailable("calendar access is denied")

    monkeypatch.setattr(calendars, "_SOURCES", {"macos": unavailable})
    assert events_for_recording(datetime.now(), 60, {}) == []
    assert "calendar lookup skipped" in capsys.readouterr().out


def test_events_for_recording_degrades_on_unexpected_error(monkeypatch, capsys):
    monkeypatch.setattr(
        calendars,
        "_SOURCES",
        {"macos": lambda *a, **k: (_ for _ in ()).throw(RuntimeError("objc blew up"))},
    )
    assert events_for_recording(datetime.now(), 60, {}) == []
    assert "calendar lookup failed" in capsys.readouterr().out


def test_events_for_recording_passes_events_through(monkeypatch):
    events = [{"title": "Standup", "start": "2026-08-25T09:00:00", "end": "..."}]
    monkeypatch.setattr(calendars, "_SOURCES", {"macos": lambda *a, **k: events})
    assert events_for_recording(datetime(2026, 8, 25, 9, 0), 600, {}) == events


# --- event_offsets ----------------------------------------------------------


def test_event_offsets_are_relative_to_recording_start():
    event = {"start": "2026-08-25T10:28:00", "end": "2026-08-25T11:16:00"}
    start, end = event_offsets(event, datetime(2026, 8, 25, 9, 34, 0))
    assert start == pytest.approx(54 * 60)
    assert end == pytest.approx(102 * 60)


def test_event_offsets_can_be_negative_for_meetings_already_running():
    event = {"start": "2026-08-25T09:30:00", "end": "2026-08-25T10:00:00"}
    start, _ = event_offsets(event, datetime(2026, 8, 25, 9, 34, 0))
    assert start == pytest.approx(-240)


# --- permission guidance -----------------------------------------------------


def test_permission_error_names_the_app_to_grant(monkeypatch):
    """The app to add is the terminal, not this tool, which is rarely obvious."""
    from transcribe import permissions

    monkeypatch.setattr(permissions, "responsible_app", lambda: "Warp")
    hint = permissions.grant_hint("Calendars")
    assert "Warp" in hint
    assert "Privacy & Security > Calendars" in hint
    assert "Cmd-Q" in hint


def test_grant_hint_falls_back_without_an_app_bundle(monkeypatch):
    from transcribe import permissions

    monkeypatch.setattr(permissions, "responsible_app", lambda: None)
    assert "the terminal app you are running this from" in permissions.grant_hint("Calendars")


def test_full_disk_access_hint_says_to_add_it_manually(monkeypatch):
    """Full Disk Access never lists an app until you add it with '+'."""
    from transcribe import permissions

    monkeypatch.setattr(permissions, "responsible_app", lambda: "Warp")
    hint = permissions.grant_hint("Full Disk Access", needs_manual_add=True)
    assert "'+' button" in hint
    assert "never fills itself in" in hint


def test_responsible_app_walks_up_to_a_bundle(monkeypatch):
    """A CLI's own process is not in a bundle; its terminal is."""
    import subprocess as sp

    from transcribe import permissions

    tree = {
        str(permissions.os.getpid()): ("200", "/usr/bin/python3"),
        "200": ("300", "/bin/zsh"),
        "300": ("1", "/Applications/Warp.app/Contents/MacOS/stable"),
    }

    def fake_run(cmd, **kwargs):
        pid = cmd[-1]
        parent, command = tree.get(pid, ("1", "launchd"))
        return sp.CompletedProcess(cmd, 0, stdout=f"{parent} {command}\n", stderr="")

    monkeypatch.setattr(permissions.subprocess, "run", fake_run)
    assert permissions.responsible_app() == "Warp"
