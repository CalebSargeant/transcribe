#!/usr/bin/env python3
"""Command-line entry point for transcribe.

Usage:
  transcribe <video_file>           - Transcribe a single file
  transcribe watch <directory>      - Watch directory for new files
  transcribe setup-daemon           - Install background daemon
  transcribe config                 - Configure settings
  transcribe doctor                 - Check dependencies and models
  transcribe calendar-check         - Verify macOS Calendar access
  transcribe --version              - Show version information
Requires: brew install whisper-cpp ffmpeg
"""

import shutil
import sys
from pathlib import Path

from . import __version__
from .config import CONFIG_FILE, load_config
from .daemon import setup_daemon
from .processing import process_video_file
from .tls import _ensure_tls_ca_bundle
from .watch import watch_directory

# Run TLS fixup as early as possible, before any network clients are created
_ensure_tls_ca_bundle()

# Force line-buffered output for daemon logging
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass


def configure():
    """Interactive configuration."""
    config = load_config()

    print("\nTranscribe Configuration\n" + "=" * 40)
    # Mask any key whose name suggests it holds a credential.
    secret_markers = ("api_key", "webhook", "token", "secret")
    print("\nCurrent configuration:")
    for key, value in config.items():
        if any(marker in key.lower() for marker in secret_markers):
            display_value = "***" if value else "(not set)"
        else:
            display_value = value
        print(f"  {key}: {display_value}")

    print("\nEdit the configuration file at:")
    print(f"  {CONFIG_FILE}")
    print("\nRequired for full functionality:")
    print("  - anthropic_api_key (or openai_api_key): notes and summaries")
    print("  - slack_webhook_url: notifications")


def doctor():
    """Report on every dependency the pipeline can use, and what is missing."""
    config = load_config()
    print("\nTranscribe doctor\n" + "=" * 40)

    ok = True

    print("\nCommand-line tools:")
    for tool, install in (
        ("ffmpeg", "brew install ffmpeg"),
        ("ffprobe", "brew install ffmpeg"),
        ("whisper-cli", "brew install whisper-cpp"),
    ):
        path = shutil.which(tool)
        if path:
            print(f"  ✓ {tool}: {path}")
        else:
            ok = False
            print(f"  ✗ {tool}: not found — {install}")

    print("\nTranscription:")
    print(f"  model: {config.get('whisper_model')}")
    print(f"  VAD: {'on' if config.get('whisper_vad', True) else 'OFF (not recommended)'}")

    print("\nSpeaker attribution (diarization):")
    if not config.get("diarization_enabled", True):
        print("  - disabled in config")
    else:
        missing = [name for name in ("sherpa_onnx", "numpy") if not _importable(name)]
        if missing:
            ok = False
            print(f"  ✗ missing: {', '.join(missing)}")
            print("    install with: pip install 'transcribe[diarize]'")
        else:
            print("  ✓ sherpa-onnx and numpy available")

    print("\nCalendar:")
    if not config.get("calendar_enabled", True):
        print("  - disabled in config")
    elif not _importable("EventKit"):
        print("  ✗ pyobjc-framework-EventKit not installed")
        print("    install with: pip install 'transcribe[calendar]'")
    else:
        _report_calendar_status()

    print("\nLLM provider:")
    provider = (config.get("llm_provider") or "claude").strip().lower()
    key = config.get("openai_api_key" if provider == "openai" else "anthropic_api_key")
    if key:
        model = config.get("openai_model" if provider == "openai" else "anthropic_model")
        print(f"  ✓ {provider} configured (model: {model})")
    else:
        print(f"  ✗ {provider} selected but no API key set in {CONFIG_FILE}")
        print("    Without it you still get transcripts, but no notes or summaries.")

    print("\nSlack:")
    if config.get("slack_bot_token") or config.get("slack_webhook_url"):
        print("  ✓ configured")
    else:
        print("  - not configured (optional)")

    print()
    return 0 if ok else 1


def _importable(module_name):
    """True when ``module_name`` can be imported."""
    import importlib.util

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _report_calendar_status():
    """Print the current EventKit authorization status."""
    from .calendars import CalendarUnavailable, authorization_status

    try:
        status, label = authorization_status()
    except CalendarUnavailable as e:
        print(f"  ✗ {e}")
        return
    if status in (3, 5):
        print(f"  ✓ access granted ({label})")
    elif status == 0:
        print("  - not yet requested — run: transcribe calendar-check")
    else:
        print(f"  ✗ access {label} — enable under System Settings > Privacy & Security > Calendars")


def calendar_check():
    """Trigger the macOS Calendar permission prompt and list upcoming events.

    Run this from a normal terminal session. A launchd daemon has no UI to show
    the permission prompt, so access has to be granted interactively once.
    """
    from datetime import datetime, timedelta

    from .calendars import CalendarUnavailable, fetch_macos_events

    config = load_config()
    now = datetime.now()
    try:
        events = fetch_macos_events(now - timedelta(days=1), now + timedelta(days=7), config)
    except CalendarUnavailable as e:
        print(f"✗ {e}")
        return 1
    except Exception as e:
        print(f"✗ Calendar lookup failed ({type(e).__name__}: {e})")
        return 1

    print(f"✓ Calendar access working — {len(events)} event(s) in the next 7 days")
    for event in events[:15]:
        attendees = f" — {len(event['attendees'])} attendee(s)" if event["attendees"] else ""
        print(f"  {event['start'][:16].replace('T', ' ')}  {event['title']}{attendees}")
    if not events:
        print("  (no events found — check that Calendar.app has your accounts synced)")
    return 0


def _print_usage():
    print("Usage:")
    print("  transcribe <video_file> [--json] [--flat] [--no-split]")
    print("                                    - Transcribe a single file")
    print("  transcribe watch [directory]      - Watch directory for new files")
    print("  transcribe setup-daemon           - Install background daemon")
    print("  transcribe config                 - Show/edit configuration")
    print("  transcribe doctor                 - Check dependencies and models")
    print("  transcribe calendar-check         - Verify macOS Calendar access")
    print("  transcribe --version              - Show version information")


def _print_version():
    # Prefer package metadata when available
    try:
        from importlib.metadata import version as _version

        ver = _version("transcribe")
    except Exception:
        ver = __version__
    source = "brew/pyinstaller" if getattr(sys, "frozen", False) else "python package"
    print(f"transcribe {ver} ({source})")


def main():
    """Main entry point for the transcribe command."""
    # Strip global flags before command dispatch so that e.g. `transcribe watch
    # --json` does not mistake a flag for the watch directory.
    argv = sys.argv[1:]
    flags = {
        "--json": "write_json",
        "--flat": "flat",
        "--no-split": "no_split",
        "--no-diarize": "no_diarize",
    }
    selected = {name for arg, name in flags.items() if arg in argv}
    args = [arg for arg in argv if arg not in flags]

    if not args:
        _print_usage()
        sys.exit(1)

    command = args[0]

    if command in ["--help", "-h", "help"]:
        _print_usage()
        sys.exit(0)
    elif command in ["--version", "-v", "version"]:
        _print_version()
        sys.exit(0)
    elif command == "config":
        configure()
    elif command == "doctor":
        sys.exit(doctor())
    elif command == "calendar-check":
        sys.exit(calendar_check())
    elif command == "setup-daemon":
        config = load_config()
        setup_daemon(config)
    elif command == "watch":
        config = _apply_flags(load_config(), selected)
        directory = args[1] if len(args) > 1 else config["watch_directory"]
        watch_directory(directory, config)
    else:
        # Single-file mode.
        video_file = args[0]
        if not Path(video_file).exists():
            print(f"Error: File not found: {video_file}")
            sys.exit(1)

        config = _apply_flags(load_config(), selected)
        process_video_file(video_file, config, write_json="write_json" in selected)


def _apply_flags(config, selected):
    """Let command-line flags override the corresponding config keys."""
    if "flat" in selected:
        config["meeting_mode"] = False
    if "no_split" in selected:
        config["split_meetings"] = False
        config["split_video"] = False
    if "no_diarize" in selected:
        config["diarization_enabled"] = False
    return config


if __name__ == "__main__":
    main()
