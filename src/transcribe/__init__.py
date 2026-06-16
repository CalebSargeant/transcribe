"""Transcribe video/audio files using Whisper CLI.

Auto-watch, OpenAI summarization, and Slack notifications.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("transcribe")
except PackageNotFoundError:  # pragma: no cover - package not installed
    __version__ = "0.0.0"

__all__ = ["__version__"]
