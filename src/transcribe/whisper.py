"""Local transcription via whisper.cpp (``whisper-cli``).

Produces timestamped segments rather than one flat blob, because everything
downstream -- speaker attribution, meeting splitting, and the timestamped
"Details" section of the notes -- is anchored to time.

Voice Activity Detection is on by default and matters more than it sounds.
A long recording usually contains stretches of room tone rather than digital
silence; fed that, whisper hallucinates filler ("Thank you." on repeat) and can
lock into a repetition loop that ruins every following hour. Silero VAD skips
non-speech and resets decoder state per speech chunk, which contains the damage.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from difflib import SequenceMatcher

from .media import extract_audio
from .segments import Segment

# Base URLs for the ggml models hosted on Hugging Face.
HF_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
HF_VAD_BASE_URL = "https://huggingface.co/ggml-org/whisper-vad/resolve/main"

# Silero VAD model shipped for whisper.cpp.
VAD_MODEL_NAME = "silero-v5.1.2"


def model_dir():
    """Where downloaded ggml models live.

    Resolved per call rather than at import so the location follows $HOME.
    """
    return os.path.expanduser("~/.whisper-models")


# Allowlist of valid ggml whisper model names. The model name flows from config
# into both a download URL and a local filesystem path, so it must be validated
# against this fixed set to prevent path traversal (e.g. "../../x") and
# malformed URLs.
# TODO: pin model checksums (SHA256) to verify downloaded model integrity.
ALLOWED_WHISPER_MODELS = frozenset(
    {
        "tiny",
        "tiny.en",
        "base",
        "base.en",
        "small",
        "small.en",
        "medium",
        "medium.en",
        "large-v1",
        "large-v2",
        "large-v3",
        "large-v3-turbo",
    }
)


def _validate_model_name(model_name):
    """Validate ``model_name`` against the allowlist, returning it unchanged.

    Raises ValueError for any name outside ``ALLOWED_WHISPER_MODELS`` or one
    that contains path separators / traversal sequences. This runs BEFORE the
    name is used to build a download URL or a local file path.
    """
    if (
        not isinstance(model_name, str)
        or "/" in model_name
        or "\\" in model_name
        or ".." in model_name
        or os.sep in model_name
        or model_name not in ALLOWED_WHISPER_MODELS
    ):
        allowed = ", ".join(sorted(ALLOWED_WHISPER_MODELS))
        raise ValueError(f"Invalid whisper_model {model_name!r}. Allowed models: {allowed}")
    return model_name


def _download(url, dest_path, label):
    """Download ``url`` to ``dest_path`` atomically, printing progress."""
    import urllib.request

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    print(f"{label} not found. Downloading from {url} ...")

    def _report(block_num, block_size, total_size):
        if total_size <= 0:
            return
        downloaded = block_num * block_size
        pct = min(downloaded * 100 // total_size, 100)
        mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        print(f"\r  Downloading: {pct}% ({mb:.1f}/{total_mb:.1f} MB)", end="")

    tmp_path = dest_path + ".part"
    try:
        urllib.request.urlretrieve(url, tmp_path, _report)
        print()  # newline after the progress line
        os.replace(tmp_path, dest_path)
        print(f"✓ Downloaded to {dest_path}")
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _ensure_model(model_name="base"):
    """Resolve the path to the ggml model, downloading it if it is missing.

    Resolution order:
      1. A model bundled next to the package / inside a PyInstaller bundle.
      2. ``~/.whisper-models/ggml-<model_name>.bin`` -- downloaded on demand
         from Hugging Face if not already present.
    """
    # Validate before the name is used in any path or URL.
    model_name = _validate_model_name(model_name)
    filename = f"ggml-{model_name}.bin"

    # Find model relative to the bundle/package location.
    # When frozen by PyInstaller the data files live under sys._MEIPASS;
    # otherwise resolve relative to this module's directory.
    script_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    bundled_path = os.path.join(script_dir, "models", filename)
    if os.path.exists(bundled_path):
        return bundled_path

    # Fall back to the home directory, downloading the model if necessary.
    home_path = os.path.join(model_dir(), filename)
    if not os.path.exists(home_path):
        _download(f"{HF_MODEL_BASE_URL}/{filename}", home_path, f"Whisper model {model_name!r}")
    return home_path


def _ensure_vad_model():
    """Resolve the Silero VAD model path, downloading it (~1 MB) if missing."""
    filename = f"ggml-{VAD_MODEL_NAME}.bin"
    script_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    bundled_path = os.path.join(script_dir, "models", filename)
    if os.path.exists(bundled_path):
        return bundled_path

    home_path = os.path.join(model_dir(), filename)
    if not os.path.exists(home_path):
        _download(f"{HF_VAD_BASE_URL}/{filename}", home_path, "Silero VAD model")
    return home_path


def _download_model(model_name, dest_path):
    """Download a ggml whisper model. Retained for backwards compatibility."""
    _download(
        f"{HF_MODEL_BASE_URL}/ggml-{model_name}.bin",
        dest_path,
        f"Whisper model {model_name!r}",
    )


def _timestamp_to_seconds(value):
    """Convert a whisper ``HH:MM:SS,mmm`` timestamp into float seconds."""
    hours, minutes, rest = value.split(":")
    seconds, _, millis = rest.partition(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis or 0) / 1000.0


def _parse_whisper_json(json_path):
    """Parse whisper-cli's ``-oj`` output into a list of ``Segment``."""
    with open(json_path) as handle:
        payload = json.load(handle)

    segments = []
    for entry in payload.get("transcription", []):
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        stamps = entry.get("timestamps") or {}
        try:
            start = _timestamp_to_seconds(stamps["from"])
            end = _timestamp_to_seconds(stamps["to"])
        except (KeyError, ValueError):
            # Fall back to the raw offsets (milliseconds) when present.
            offsets = entry.get("offsets") or {}
            start = offsets.get("from", 0) / 1000.0
            end = offsets.get("to", 0) / 1000.0
        segments.append(Segment(start=start, end=end, text=text))
    return segments


# A long sentence repeated back to back is a decoder loop, not speech. Short
# utterances ("Yes.", "Yeah.") genuinely do repeat, so they get more leeway.
LOOP_LONG_TEXT_CHARS = 25
LOOP_KEEP_LONG = 1
LOOP_KEEP_SHORT = 2
# A loop drifts as it repeats ("We're going to..." becomes "It's going to..."),
# so exact matching misses the tail of one. Long lines are compared by
# similarity instead; short ones are not, because "Yes." and "Yeah." are
# genuinely different words.
LOOP_SIMILARITY = 0.85


def _normalise(text):
    """Lowercase, strip punctuation and spacing, for comparing repeats."""
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def _same_run(current, previous):
    """True when two consecutive lines are the same utterance repeating."""
    if not previous or not current:
        return False
    if current == previous:
        return True
    if min(len(current), len(previous)) <= LOOP_LONG_TEXT_CHARS:
        return False
    return SequenceMatcher(None, current, previous).ratio() >= LOOP_SIMILARITY


def collapse_repetitions(segments):
    """Collapse runs of identical consecutive segments.

    Whisper falls into repetition loops on ambiguous audio, emitting the same
    sentence for minutes. VAD contains the worst of it by resetting decoder
    state per speech chunk, but a loop inside one chunk still gets through, and
    the notes step will then faithfully summarise a hallucination.

    Returns ``(segments, dropped)``.
    """
    kept = []
    dropped = 0
    run_text = None
    run_length = 0

    for segment in segments:
        normalised = _normalise(segment.text)
        if normalised and _same_run(normalised, run_text):
            run_length += 1
        else:
            run_text = normalised
            run_length = 1

        allowed = LOOP_KEEP_LONG if len(normalised) > LOOP_LONG_TEXT_CHARS else LOOP_KEEP_SHORT
        if run_length <= allowed:
            kept.append(segment)
        else:
            dropped += 1

    return kept, dropped


def transcribe_audio_segments(audio_path, config=None):
    """Transcribe a 16 kHz mono WAV, returning a list of timestamped ``Segment``."""
    config = config or {}
    whisper_bin = shutil.which("whisper-cli") or "/opt/homebrew/bin/whisper-cli"

    model_name = config.get("whisper_model") or "base"
    model_path = _ensure_model(model_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_stem = os.path.join(tmpdir, "transcript")
        cmd = [
            whisper_bin,
            "-m",
            model_path,
            "-f",
            audio_path,
            "-t",
            str(config.get("whisper_threads") or 8),
            "-l",
            config.get("whisper_language") or "en",
            "-oj",
            "-of",
            out_stem,
            "-pp",
        ]

        # Suppressing non-speech tokens removes the "(clears throat)"-style
        # artifacts that also seed hallucination loops.
        if config.get("whisper_suppress_non_speech", True):
            cmd.append("-sns")

        if config.get("whisper_vad", True):
            cmd += ["--vad", "-vm", _ensure_vad_model()]
            cmd += ["-vt", str(config.get("whisper_vad_threshold", 0.5))]

        # An initial prompt biases the decoder toward domain vocabulary, which
        # noticeably improves proper nouns and technical jargon.
        prompt = config.get("whisper_prompt")
        if prompt:
            cmd += ["--prompt", str(prompt)]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running whisper-cli: {e}")
            print(f"Stderr: {e.stderr}")
            raise
        except FileNotFoundError as e:
            raise FileNotFoundError(
                "whisper-cli not found. Install with: brew install whisper-cpp"
            ) from e

        segments = _parse_whisper_json(out_stem + ".json")
        if config.get("whisper_collapse_repetitions", True):
            segments, dropped = collapse_repetitions(segments)
            if dropped:
                print(f"  Dropped {dropped} repeated segment(s) from decoder loops")
        return segments


def transcribe_video_segments(video_path, config=None):
    """Extract audio from a video and transcribe it into timestamped segments.

    Returns ``(segments, audio_path)``. The caller owns ``audio_path`` and is
    responsible for deleting it -- later stages (diarization) reuse the same
    WAV rather than paying for a second extraction.
    """
    # Normalize to an absolute path so a filename starting with "-" is not
    # parsed as an option by the ffmpeg/whisper-cli subprocess (argument
    # injection, e.g. via a malicious filename dropped into a watched folder).
    video_path = os.path.abspath(video_path)
    print(f"Extracting audio from {video_path}...")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        audio_path = temp_audio.name

    try:
        extract_audio(video_path, audio_path)
    except subprocess.CalledProcessError as e:
        os.unlink(audio_path)
        print(f"Error extracting audio: {e}")
        print(f"Stderr: {e.stderr}")
        raise
    except FileNotFoundError as e:
        os.unlink(audio_path)
        raise FileNotFoundError("ffmpeg not found. Install with: brew install ffmpeg") from e

    print("Transcribing audio (this may take a while for long files)...")
    try:
        segments = transcribe_audio_segments(audio_path, config)
    except Exception:
        os.unlink(audio_path)
        raise

    return segments, audio_path


def transcribe_video(video_path, config=None):
    """Transcribe a video file and return the text.

    Kept for backwards compatibility with the pre-segment API: callers that only
    want a flat transcript still get one.
    """
    try:
        segments, audio_path = transcribe_video_segments(video_path, config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except subprocess.CalledProcessError:
        sys.exit(1)

    os.unlink(audio_path)
    return " ".join(segment.text for segment in segments).strip()
