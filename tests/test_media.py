"""Tests for ffmpeg/ffprobe helpers: probing, clock recovery, and cutting."""

import json
import subprocess
from datetime import datetime

import pytest

from transcribe import media


@pytest.fixture
def fake_run(monkeypatch):
    """Capture subprocess invocations and return a scripted ffprobe payload."""
    calls = []
    payload = {"format": {}}

    def _run(cmd, **kwargs):
        calls.append(cmd)
        if "ffprobe" in cmd[0]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(media.subprocess, "run", _run)
    return calls, payload


# --- probe_duration ---------------------------------------------------------


def test_probe_duration_reads_format(fake_run):
    _, payload = fake_run
    payload["format"] = {"duration": "12793.51"}
    assert media.probe_duration("/v.mov") == pytest.approx(12793.51)


def test_probe_duration_returns_zero_when_missing(fake_run):
    assert media.probe_duration("/v.mov") == 0.0


def test_probe_survives_ffprobe_failure(monkeypatch):
    def _boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(media.subprocess, "run", _boom)
    assert media.probe("/v.mov") == {}
    assert media.probe_duration("/v.mov") == 0.0


def test_probe_survives_missing_ffprobe(monkeypatch):
    monkeypatch.setattr(
        media.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())
    )
    assert media.probe("/v.mov") == {}


# --- recording_started_at ---------------------------------------------------


def test_recording_started_at_prefers_container_metadata(fake_run):
    _, payload = fake_run
    payload["format"] = {"tags": {"creation_time": "2026-08-25T07:34:17.000000Z"}}
    started = media.recording_started_at("/Users/x/Movies/2026-08-25 09-34-17.mov")
    assert isinstance(started, datetime)
    assert started.tzinfo is None  # normalized to naive local time


def test_recording_started_at_falls_back_to_obs_filename(fake_run):
    """OBS names files by wall-clock start, which beats guessing from mtime."""
    assert media.recording_started_at("/Users/x/Movies/2026-08-25 09-34-17.mov") == datetime(
        2026, 8, 25, 9, 34, 17
    )


def test_recording_started_at_handles_underscore_filenames(fake_run):
    assert media.recording_started_at("/x/2026-08-25 09_34_17.mp4") == datetime(
        2026, 8, 25, 9, 34, 17
    )


def test_recording_started_at_uses_mtime_minus_duration(fake_run, tmp_path):
    """With no metadata and no parsable name, wind mtime back over the recording."""
    _, payload = fake_run
    payload["format"] = {"duration": "600"}
    video = tmp_path / "unparseable-name.mov"
    video.write_bytes(b"x")

    started = media.recording_started_at(str(video))
    finished = datetime.fromtimestamp(video.stat().st_mtime)
    assert (finished - started).total_seconds() == pytest.approx(600, abs=1)


def test_recording_started_at_returns_none_for_missing_file(fake_run):
    assert media.recording_started_at("/does/not/exist.mov") is None


# --- cut_video --------------------------------------------------------------


def test_cut_video_uses_stream_copy_and_duration(fake_run):
    calls, _ = fake_run
    media.cut_video("/v.mov", "/out/clip.mov", start=100.0, end=250.0)
    cmd = calls[-1]
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
    # Input seeking, then an explicit duration rather than an ambiguous -to.
    assert cmd[cmd.index("-ss") + 1] == "100.000"
    assert cmd[cmd.index("-t") + 1] == "150.000"
    assert "-to" not in cmd
    # -ss precedes -i so the seek happens on the input (fast path).
    assert cmd.index("-ss") < cmd.index("-i")


def test_cut_video_clamps_negative_start(fake_run):
    calls, _ = fake_run
    media.cut_video("/v.mov", "/out/clip.mov", start=-30.0, end=10.0)
    assert calls[-1][calls[-1].index("-ss") + 1] == "0.000"


def test_cut_video_without_end_runs_to_eof(fake_run):
    calls, _ = fake_run
    media.cut_video("/v.mov", "/out/clip.mov", start=5.0, end=None)
    assert "-t" not in calls[-1]


# --- extract_audio ----------------------------------------------------------


def test_extract_audio_requests_16k_mono_pcm(fake_run):
    calls, _ = fake_run
    media.extract_audio("/v.mov", "/tmp/a.wav")
    cmd = calls[-1]
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[cmd.index("-c:a") + 1] == "pcm_s16le"


def test_extract_audio_absolutizes_path_against_option_injection(fake_run):
    """A filename starting with '-' must not be parsed as an ffmpeg option."""
    calls, _ = fake_run
    media.extract_audio("-evil.mov", "/tmp/a.wav")
    assert calls[-1][calls[-1].index("-i") + 1].startswith("/")


# --- stream selection when cutting -------------------------------------------


def test_cut_maps_only_copyable_streams(fake_run):
    """-map 0 also grabs tracks that cannot be stream-copied.

    Voice Memos' .qta carries an Apple Positional Audio stream and an mebx
    timed-metadata track; ffmpeg fails outright rather than skipping them.
    """
    calls, _ = fake_run
    media.cut_video("/v.qta", "/out/clip.m4a", start=0.0, end=10.0)
    cmd = calls[-1]
    assert "0:v?" in cmd  # video only if present
    assert "0:a:0" in cmd  # exactly one audio stream
    assert cmd.count("-map") == 2
    # The blanket map is what broke on multi-stream containers.
    assert not any(part == "0" and cmd[index - 1] == "-map" for index, part in enumerate(cmd))


def test_has_video_stream_true_when_ffprobe_lists_one(monkeypatch):
    monkeypatch.setattr(
        media.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="0\n", stderr=""),
    )
    assert media.has_video_stream("/v.mov") is True


def test_has_video_stream_false_for_audio_only(monkeypatch):
    monkeypatch.setattr(
        media.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="", stderr=""),
    )
    assert media.has_video_stream("/a.m4a") is False


def test_has_video_stream_false_when_ffprobe_fails(monkeypatch):
    def _boom(*a, **k):
        raise subprocess.CalledProcessError(1, a[0])

    monkeypatch.setattr(media.subprocess, "run", _boom)
    assert media.has_video_stream("/broken.mov") is False
