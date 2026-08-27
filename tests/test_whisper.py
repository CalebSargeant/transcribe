"""Tests for transcribe.whisper: model resolution, download, transcription."""

import json
import subprocess
import sys

import pytest

from transcribe import whisper
from transcribe.whisper import (
    _download_model,
    _ensure_model,
    _validate_model_name,
    transcribe_video,
)

# --- _validate_model_name ---------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
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
    ],
)
def test_validate_model_name_accepts_allowlisted(name):
    assert _validate_model_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "large",  # ggml-large.bin 404s; only versioned names are valid
        "huge",
        "",
        "../../etc/passwd",
        "..",
        "base/../../x",
        "sub/base",
        "base\\evil",
        "BASE",  # case-sensitive
        None,
    ],
)
def test_validate_model_name_rejects_invalid(name):
    with pytest.raises(ValueError, match="Invalid whisper_model"):
        _validate_model_name(name)


def test_ensure_model_rejects_invalid_before_download(monkeypatch):
    """An invalid model name is rejected before any path or URL is built."""
    download_called = []
    monkeypatch.setattr(whisper, "_download", lambda *a, **k: download_called.append(a))
    with pytest.raises(ValueError, match="Invalid whisper_model"):
        _ensure_model("../../evil")
    assert download_called == []


# --- _ensure_model ----------------------------------------------------------


def test_ensure_model_prefers_bundled_path(monkeypatch, tmp_path):
    """If a model sits next to the package (or in _MEIPASS), use it directly."""
    bundle = tmp_path / "bundle"
    (bundle / "models").mkdir(parents=True)
    bundled = bundle / "models" / "ggml-base.bin"
    bundled.write_bytes(b"fake-model")

    # Simulate frozen bundle: sys._MEIPASS points at the bundle root.
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    download_called = []
    monkeypatch.setattr(whisper, "_download", lambda *a, **k: download_called.append(a))

    path = _ensure_model("base")
    assert path == str(bundled)
    assert download_called == []


def test_ensure_model_falls_back_to_home_and_downloads(monkeypatch, tmp_path):
    """When no bundled model and no home model exist, the download is triggered."""
    # Ensure no _MEIPASS so it resolves relative to the package (no model there).
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    home = tmp_path / "home"
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", str(home)))

    downloads = []

    def fake_download(url, dest_path, label):
        downloads.append((url, dest_path))
        # Pretend the download created the file.
        import os

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        open(dest_path, "wb").close()

    monkeypatch.setattr(whisper, "_download", fake_download)

    path = _ensure_model("small")

    expected = str(home / ".whisper-models" / "ggml-small.bin")
    assert path == expected
    assert downloads == [(f"{whisper.HF_MODEL_BASE_URL}/ggml-small.bin", expected)]


def test_ensure_model_uses_existing_home_model_without_download(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    home = tmp_path / "home"
    model_dir = home / ".whisper-models"
    model_dir.mkdir(parents=True)
    existing = model_dir / "ggml-base.bin"
    existing.write_bytes(b"already here")
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", str(home)))

    download_called = []
    monkeypatch.setattr(whisper, "_download", lambda *a, **k: download_called.append(a))

    path = _ensure_model("base")
    assert path == str(existing)
    assert download_called == []


# --- _download_model --------------------------------------------------------


def test_download_model_builds_hf_url_and_renames(monkeypatch, tmp_path):
    dest = tmp_path / "models" / "ggml-base.bin"
    captured = {}

    def fake_urlretrieve(url, tmp_path_arg, reporthook):
        captured["url"] = url
        captured["tmp"] = tmp_path_arg
        # urlretrieve writes the .part file.
        with open(tmp_path_arg, "wb") as f:
            f.write(b"downloaded-bytes")
        # exercise the progress reporter
        reporthook(1, 1024, 2048)
        reporthook(2, 1024, 2048)
        return tmp_path_arg, None

    monkeypatch.setattr("urllib.request.urlretrieve", fake_urlretrieve)

    _download_model("base", str(dest))

    assert captured["url"] == f"{whisper.HF_MODEL_BASE_URL}/ggml-base.bin"
    assert captured["tmp"] == str(dest) + ".part"
    # Atomic rename: final file exists, .part is gone.
    assert dest.exists()
    assert dest.read_bytes() == b"downloaded-bytes"
    assert not (tmp_path / "models" / "ggml-base.bin.part").exists()


def test_download_model_cleans_up_part_on_failure(monkeypatch, tmp_path):
    dest = tmp_path / "models" / "ggml-base.bin"

    def fake_urlretrieve(url, tmp_path_arg, reporthook):
        # Create the partial file, then fail.
        import os

        os.makedirs(os.path.dirname(tmp_path_arg), exist_ok=True)
        with open(tmp_path_arg, "wb") as f:
            f.write(b"partial")
        raise OSError("network died")

    monkeypatch.setattr("urllib.request.urlretrieve", fake_urlretrieve)

    with pytest.raises(OSError, match="network died"):
        _download_model("base", str(dest))

    # Partial file cleaned up, final file never created.
    assert not (tmp_path / "models" / "ggml-base.bin.part").exists()
    assert not dest.exists()


# --- transcribe_video -------------------------------------------------------


@pytest.fixture
def whisper_env(monkeypatch):
    """Mock tool discovery and model resolution, and fake whisper's JSON output.

    whisper-cli writes its result to ``<-of stem>.json``; the fake run() writes
    that file so the parser has something real to read.
    """
    monkeypatch.setattr(whisper.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(whisper, "_ensure_model", lambda name="base": "/models/ggml-base.bin")
    monkeypatch.setattr(whisper, "_ensure_vad_model", lambda: "/models/ggml-vad.bin")

    calls = []
    payload = {
        "transcription": [
            {
                "timestamps": {"from": "00:00:00,000", "to": "00:00:02,500"},
                "text": " Hello world.",
            },
            {
                "timestamps": {"from": "00:01:05,000", "to": "00:01:07,000"},
                "text": " More text.",
            },
            {"timestamps": {"from": "00:02:00,000", "to": "00:02:01,000"}, "text": "   "},
        ]
    }

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "whisper-cli" in cmd[0]:
            stem = cmd[cmd.index("-of") + 1]
            with open(stem + ".json", "w") as handle:
                json.dump(payload, handle)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(whisper.subprocess, "run", fake_run)
    return calls


def test_transcribe_video_joins_segment_text(whisper_env, base_config):
    text = transcribe_video("/some/video.mov", base_config)
    # Blank segments are dropped; the rest are joined with a single space.
    assert text == "Hello world. More text."


def test_transcribe_segments_carry_timestamps(whisper_env, base_config):
    segments, audio_path = whisper.transcribe_video_segments("/some/video.mov", base_config)
    whisper.os.unlink(audio_path)
    assert [(s.start, s.end, s.text) for s in segments] == [
        (0.0, 2.5, "Hello world."),
        (65.0, 67.0, "More text."),
    ]


def test_transcribe_video_invokes_ffmpeg_then_whisper(whisper_env, base_config):
    transcribe_video("/some/video.mov", base_config)
    # First call ffmpeg, second whisper-cli.
    assert whisper_env[0][0] == "/usr/bin/ffmpeg"
    assert "/some/video.mov" in whisper_env[0]
    assert whisper_env[1][0] == "/usr/bin/whisper-cli"
    assert "/models/ggml-base.bin" in whisper_env[1]


def test_transcribe_video_enables_vad_by_default(whisper_env, base_config):
    transcribe_video("/some/video.mov", base_config)
    assert "--vad" in whisper_env[1]
    assert "/models/ggml-vad.bin" in whisper_env[1]


def test_transcribe_video_vad_can_be_disabled(whisper_env, base_config):
    base_config["whisper_vad"] = False
    transcribe_video("/some/video.mov", base_config)
    assert "--vad" not in whisper_env[1]


def test_transcribe_video_passes_initial_prompt(whisper_env, base_config):
    base_config["whisper_prompt"] = "Terraform, MikroTik, BGP"
    transcribe_video("/some/video.mov", base_config)
    assert whisper_env[1][whisper_env[1].index("--prompt") + 1] == "Terraform, MikroTik, BGP"


def test_transcribe_video_passes_configured_model(whisper_env, base_config, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        whisper, "_ensure_model", lambda name="base": seen.setdefault("model", name) or "/m.bin"
    )
    base_config["whisper_model"] = "medium"
    transcribe_video("/v.mov", base_config)
    assert seen["model"] == "medium"


def test_transcribe_video_cleans_up_temp_audio(whisper_env, base_config, monkeypatch):
    extracted = []
    monkeypatch.setattr(
        whisper, "extract_audio", lambda video, audio: extracted.append(audio) or audio
    )

    transcribe_video("/v.mov", base_config)

    # The temp .wav is created, then removed once the transcript is parsed.
    assert extracted and extracted[0].endswith(".wav")
    assert not whisper.os.path.exists(extracted[0])


def test_transcribe_video_exits_on_subprocess_error(monkeypatch, base_config):
    monkeypatch.setattr(whisper.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(whisper, "_ensure_model", lambda name="base": "/m.bin")

    def fake_run(cmd, **k):
        raise subprocess.CalledProcessError(1, cmd, stderr="boom")

    monkeypatch.setattr(whisper.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        transcribe_video("/v.mov", base_config)
    assert exc.value.code == 1


def test_transcribe_video_exits_when_tool_missing(monkeypatch, base_config):
    monkeypatch.setattr(whisper.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(whisper, "_ensure_model", lambda name="base": "/m.bin")

    def fake_run(cmd, **k):
        raise FileNotFoundError("no ffmpeg")

    monkeypatch.setattr(whisper.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        transcribe_video("/v.mov", base_config)
    assert exc.value.code == 1
