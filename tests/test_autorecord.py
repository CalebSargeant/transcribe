"""Tests for the meeting-detection state machine."""

import pytest

from transcribe.audio import DEFAULT_IGNORED_DEVICES, is_ignored
from transcribe.autorecord import MeetingRecorder, Presence, meeting_in_progress
from transcribe.camera import DEFAULT_IGNORED_CAMERAS
from transcribe.camera import is_ignored as camera_ignored


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


# --- what counts as a meeting ------------------------------------------------


def test_mic_alone_is_not_a_meeting():
    """Dictation, voice notes and Siri all hold the mic and none are meetings."""
    assert meeting_in_progress(Presence(mic=True)) is False


def test_mic_and_camera_is_a_meeting():
    """Almost nothing but a video call turns the camera on."""
    assert meeting_in_progress(Presence(mic=True, camera=True)) is True


def test_mic_and_calendar_is_a_meeting():
    """Catches the audio-only standup, which mic+camera would miss."""
    assert meeting_in_progress(Presence(mic=True, calendar_meeting=True)) is True


def test_camera_without_mic_is_not_a_meeting():
    """A camera check or a photo is not a conversation."""
    assert meeting_in_progress(Presence(camera=True)) is False


def test_calendar_without_mic_is_not_a_meeting():
    """A meeting in the diary you never joined must not record an empty room."""
    assert meeting_in_progress(Presence(calendar_meeting=True)) is False


def test_nothing_is_not_a_meeting():
    assert meeting_in_progress(Presence()) is False


def test_calendar_signal_can_be_disabled():
    presence = Presence(mic=True, calendar_meeting=True)
    assert meeting_in_progress(presence, {"autorecord_use_calendar": False}) is False
    # Camera still works as the corroborating signal.
    assert (
        meeting_in_progress(Presence(mic=True, camera=True), {"autorecord_use_calendar": False})
        is True
    )


def test_mic_only_mode_is_opt_in():
    presence = Presence(mic=True)
    assert meeting_in_progress(presence) is False
    assert meeting_in_progress(presence, {"autorecord_mic_only": True}) is True


def test_the_silent_attendee_is_not_detected_without_a_calendar_entry():
    """Joining with everything off is undetectable; that is what manual is for."""
    assert meeting_in_progress(Presence(mic=False, camera=False)) is False


# --- manual override ---------------------------------------------------------


def test_manual_start_skips_the_debounce(recorder):
    """An explicit instruction should not wait 45 seconds to take effect."""
    assert recorder.update(0, False, manual=True) == "start"
    assert recorder.recording is True


def test_manual_stop_is_immediate(recorder):
    recorder.update(0, True)
    recorder.update(50, True)
    assert recorder.recording is True
    assert recorder.update(60, True, manual=False) == "stop"
    assert recorder.recording is False


def test_manual_beats_detection(recorder):
    """Manual off must hold even while a meeting is plainly in progress."""
    assert recorder.update(0, True, manual=False) is None
    assert recorder.update(100, True, manual=False) is None
    assert recorder.recording is False


def test_manual_start_is_idempotent(recorder):
    assert recorder.update(0, False, manual=True) == "start"
    assert recorder.update(10, False, manual=True) is None


def test_detection_resumes_cleanly_after_manual_control(recorder):
    """Releasing the override must not leave a stale countdown behind."""
    recorder.update(0, False, manual=True)
    recorder.update(10, False, manual=False)
    assert recorder.recording is False
    assert recorder.update(20, True) is None
    assert recorder.update(64, True) is None  # countdown restarts at 20
    assert recorder.update(65, True) == "start"


# --- virtual cameras ---------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["OBS Virtual Camera", "Capture screen 0", "mmhmm camera", "Snap Camera"]
)
def test_virtual_cameras_are_ignored(name):
    assert camera_ignored(name, DEFAULT_IGNORED_CAMERAS) is True


@pytest.mark.parametrize("name", ["Logitech BRIO", "FaceTime HD Camera"])
def test_real_cameras_are_not_ignored(name):
    assert camera_ignored(name, DEFAULT_IGNORED_CAMERAS) is False


def test_iphone_desk_view_is_ignored():
    """Continuity Desk View is a second stream of the same camera, not a call."""
    assert camera_ignored("Caleb's iPhone Desk View Camera", DEFAULT_IGNORED_CAMERAS) is True
