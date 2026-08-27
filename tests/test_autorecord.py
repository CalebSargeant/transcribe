"""Tests for the meeting-detection state machine."""

import pytest

from transcribe.audio import DEFAULT_IGNORED_DEVICES, is_ignored
from transcribe.autorecord import MeetingRecorder


@pytest.fixture
def recorder():
    return MeetingRecorder(
        {
            "autorecord_start_after_seconds": 45,
            "autorecord_stop_after_seconds": 120,
            "autorecord_min_free_gb": 10,
        }
    )


# --- starting ---------------------------------------------------------------


def test_brief_mic_activity_does_not_record(recorder):
    """A notification chime or a mic test must not produce a recording."""
    assert recorder.update(0, True) is None
    assert recorder.update(10, True) is None
    assert recorder.update(20, False) is None
    assert recorder.recording is False


def test_sustained_mic_activity_starts_recording(recorder):
    assert recorder.update(0, True) is None
    assert recorder.update(44, True) is None  # one second short
    assert recorder.update(45, True) == "start"
    assert recorder.recording is True


def test_start_fires_only_once(recorder):
    recorder.update(0, True)
    assert recorder.update(50, True) == "start"
    assert recorder.update(60, True) is None
    assert recorder.update(600, True) is None


def test_activity_clock_resets_when_the_mic_drops(recorder):
    """A gap means the countdown starts again, not that it carries over."""
    recorder.update(0, True)
    recorder.update(40, True)
    recorder.update(41, False)  # dropped just before the threshold
    recorder.update(42, True)
    assert recorder.update(80, True) is None  # only 38s of the new stretch
    assert recorder.update(87, True) == "start"


# --- stopping ---------------------------------------------------------------


def test_short_silence_does_not_stop_recording(recorder):
    """Swapping a headset mid-meeting must not split the recording in two."""
    recorder.update(0, True)
    recorder.update(50, True)
    assert recorder.update(60, False) is None
    assert recorder.update(100, False) is None
    assert recorder.recording is True


def test_sustained_silence_stops_recording(recorder):
    recorder.update(0, True)
    recorder.update(50, True)
    recorder.update(60, False)
    assert recorder.update(179, False) is None
    assert recorder.update(180, False) == "stop"
    assert recorder.recording is False


def test_silence_clock_resets_when_talking_resumes(recorder):
    recorder.update(0, True)
    recorder.update(50, True)
    recorder.update(60, False)
    recorder.update(100, True)  # back on the call
    assert recorder.update(215, False) is None  # silence only started at 215
    assert recorder.update(340, False) == "stop"


def test_stop_fires_only_once(recorder):
    recorder.update(0, True)
    recorder.update(50, True)
    recorder.update(60, False)
    assert recorder.update(200, False) == "stop"
    assert recorder.update(400, False) is None


def test_a_full_meeting_cycle(recorder):
    assert recorder.update(0, True) is None
    assert recorder.update(45, True) == "start"
    assert recorder.update(1800, True) is None
    assert recorder.update(1810, False) is None
    assert recorder.update(1930, False) == "stop"
    # And the next meeting records too.
    assert recorder.update(3000, True) is None
    assert recorder.update(3045, True) == "start"


# --- disk guard -------------------------------------------------------------


def test_does_not_start_when_the_disk_is_nearly_full(recorder):
    """A truncated recording on a full disk loses the meeting entirely."""
    recorder.update(0, True)
    assert recorder.update(60, True, free_gb=2) is None
    assert recorder.recording is False


def test_starts_once_space_is_available_again(recorder):
    recorder.update(0, True)
    assert recorder.update(60, True, free_gb=2) is None
    assert recorder.update(70, True, free_gb=50) == "start"


def test_low_disk_does_not_interrupt_a_recording_in_progress(recorder):
    """Stopping early would lose what has already been captured."""
    recorder.update(0, True)
    assert recorder.update(50, True, free_gb=50) == "start"
    assert recorder.update(100, True, free_gb=1) is None
    assert recorder.recording is True


# --- virtual device filtering -----------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Steam Streaming Microphone",
        "BlackHole 2ch",
        "ZoomAudioDevice",
        "OBS Virtual Camera",
        "Krisp Microphone",
        "Loopback Audio",
    ],
)
def test_virtual_devices_are_ignored(name):
    """These report as running whenever their host app is open, meeting or not."""
    assert is_ignored(name, DEFAULT_IGNORED_DEVICES) is True


@pytest.mark.parametrize(
    "name",
    ["MacBook Pro Microphone", "SB725 Dell Pro Premium Soundbar", "Caleb's iPhone Microphone"],
)
def test_real_devices_are_not_ignored(name):
    assert is_ignored(name, DEFAULT_IGNORED_DEVICES) is False
