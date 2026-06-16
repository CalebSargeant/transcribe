#!/usr/bin/env python3
"""Command-line entry point for transcribe.

Usage:
  transcribe <video_file>           - Transcribe a single file
  transcribe watch <directory>      - Watch directory for new files
  transcribe setup-daemon           - Install background daemon
  transcribe config                 - Configure settings
  transcribe --version              - Show version information
Requires: brew install whisper-cpp ffmpeg
"""

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
    print("  - openai_api_key: For transcript summarization")
    print("  - slack_webhook_url: For notifications")


def _print_usage():
    print("Usage:")
    print("  transcribe <video_file> [--json]  - Transcribe a single file")
    print("  transcribe watch [directory]      - Watch directory for new files")
    print("  transcribe setup-daemon           - Install background daemon")
    print("  transcribe config                 - Show/edit configuration")
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
    # Strip --json globally before command dispatch. It only affects single-file
    # mode (writes a <video>_result.json); stripping it first means e.g.
    # `transcribe watch --json` does not mistake "--json" for the watch dir.
    write_json = "--json" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--json"]

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
    elif command == "setup-daemon":
        config = load_config()
        setup_daemon(config)
    elif command == "watch":
        config = load_config()
        directory = args[1] if len(args) > 1 else config["watch_directory"]
        watch_directory(directory, config)
    else:
        # Single-file mode. The optional --json flag (already stripped above)
        # also writes a <video>_result.json alongside the .txt outputs.
        video_file = args[0]
        if not Path(video_file).exists():
            print(f"Error: File not found: {video_file}")
            sys.exit(1)

        config = load_config()
        process_video_file(video_file, config, write_json=write_json)


if __name__ == "__main__":
    main()
