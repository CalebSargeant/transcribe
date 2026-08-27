"""Start and stop an OBS recording when a meeting starts and ends.

Microphone activity alone is too eager: dictation, voice notes and Siri all use
the microphone and none of them are meetings. So a recording needs the mic *and*
one corroborating signal:

* **the camera is on** -- almost nothing but a video call turns it on, which
  makes it the highest-precision signal available, or
* **the calendar says a meeting is happening now** -- which is what every
  hosted meeting recorder actually keys off, and is the only thing that catches
  a meeting you join with the camera off.

Neither covers a meeting you attend silently with everything off. Nothing
short of watching the conferencing app can, which is why the menu bar has a
manual toggle: an explicit "record this" always wins.

Two guards stop it being annoying. A meeting must hold the signal for
``autorecord_start_after_seconds`` before recording begins, so a chime does not
produce a file, and release it for ``autorecord_stop_after_seconds`` before it
stops, so swapping a headset does not chop a meeting in two. A manual toggle
skips both, because an explicit instruction should not be second-guessed.
"""

import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime

from .audio import DEFAULT_IGNORED_DEVICES, microphone_in_use
from .camera import DEFAULT_IGNORED_CAMERAS, camera_in_use

# Defaults chosen so a real meeting is caught and a stray chime is not.
DEFAULT_POLL_SECONDS = 5
DEFAULT_START_AFTER = 45
DEFAULT_STOP_AFTER = 120
# Recording into a nearly full disk corrupts the file and loses the meeting.
DEFAULT_MIN_FREE_GB = 10


class ObsUnavailable(RuntimeError):
    """Raised when OBS cannot be reached over obs-websocket."""


@dataclass
class Presence:
    """What the machine can currently observe about whether you are in a meeting."""

    mic: bool = False
    camera: bool = False
    calendar_meeting: bool = False

    def describe(self):
        parts = [
            f"mic={'on' if self.mic else 'off'}",
            f"camera={'on' if self.camera else 'off'}",
            f"calendar={'meeting' if self.calendar_meeting else 'clear'}",
        ]
        return ", ".join(parts)


def meeting_in_progress(presence, config=None):
    """Decide whether ``presence`` looks like a meeting worth recording.

    The microphone is necessary but never sufficient. Requiring a second signal
    is what separates a meeting from a voice note.
    """
    config = config or {}
    if not presence.mic:
        return False
    if config.get("autorecord_require_camera", True) and presence.camera:
        return True
    if config.get("autorecord_use_calendar", True) and presence.calendar_meeting:
        return True
    # Deliberately opt-in: on its own the microphone fires on dictation and
    # voice notes, which is what makes always-on recording feel unhinged.
    return bool(config.get("autorecord_mic_only", False))


def _log(message):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def free_gigabytes(path):
    """Free space on the volume holding ``path``, in GB."""
    return shutil.disk_usage(path).free / (1024**3)


def obs_is_running():
    """True when the OBS application is running."""
    return subprocess.run(["pgrep", "-x", "OBS"], capture_output=True).returncode == 0


def launch_obs(wait_seconds=15):
    """Start OBS and wait for it to come up. Returns True if it is running."""
    if obs_is_running():
        return True
    _log("Starting OBS...")
    subprocess.run(["open", "-a", "OBS", "--args", "--minimize-to-tray"], capture_output=True)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if obs_is_running():
            # OBS needs a moment after launch before it accepts websocket calls.
            time.sleep(3)
            return True
        time.sleep(1)
    return False


def connect(config):
    """Return a connected obs-websocket client."""
    try:
        import obsws_python
    except ImportError as e:
        raise ObsUnavailable(
            "obsws-python is not installed. Install with: pip install 'transcribe[autorecord]'"
        ) from e

    try:
        return obsws_python.ReqClient(
            host=config.get("obs_host") or "localhost",
            port=int(config.get("obs_port") or 4455),
            password=config.get("obs_password") or "",
            timeout=5,
        )
    except Exception as e:
        raise ObsUnavailable(
            f"could not reach OBS on "
            f"{config.get('obs_host') or 'localhost'}:{config.get('obs_port') or 4455} "
            f"({type(e).__name__}: {e}). Enable Tools > WebSocket Server Settings in OBS."
        ) from e


def is_recording(client):
    """True when OBS is currently recording."""
    try:
        return bool(client.get_record_status().output_active)
    except Exception:
        return False


def start_recording(client):
    """Begin recording, unless one is already in progress."""
    if is_recording(client):
        return False
    client.start_record()
    return True


def stop_recording(client):
    """End the current recording and return the output path, if OBS reports one."""
    if not is_recording(client):
        return None
    response = client.stop_record()
    return getattr(response, "output_path", None)


class MeetingRecorder:
    """Tracks microphone activity and drives OBS through it.

    Kept free of sleeping and clock reads so the state machine can be tested
    directly: ``update`` is handed the time and whether the mic is live.
    """

    def __init__(self, config=None):
        config = config or {}
        self.start_after = float(config.get("autorecord_start_after_seconds", DEFAULT_START_AFTER))
        self.stop_after = float(config.get("autorecord_stop_after_seconds", DEFAULT_STOP_AFTER))
        self.min_free_gb = float(config.get("autorecord_min_free_gb", DEFAULT_MIN_FREE_GB))
        self.recording = False
        self._active_since = None
        self._idle_since = None

    def update(self, now, meeting_active, free_gb=None, manual=None):
        """Advance the state machine. Returns 'start', 'stop', or None.

        ``manual`` overrides detection entirely: True forces recording on and
        False forces it off, both without debounce, because an explicit
        instruction should take effect immediately.
        """
        if manual is not None:
            self._active_since = None
            self._idle_since = None
            if manual and not self.recording:
                self.recording = True
                return "start"
            if not manual and self.recording:
                self.recording = False
                return "stop"
            return None

        if meeting_active:
            self._idle_since = None
            if self._active_since is None:
                self._active_since = now
            if self.recording or now - self._active_since < self.start_after:
                return None
            # Refusing to start beats producing a truncated file on a full disk.
            if free_gb is not None and free_gb < self.min_free_gb:
                return None
            self.recording = True
            return "start"

        self._active_since = None
        if self._idle_since is None:
            self._idle_since = now
        if self.recording and now - self._idle_since >= self.stop_after:
            self.recording = False
            return "stop"
        return None


def calendar_meeting_now(config, cache=None):
    """True when a calendar event is in progress right now.

    Results are cached for a minute: the calendar is polled every few seconds
    and event boundaries do not move that fast.
    """
    from datetime import timedelta

    if not config.get("autorecord_use_calendar", True):
        return False

    cache = cache if cache is not None else {}
    now = time.monotonic()
    if cache.get("expires", 0) > now:
        return cache["value"]

    try:
        from .calendars import fetch_macos_events

        wall = datetime.now()
        events = fetch_macos_events(
            wall - timedelta(minutes=5), wall + timedelta(minutes=5), config
        )
        value = bool(events)
    except Exception:
        # Calendars are a bonus signal; never let them break detection.
        value = False

    cache["value"] = value
    cache["expires"] = now + 60
    return value


def current_presence(config, calendar_cache=None):
    """Sample every meeting signal the machine can see."""
    mic_ignored = tuple(config.get("autorecord_ignored_devices") or DEFAULT_IGNORED_DEVICES)
    cam_ignored = tuple(config.get("autorecord_ignored_cameras") or DEFAULT_IGNORED_CAMERAS)
    return Presence(
        mic=microphone_in_use(mic_ignored),
        camera=camera_in_use(cam_ignored),
        calendar_meeting=calendar_meeting_now(config, calendar_cache),
    )


def watch(config=None, poll_seconds=None, iterations=None, control=None):
    """Poll for meetings and drive OBS until interrupted.

    ``control`` is an optional object with a ``manual`` attribute (True, False,
    or None) so a menu bar app can force recording on or off.
    ``iterations`` bounds the loop for testing; None runs forever.
    """
    config = config or {}
    poll = float(poll_seconds or config.get("autorecord_poll_seconds", DEFAULT_POLL_SECONDS))
    watch_dir = config.get("watch_directory") or "."

    recorder = MeetingRecorder(config)
    rules = ["mic + camera"]
    if config.get("autorecord_use_calendar", True):
        rules.append("mic + calendar meeting")
    if config.get("autorecord_mic_only", False):
        rules.append("mic alone")
    _log(f"Watching for meetings. Will record on: {' or '.join(rules)}")
    _log(
        f"Start after {recorder.start_after:.0f}s, stop after {recorder.stop_after:.0f}s, "
        f"minimum {recorder.min_free_gb:.0f} GB free"
    )

    client = None
    calendar_cache = {}
    previous = None
    count = 0
    while iterations is None or count < iterations:
        count += 1
        try:
            presence = current_presence(config, calendar_cache)
            if previous != presence:
                _log(f"Signals: {presence.describe()}")
                previous = presence

            action = recorder.update(
                time.monotonic(),
                meeting_in_progress(presence, config),
                free_gigabytes(watch_dir),
                manual=getattr(control, "manual", None),
            )

            if action == "start":
                free = free_gigabytes(watch_dir)
                if not launch_obs():
                    _log("Could not start OBS; skipping this meeting")
                    recorder.recording = False
                else:
                    client = client or connect(config)
                    if start_recording(client):
                        _log(f"Meeting detected, recording started ({free:.0f} GB free)")
            elif action == "stop":
                if client is not None:
                    path = stop_recording(client)
                    _log(f"Meeting ended, recording stopped{f' -> {path}' if path else ''}")

        except ObsUnavailable as e:
            _log(f"OBS unavailable: {e}")
            recorder.recording = False
            client = None
        except Exception as e:
            _log(f"Warning: {type(e).__name__}: {e}")
            client = None

        if iterations is None or count < iterations:
            time.sleep(poll)
