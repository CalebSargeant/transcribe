"""Whisper CLI transcription."""

import os
import shutil
import subprocess
import sys
import tempfile

# Base URL for the ggml whisper models hosted on Hugging Face.
HF_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

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
    home_path = os.path.expanduser(f"~/.whisper-models/{filename}")
    if not os.path.exists(home_path):
        _download_model(model_name, home_path)
    return home_path


def _download_model(model_name, dest_path):
    """Download a ggml model from Hugging Face to dest_path with progress."""
    import urllib.request

    url = f"{HF_MODEL_BASE_URL}/ggml-{model_name}.bin"
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    print(f"Whisper model '{model_name}' not found. Downloading from {url} ...")

    def _report(block_num, block_size, total_size):
        if total_size <= 0:
            return
        downloaded = block_num * block_size
        pct = min(downloaded * 100 // total_size, 100)
        mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        print(f"\r  Downloading model: {pct}% ({mb:.1f}/{total_mb:.1f} MB)", end="")

    tmp_path = dest_path + ".part"
    try:
        urllib.request.urlretrieve(url, tmp_path, _report)
        print()  # newline after the progress line
        os.replace(tmp_path, dest_path)
        print(f"✓ Model downloaded to {dest_path}")
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def transcribe_video(video_path, config=None):
    """Transcribe a video file and return the text."""
    # Normalize to an absolute path so a filename starting with "-" is not
    # parsed as an option by the ffmpeg/whisper-cli subprocess (argument
    # injection, e.g. via a malicious filename dropped into a watched folder).
    video_path = os.path.abspath(video_path)
    print(f"Extracting audio from {video_path}...")

    # Find tools in PATH
    ffmpeg_bin = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    whisper_bin = shutil.which("whisper-cli") or "/opt/homebrew/bin/whisper-cli"

    model_name = (config or {}).get("whisper_model") or "base"

    # Extract audio to WAV for faster processing
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        audio_path = temp_audio.name

    try:
        # Extract audio using ffmpeg
        subprocess.run(
            [
                ffmpeg_bin,
                "-i",
                video_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                audio_path,
                "-y",
            ],
            check=True,
            capture_output=True,
        )

        print("Transcribing audio (this may take a while for long files)...")

        # Resolve the model path, downloading it if it is missing.
        model_path = _ensure_model(model_name)

        # Use whisper-cli with progress
        result = subprocess.run(
            [whisper_bin, "-m", model_path, "-f", audio_path, "-nt", "-pp"],
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse output - whisper-cli prints transcription to stdout
        lines = result.stdout.strip().split("\n")
        # Filter out debug/info lines and keep only transcription
        text_lines = [line for line in lines if not line.startswith(("whisper_", "ggml_", "["))]

        return " ".join(text_lines).strip()

    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: Required tool not found. Install with: brew install whisper-cpp ffmpeg")
        sys.exit(1)
    finally:
        # Clean up temporary audio file
        if os.path.exists(audio_path):
            os.unlink(audio_path)
