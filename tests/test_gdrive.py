"""Tests for transcribe.gdrive: Drive folder URL resolution.

The Google client libraries are an optional extra and may not be installed,
so the in-function imports are stubbed via sys.modules.
"""

import sys
import types

import pytest

from transcribe.gdrive import get_google_drive_folder_url


@pytest.fixture
def fake_google(monkeypatch):
    """Stub google.auth.default and googleapiclient.discovery.build."""
    state = {"files": [], "queries": []}

    class FakeCreds:
        def with_quota_project(self, project):
            return self

    class FakeFilesResource:
        def list(self, **kwargs):
            state["queries"].append(kwargs.get("q"))

            class _Exec:
                def execute(_self):
                    return {"files": state["files"]}

            return _Exec()

    class FakeService:
        def files(self):
            return FakeFilesResource()

    # google.auth.default
    google_mod = types.ModuleType("google")
    google_auth = types.ModuleType("google.auth")
    google_auth.default = lambda scopes=None: (FakeCreds(), "proj")
    google_mod.auth = google_auth

    # googleapiclient.discovery.build
    gac = types.ModuleType("googleapiclient")
    gac_disc = types.ModuleType("googleapiclient.discovery")
    gac_disc.build = lambda *a, **k: FakeService()
    gac.discovery = gac_disc

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    monkeypatch.setitem(sys.modules, "googleapiclient", gac)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", gac_disc)
    return state


def test_returns_drive_url_when_folder_found(fake_google):
    fake_google["files"] = [{"id": "FOLDER123", "name": "meeting"}]
    url = get_google_drive_folder_url("/dest/meeting")
    assert url == "https://drive.google.com/drive/folders/FOLDER123"
    # Query searches by folder name.
    assert "name='meeting'" in fake_google["queries"][0]


def test_returns_none_when_not_found(fake_google, monkeypatch):
    fake_google["files"] = []  # never found
    # Don't actually sleep through the 10 retries.
    import transcribe.gdrive as gdrive

    monkeypatch.setattr(gdrive.time, "sleep", lambda s: None)
    url = get_google_drive_folder_url("/dest/missing")
    assert url is None


def test_returns_none_on_exception(monkeypatch):
    # No google modules installed / import fails -> graceful None.
    monkeypatch.setitem(sys.modules, "google.auth", None)
    url = get_google_drive_folder_url("/dest/x")
    assert url is None
