"""Calendar lookup, used to name meetings and recover the attendee list.

A recording knows when it happened; a calendar knows what it was and who was in
it. Matching the two gives real meeting titles, real attendee names (which in
turn make speaker attribution far more accurate), and true boundaries when one
recording spans several back-to-back meetings.

Only the macOS Calendar (EventKit) source is implemented. It reads whatever
accounts Calendar.app already syncs, Google and Exchange included, so it covers
most setups without a second OAuth flow. ``load_source`` is the seam where
direct Google Calendar and Microsoft 365 sources plug in later.
"""

import threading
from datetime import datetime, timedelta

# EventKit's epoch: 2001-01-01 00:00:00 UTC.
_NSDATE_EPOCH_OFFSET = 978307200.0

# How long to wait for the user to answer the macOS permission prompt.
_ACCESS_TIMEOUT_SECONDS = 30


class CalendarUnavailable(RuntimeError):
    """Raised when no calendar can be read (missing dependency or permission)."""


def _nsdate_to_datetime(nsdate):
    """Convert an EventKit NSDate into a naive local ``datetime``."""
    if nsdate is None:
        return None
    return datetime.fromtimestamp(nsdate.timeIntervalSince1970())


def _request_access(store):
    """Request calendar access, returning True if granted.

    macOS shows a permission prompt the first time. In a headless context (a
    launchd daemon, or a subprocess with no UI session) the request is denied
    without prompting -- hence ``transcribe calendar-check``, which the user runs
    from a normal terminal to trigger the prompt once.
    """
    from EventKit import EKEntityTypeEvent

    answered = threading.Event()
    outcome = {"granted": False}

    def _completion(granted, error):
        outcome["granted"] = bool(granted)
        answered.set()

    # requestFullAccessToEventsWithCompletion: is the macOS 14+ API; older
    # systems only have requestAccessToEntityType:completion:.
    if store.respondsToSelector_("requestFullAccessToEventsWithCompletion:"):
        store.requestFullAccessToEventsWithCompletion_(_completion)
    else:
        store.requestAccessToEntityType_completion_(EKEntityTypeEvent, _completion)

    answered.wait(_ACCESS_TIMEOUT_SECONDS)
    return outcome["granted"]


def authorization_status():
    """Return the EventKit authorization status as ``(code, human_label)``."""
    try:
        from EventKit import EKEntityTypeEvent, EKEventStore
    except ImportError as e:
        raise CalendarUnavailable(
            "pyobjc-framework-EventKit is not installed. "
            "Install with: pip install 'transcribe[calendar]'"
        ) from e

    labels = {
        0: "not determined",
        1: "restricted",
        2: "denied",
        3: "authorized",
        4: "write only",
        5: "full access",
    }
    status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
    return status, labels.get(status, "unknown")


def _attendee_names(event):
    """Extract readable attendee names from an EKEvent."""
    names = []
    for participant in event.attendees() or []:
        name = participant.name()
        if not name:
            url = participant.URL()
            name = str(url.resourceSpecifier()) if url else None
        if name:
            names.append(str(name))
    organizer = event.organizer()
    if organizer is not None and organizer.name():
        organizer_name = str(organizer.name())
        if organizer_name not in names:
            names.insert(0, organizer_name)
    return names


def fetch_macos_events(window_start, window_end, config=None):
    """Return calendar events overlapping ``window_start``..``window_end``.

    Each event is a plain dict so it can be serialized straight into the notes
    JSON. All-day events are skipped -- they are almost never the meeting that
    was recorded.
    """
    config = config or {}
    try:
        from EventKit import EKEventStore
        from Foundation import NSDate
    except ImportError as e:
        raise CalendarUnavailable(
            "pyobjc-framework-EventKit is not installed. "
            "Install with: pip install 'transcribe[calendar]'"
        ) from e

    store = EKEventStore.alloc().init()
    status, label = authorization_status()
    # 3 = legacy "authorized", 5 = macOS 14+ full access.
    if status not in (3, 5) and not _request_access(store):
        from .permissions import grant_hint

        raise CalendarUnavailable(
            f"calendar access is {label}.\n{grant_hint('Calendars')}\n"
            "  A permission prompt only appears when there is a UI session to show it, "
            "so run 'transcribe calendar-check' from your own terminal window."
        )

    to_nsdate = NSDate.dateWithTimeIntervalSinceReferenceDate_
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        to_nsdate(window_start.timestamp() - _NSDATE_EPOCH_OFFSET),
        to_nsdate(window_end.timestamp() - _NSDATE_EPOCH_OFFSET),
        None,
    )

    events = []
    for event in store.eventsMatchingPredicate_(predicate) or []:
        if event.isAllDay():
            continue
        start = _nsdate_to_datetime(event.startDate())
        end = _nsdate_to_datetime(event.endDate())
        if start is None or end is None:
            continue
        events.append(
            {
                "title": str(event.title() or "Untitled event"),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "attendees": _attendee_names(event),
                "location": str(event.location() or "") or None,
                "calendar": str(event.calendar().title()) if event.calendar() else None,
            }
        )

    events.sort(key=lambda item: item["start"])
    return events


# Source registry. Additional providers (Google Calendar API, Microsoft 365
# Graph) register here without the callers needing to change.
_SOURCES = {"macos": fetch_macos_events}


def load_source(name):
    """Return the fetch function for a calendar source name."""
    try:
        return _SOURCES[name]
    except KeyError:
        known = ", ".join(sorted(_SOURCES))
        raise CalendarUnavailable(
            f"Unknown calendar_source {name!r}. Available sources: {known}"
        ) from None


def events_for_recording(started_at, duration_seconds, config=None):
    """Find calendar events overlapping a recording, with a tolerance margin.

    ``started_at`` is when the recording began; the window is padded on both
    sides because people start recording before a meeting opens and stop after
    it ends. Returns ``[]`` when calendars are disabled or unreadable, so the
    pipeline degrades to content-only titles instead of failing.
    """
    config = config or {}
    if not config.get("calendar_enabled", True):
        return []
    if started_at is None:
        return []

    margin = timedelta(minutes=int(config.get("calendar_margin_minutes", 15)))
    window_start = started_at - margin
    window_end = started_at + timedelta(seconds=duration_seconds) + margin

    try:
        fetch = load_source(config.get("calendar_source") or "macos")
        return fetch(window_start, window_end, config)
    except CalendarUnavailable as e:
        print(f"Note: calendar lookup skipped ({e})")
        return []
    except Exception as e:
        print(f"Warning: calendar lookup failed ({type(e).__name__}: {e})")
        return []


def event_offsets(event, recording_start):
    """Convert an event's wall-clock span into offsets from the recording start.

    Returns ``(start_offset, end_offset)`` in seconds; values may be negative
    when the meeting began before recording started.
    """
    start = datetime.fromisoformat(event["start"])
    end = datetime.fromisoformat(event["end"])
    return (
        (start - recording_start).total_seconds(),
        (end - recording_start).total_seconds(),
    )
