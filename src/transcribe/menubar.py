"""A menu bar app for meeting recording.

Automatic detection can only ever be a guess. It cannot see a meeting you attend
with your camera and microphone off, and it will occasionally read something
else as a meeting. So the menu bar carries the two things detection cannot
provide: a manual override that always wins, and visibility into why the
detector thinks what it thinks.

The title character is the whole status at a glance:

* ``●``  recording
* ``○``  a meeting is detected, waiting out the start delay
* ``◌``  idle
* ``⊘``  automatic detection paused
"""

import contextlib
import threading

from .autorecord import (
    MeetingRecorder,
    ObsUnavailable,
    connect,
    current_presence,
    free_gigabytes,
    is_recording,
    launch_obs,
    meeting_in_progress,
    start_recording,
    stop_recording,
)
from .config import load_config

IDLE = "◌"
DETECTED = "○"
RECORDING = "●"
PAUSED = "⊘"


class MenuBarUnavailable(RuntimeError):
    """Raised when rumps is not installed."""


class RecorderController:
    """Shared state between the menu bar and the polling thread.

    ``manual`` is three-valued on purpose: True forces recording, False forces
    it off, and None hands control back to detection.
    """

    def __init__(self):
        self.manual = None
        self.paused = False
        self.lock = threading.Lock()

    def record_now(self):
        with self.lock:
            self.manual = True

    def stop_now(self):
        with self.lock:
            self.manual = False

    def resume_auto(self):
        with self.lock:
            self.manual = None
            self.paused = False

    def pause_auto(self):
        with self.lock:
            self.paused = True
            self.manual = False


def run(config=None):
    """Run the menu bar app. Blocks until the user quits."""
    try:
        import rumps
    except ImportError as e:
        raise MenuBarUnavailable(
            "rumps is not installed. Install with: pip install 'transcribe[menubar]'"
        ) from e

    config = config or load_config()
    control = RecorderController()
    recorder = MeetingRecorder(config)
    poll = float(config.get("autorecord_poll_seconds", 5))
    watch_dir = config.get("watch_directory") or "."

    class TranscribeApp(rumps.App):
        def __init__(self):
            super().__init__("Transcribe", title=IDLE, quit_button=None)
            self.status_item = rumps.MenuItem("Idle")
            self.status_item.set_callback(None)
            self.signals_item = rumps.MenuItem("Signals: ...")
            self.signals_item.set_callback(None)
            self.menu = [
                self.status_item,
                self.signals_item,
                None,
                rumps.MenuItem("Record now", callback=self.on_record),
                rumps.MenuItem("Stop recording", callback=self.on_stop),
                None,
                rumps.MenuItem("Pause auto-record", callback=self.on_pause),
                rumps.MenuItem("Resume auto-record", callback=self.on_resume),
                None,
                rumps.MenuItem("Quit", callback=self.on_quit),
            ]
            self._client = None
            self._calendar_cache = {}

        # --- menu actions -------------------------------------------------

        def on_record(self, _):
            control.record_now()

        def on_stop(self, _):
            control.stop_now()

        def on_pause(self, _):
            control.pause_auto()

        def on_resume(self, _):
            control.resume_auto()

        def on_quit(self, _):
            # Leaving a recording running with nothing to stop it would lose it.
            if recorder.recording and self._client is not None:
                with contextlib.suppress(Exception):
                    stop_recording(self._client)
            rumps.quit_application()

        # --- polling ------------------------------------------------------

        def _obs(self):
            if self._client is None:
                launch_obs()
                self._client = connect(config)
            return self._client

        @rumps.timer(1)
        def tick(self, _):
            # rumps drives this on the main thread, so the poll interval is
            # enforced here rather than by sleeping and freezing the UI.
            if not hasattr(self, "_countdown"):
                self._countdown = 0
            self._countdown -= 1
            if self._countdown > 0:
                return
            self._countdown = max(int(poll), 1)

            try:
                self._poll_once()
            except ObsUnavailable as e:
                self.status_item.title = "OBS unavailable"
                self.signals_item.title = str(e)[:70]
                self._client = None
                recorder.recording = False
            except Exception as e:
                self.status_item.title = f"Error: {type(e).__name__}"

        def _poll_once(self):
            import time

            with control.lock:
                manual = control.manual
                paused = control.paused

            presence = current_presence(config, self._calendar_cache)
            detected = meeting_in_progress(presence, config)

            action = recorder.update(
                time.monotonic(),
                False if paused else detected,
                free_gigabytes(watch_dir),
                manual=manual,
            )

            if action == "start":
                if start_recording(self._obs()):
                    self.status_item.title = "Recording"
            elif action == "stop":
                if self._client is not None:
                    stop_recording(self._client)
                self.status_item.title = "Idle"
                # A manual stop is a one-shot instruction, not a permanent mode.
                with control.lock:
                    if control.manual is False and not control.paused:
                        control.manual = None

            live = recorder.recording or (self._client is not None and is_recording(self._client))
            if live:
                self.title = RECORDING
                self.status_item.title = "Recording"
            elif paused:
                self.title = PAUSED
                self.status_item.title = "Auto-record paused"
            elif detected:
                self.title = DETECTED
                self.status_item.title = "Meeting detected"
            else:
                self.title = IDLE
                self.status_item.title = "Idle"

            self.signals_item.title = f"Signals: {presence.describe()}"

    TranscribeApp().run()
