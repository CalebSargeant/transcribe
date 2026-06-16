"""Tests for transcribe.daemon: launchd plist generation."""

from pathlib import Path

from transcribe import daemon
from transcribe.daemon import setup_daemon


def test_setup_daemon_writes_plist(monkeypatch, tmp_path, base_config, capsys):
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)
    monkeypatch.setattr(daemon.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(daemon.shutil, "which", lambda name: "/usr/local/bin/transcribe")

    base_config["watch_directory"] = "/my/watch/dir"
    setup_daemon(base_config)

    plist = home / "Library" / "LaunchAgents" / "com.calebsargeant.transcribe.plist"
    assert plist.exists()
    content = plist.read_text()

    # Preserved label and the watch command wiring.
    assert "<string>com.calebsargeant.transcribe</string>" in content
    assert "<string>/usr/local/bin/transcribe</string>" in content
    assert "<string>watch</string>" in content
    assert "<string>/my/watch/dir</string>" in content
    # Standard log paths point under the (mocked) home.
    assert f"{home}/Library/Logs/transcribe.log" in content
    assert f"{home}/Library/Logs/transcribe.error.log" in content

    out = capsys.readouterr().out
    assert "Created launchd plist" in out
    assert "launchctl load" in out


def test_setup_daemon_creates_parent_dir(monkeypatch, tmp_path, base_config):
    home = tmp_path / "home"  # LaunchAgents does NOT exist yet
    monkeypatch.setattr(daemon.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(daemon.shutil, "which", lambda name: "/bin/transcribe")

    setup_daemon(base_config)

    assert (home / "Library" / "LaunchAgents").is_dir()
    assert Path(home / "Library" / "LaunchAgents" / "com.calebsargeant.transcribe.plist").exists()
