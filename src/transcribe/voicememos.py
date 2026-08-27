"""Importing recordings and transcripts from the macOS Voice Memos app.

Voice Memos already transcribes on device, so a memo arrives with the expensive
part done. This module reads the app's library and hands the audio plus its
existing transcript to the rest of the pipeline, skipping Whisper entirely.

Two things shape the implementation:

**The library is protected.** It lives in a group container that needs Full Disk
Access, so the process reading it has to be granted that once in System Settings.

**The schema is Apple's and undocumented.** Column names have changed across
releases, and transcription is recent. Rather than hardcode names that may not
exist on a given macOS version, the tables are introspected and columns matched
by pattern. ``describe_library`` prints what was found, which is the fastest way
to see why an import came back empty.

The database is opened read-only and immutable. Nothing here writes to it.
"""

import os
import plistlib
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

CONTAINER = Path.home() / "Library/Group Containers/group.com.apple.VoiceMemos.shared"
RECORDINGS_DIR = CONTAINER / "Recordings"
DATABASE = RECORDINGS_DIR / "CloudRecordings.db"

# Core Data stores dates as seconds since 2001-01-01, like the rest of Apple's
# frameworks.
APPLE_EPOCH = datetime(2001, 1, 1)

# Column-name fragments, most specific first, for each field we want.
_PATH_HINTS = ("ZPATH", "ZLOCALPATH", "ZFILEPATH", "PATH")
# ZENCRYPTEDTITLE holds the raw "2026-08-27T09:05:55Z" default name, so the
# user's own label is preferred and that one is only a last resort.
_TITLE_HINTS = ("ZCUSTOMLABEL", "ZTITLE", "ZLABEL", "ZNAME", "ZENCRYPTEDTITLE")
_DATE_HINTS = ("ZDATE", "ZCREATIONDATE", "ZRECORDINGDATE", "ZSTARTDATE")
_DURATION_HINTS = ("ZDURATION", "ZLOCALDURATION")
_TRANSCRIPT_HINTS = ("TRANSCRIPTION", "TRANSCRIPT")


class VoiceMemosUnavailable(RuntimeError):
    """Raised when the Voice Memos library cannot be read."""


def _responsible_app():
    """Walk up the process tree to the enclosing .app bundle, if there is one.

    macOS attributes a permission request to the *responsible* process, which
    for a command-line tool is the terminal it was launched from, not the tool
    itself. Naming that app saves the user guessing which entry to add.
    """
    import re
    import subprocess

    pid = os.getpid()
    for _ in range(12):  # a shell chain is short; this is a guard, not a limit
        try:
            result = subprocess.run(
                ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        parts = result.stdout.strip().split(None, 1)
        if len(parts) != 2:
            return None
        parent, command = parts
        match = re.search(r"/([^/]+\.app)/Contents/MacOS/", command)
        if match:
            return match.group(1)[:-4]
        try:
            pid = int(parent)
        except ValueError:
            return None
        if pid <= 1:
            return None
    return None


def _full_disk_access_hint():
    """Explain which app to grant, naming it when it can be worked out."""
    app = _responsible_app()
    target = f"**{app}**" if app else "the terminal app you are running this from"
    return (
        f"The Voice Memos library needs Full Disk Access, granted to {target}.\n"
        "  System Settings > Privacy & Security > Full Disk Access, then the '+' "
        "button.\n"
        "  Full Disk Access never fills itself in from a denied request, so nothing "
        "will appear there on its own; you have to add the app yourself.\n"
        f"  Quit {app or 'the app'} completely (Cmd-Q) and reopen it afterwards: the "
        "permission is only re-read at launch."
    )


def _connect():
    """Open the Voice Memos database read-only, never touching Apple's copy."""
    if not CONTAINER.exists():
        raise VoiceMemosUnavailable(f"Voice Memos is not set up on this Mac ({CONTAINER} missing)")

    # The container is stat-able without Full Disk Access but not readable, so a
    # missing-looking database usually means the permission, not the app.
    if not os.access(CONTAINER, os.R_OK):
        raise VoiceMemosUnavailable(_full_disk_access_hint())
    if not DATABASE.exists():
        raise VoiceMemosUnavailable(
            f"no Voice Memos database at {DATABASE}.\n{_full_disk_access_hint()}"
        )
    try:
        return sqlite3.connect(f"file:{DATABASE}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error as e:
        # sqlite cannot distinguish "denied" from "corrupt"; permission is far
        # and away the likelier cause here.
        raise VoiceMemosUnavailable(
            f"could not open the Voice Memos database.\n{_full_disk_access_hint()}"
        ) from e


def _tables(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [row[0] for row in rows]


def _columns(connection, table):
    return [row[1] for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()]


def _pick(columns, hints):
    """Return the first column matching any hint, preferring exact matches."""
    upper = {column.upper(): column for column in columns}
    for hint in hints:
        if hint in upper:
            return upper[hint]
    for hint in hints:
        for name in upper:
            if hint in name:
                return upper[name]
    return None


def _recording_table(connection):
    """Find the table holding recordings, and the columns we care about."""
    candidates = [t for t in _tables(connection) if "RECORDING" in t.upper()]
    # Prefer the table that actually has a path column and some rows.
    best = None
    for table in candidates:
        columns = _columns(connection, table)
        path_column = _pick(columns, _PATH_HINTS)
        if not path_column:
            continue
        try:
            count = connection.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]
        except sqlite3.Error:
            continue
        if best is None or count > best[1]:
            best = (table, count, columns, path_column)
    if best is None:
        raise VoiceMemosUnavailable(
            "no recordings table found; run 'transcribe voicememos --debug' to see the schema"
        )
    table, _, columns, path_column = best
    return {
        "table": table,
        "columns": columns,
        "path": path_column,
        "title": _pick(columns, _TITLE_HINTS),
        "date": _pick(columns, _DATE_HINTS),
        "duration": _pick(columns, _DURATION_HINTS),
        "transcript": _pick(columns, _TRANSCRIPT_HINTS),
    }


def _decode_transcript(value):
    """Turn whatever the transcript column holds into plain text.

    Apple has stored this as plain text, as a plist, and as an archived object
    depending on the release, so the shape is checked rather than assumed.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if raw[:8] == b"bplist00":
            try:
                parsed = plistlib.loads(raw)
            except Exception:
                parsed = None
            if parsed is not None:
                return _text_from_plist(parsed)
        # Fall back to treating it as UTF-8 with the archiver noise stripped.
        text = raw.decode("utf-8", "ignore").strip()
        return text or None
    return None


def _text_from_plist(parsed):
    """Pull the longest string out of a decoded plist structure."""
    found = []

    def walk(node):
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(parsed)
    if not found:
        return None
    # The transcript is by far the longest string in the structure.
    best = max(found, key=len).strip()
    return best or None


_ISO_DEFAULT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?$")


def _clean_title(value, recorded_at):
    """Return a usable title, ignoring Voice Memos' machine-generated default.

    An untitled memo is stored as an ISO timestamp, which makes a poor folder
    name and a worse meeting title. The LLM renames the meeting from its content
    anyway, so a readable placeholder is enough.
    """
    text = (value or "").strip()
    if text and not _ISO_DEFAULT_NAME.match(text):
        return text
    if recorded_at:
        return f"Voice Memo {recorded_at:%Y-%m-%d %H:%M}"
    return "Voice Memo"


def _resolve_audio(path_value):
    """Turn the stored path into an absolute file path, if the file exists."""
    if not path_value:
        return None
    candidate = Path(path_value)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    for base in (RECORDINGS_DIR, CONTAINER):
        resolved = base / candidate.name
        if resolved.exists():
            return resolved
    return None


def _read_sidecar_transcript(audio_path):
    """Look for a transcript sidecar file alongside the audio file.

    Voice Memos stores transcripts beside the audio rather than in the DB on
    every macOS version tested. The sidecar shares the audio file's stem; this
    tries the extensions most commonly seen in the Recordings directory.
    """
    if not audio_path:
        return None
    audio = Path(audio_path)
    for ext in (".transcript", ".txt"):
        sidecar = audio.with_suffix(ext)
        if sidecar.exists():
            try:
                return _decode_transcript(sidecar.read_bytes())
            except OSError:
                pass
    return None


def list_memos(since=None, limit=None):
    """Return Voice Memos recordings, newest first.

    Each entry is a dict with ``title``, ``recorded_at``, ``duration``,
    ``audio_path`` and ``transcript`` (None when the memo has not been
    transcribed by the app).
    """
    with _connect() as connection:
        schema = _recording_table(connection)
        wanted = [schema["path"]]
        for key in ("title", "date", "duration", "transcript"):
            if schema[key]:
                wanted.append(schema[key])

        columns = ", ".join(f'"{name}"' for name in wanted)
        order = f' ORDER BY "{schema["date"]}" DESC' if schema["date"] else ""
        rows = connection.execute(f'SELECT {columns} FROM "{schema["table"]}"{order}').fetchall()
    connection.close()

    memos = []
    for row in rows:
        values = dict(zip(wanted, row, strict=False))
        recorded_at = None
        if schema["date"] and values.get(schema["date"]) is not None:
            try:
                recorded_at = APPLE_EPOCH + timedelta(seconds=float(values[schema["date"]]))
            except (TypeError, ValueError):
                recorded_at = None

        if since and recorded_at and recorded_at < since:
            continue

        audio = _resolve_audio(values.get(schema["path"]))
        audio_path = str(audio) if audio else None
        db_transcript = _decode_transcript(
            values.get(schema["transcript"]) if schema["transcript"] else None
        )
        memos.append(
            {
                "title": _clean_title(
                    values.get(schema["title"]) if schema["title"] else None, recorded_at
                ),
                "recorded_at": recorded_at,
                "duration": values.get(schema["duration"]) if schema["duration"] else None,
                "audio_path": audio_path,
                "transcript": db_transcript or _read_sidecar_transcript(audio_path),
            }
        )
        if limit and len(memos) >= limit:
            break
    return memos


def inspect_storage(limit=40):
    """Describe what actually sits in the Recordings directory.

    The transcript is not in CloudRecordings.db on any macOS version tested, so
    it has to live beside the audio. This reports the file types present and the
    most recent entries, which is what identifies the sidecar.
    """
    import collections

    if not RECORDINGS_DIR.exists():
        return {"directory": str(RECORDINGS_DIR), "error": "not found"}

    try:
        entries = sorted(RECORDINGS_DIR.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError as e:
        return {"directory": str(RECORDINGS_DIR), "error": str(e)}

    extensions = collections.Counter(
        (entry.suffix.lower() or "(no extension)") for entry in entries if entry.is_file()
    )
    recent = []
    for entry in entries[:limit]:
        try:
            size = entry.stat().st_size
        except OSError:
            size = -1
        recent.append(
            {
                "name": str(entry.relative_to(RECORDINGS_DIR)),
                "kind": "dir" if entry.is_dir() else "file",
                "size": size,
            }
        )
    return {
        "directory": str(RECORDINGS_DIR),
        "extensions": dict(extensions.most_common()),
        "recent": recent,
    }


def describe_library():
    """Return a description of the schema actually found, for troubleshooting."""
    with _connect() as connection:
        tables = _tables(connection)
        schema = _recording_table(connection)
        transcript_columns = [
            column
            for table in tables
            for column in _columns(connection, table)
            if any(hint in column.upper() for hint in _TRANSCRIPT_HINTS)
        ]
        count = connection.execute(f'SELECT COUNT(*) FROM "{schema["table"]}"').fetchone()[0]
    connection.close()

    return {
        "database": str(DATABASE),
        "tables": tables,
        "recording_table": schema["table"],
        "recording_count": count,
        "columns": schema["columns"],
        "resolved": {
            key: schema[key] for key in ("path", "title", "date", "duration", "transcript")
        },
        "transcript_columns_anywhere": transcript_columns,
    }
