"""Tests for resolving a linkable URL for a destination folder."""

import pytest

from transcribe.links import (
    DEFAULT_ICLOUD_URL,
    describe_location,
    folder_url,
    icloud_folder_url,
    storage_kind,
)

ICLOUD = "/Users/x/Library/Mobile Documents/com~apple~CloudDocs/Meetings/Standup"
GDRIVE = "/Users/x/x@example.com - Google Drive/My Drive/Meetings/Standup"


# --- storage_kind -----------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (ICLOUD, "icloud"),
        (GDRIVE, "google_drive"),
        ("/Users/x/GoogleDrive/Meetings/Standup", "google_drive"),
        ("/Users/x/Movies/Standup", "local"),
        ("/tmp/out", "local"),
    ],
)
def test_storage_kind(path, expected):
    assert storage_kind(path) == expected


# --- icloud -----------------------------------------------------------------


def test_icloud_url_defaults_to_icloud_drive():
    """iCloud exposes no path-addressable URL, so this is the best available."""
    assert icloud_folder_url(ICLOUD) == DEFAULT_ICLOUD_URL


def test_icloud_url_is_configurable():
    assert icloud_folder_url(ICLOUD, {"icloud_base_url": "https://example.com/"}) == (
        "https://example.com/"
    )


def test_icloud_folder_resolves_without_touching_google(monkeypatch):
    monkeypatch.setattr(
        "transcribe.gdrive.get_google_drive_folder_url",
        lambda p: pytest.fail("Google Drive must not be consulted for an iCloud path"),
        raising=False,
    )
    assert folder_url(ICLOUD) == DEFAULT_ICLOUD_URL


# --- google drive -----------------------------------------------------------


def test_google_drive_folder_deep_links(monkeypatch):
    monkeypatch.setattr(
        "transcribe.gdrive.get_google_drive_folder_url",
        lambda p: "https://drive.google.com/drive/folders/XYZ",
        raising=False,
    )
    assert folder_url(GDRIVE) == "https://drive.google.com/drive/folders/XYZ"


def test_google_drive_lookup_failure_yields_no_url(monkeypatch):
    """A failed lookup must not become a file:// link; Slack renders those dead."""
    monkeypatch.setattr(
        "transcribe.gdrive.get_google_drive_folder_url", lambda p: None, raising=False
    )
    assert folder_url(GDRIVE) is None


# --- local ------------------------------------------------------------------


def test_local_folder_has_no_url():
    assert folder_url("/Users/x/Movies/Standup") is None


# --- describe_location ------------------------------------------------------


def test_describe_location_icloud():
    url, label, local = describe_location(ICLOUD)
    assert url == DEFAULT_ICLOUD_URL
    assert label == "Open iCloud Drive"
    assert local == ICLOUD


def test_describe_location_google(monkeypatch):
    monkeypatch.setattr(
        "transcribe.gdrive.get_google_drive_folder_url",
        lambda p: "https://drive.google.com/drive/folders/XYZ",
        raising=False,
    )
    url, label, local = describe_location(GDRIVE)
    assert url == "https://drive.google.com/drive/folders/XYZ"
    assert label == "Open folder in Google Drive"
    assert local == GDRIVE


def test_describe_location_local_always_returns_the_path():
    url, _, local = describe_location("/Users/x/Movies/Standup")
    assert url is None
    assert local == "/Users/x/Movies/Standup"
