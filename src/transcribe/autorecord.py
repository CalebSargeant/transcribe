"""Start and stop an OBS recording when a meeting starts and ends.

Detection is by microphone activity (see ``audio.py``) rather than by
recognising conferencing apps, so Meet in a browser tab works the same as Zoom,
Teams, or a Slack huddle.

Two guards keep it from being annoying. A meeting has to hold the microphone for
``autorecord_start_after_seconds`` before recording begins, so a notification
chime or a quick "can you hear me" does not produce a file. And it has to release
it for ``autorecord_stop_after_seconds`` before recording stops, so a pause to
switch headsets does not chop a meeting in two.
"""

import shutil
import subprocess
import time
from datetime import datetime

from .audio import DEFAULT_IGNORED_DEVICES, microphone_in_use

# Defaults chosen so a real meeting is caught and a stray chime is not.
DEFAULT_POLL_SECONDS = 5
DEFAULT_START_AFTER = 45
DEFAULT_STOP_AFTER = 120
# Recording into a nearly full disk corrupts the file and loses the meeting.
DEFAULT_MIN_FREE_GB = 10


class ObsUnavailable(RuntimeError):
    """Raised when OBS cannot be reached over obs-websocket."""


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

    def update(self, now, mic_active, free_gb=None):
        """Advance the state machine. Returns 'start', 'stop', or None."""
        if mic_active:
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


def watch(config=None, poll_seconds=None, iterations=None):
    """Poll for meetings and drive OBS until interrupted.

    ``iterations`` bounds the loop for testing; None runs forever.
    """
    config = config or {}
    poll = float(poll_seconds or config.get("autorecord_poll_seconds", DEFAULT_POLL_SECONDS))
    ignored = tuple(config.get("autorecord_ignored_devices") or DEFAULT_IGNORED_DEVICES)
    watch_dir = config.get("watch_directory") or "."

    recorder = MeetingRecorder(config)
    _log(
        f"Watching for meetings (start after {recorder.start_after:.0f}s of mic activity, "
        f"stop after {recorder.stop_after:.0f}s of silence)"
    )

    client = None
    count = 0
    while iterations is None or count < iterations:
        count += 1
        try:
            action = recorder.update(
                time.monotonic(), microphone_in_use(ignored), free_gigabytes(watch_dir)
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
