"""Tests for transcribe.config: load/save + defaults + merge behavior."""

import yaml

from transcribe import config as config_mod
from transcribe.config import DEFAULT_CONFIG, load_config, save_config


def test_default_config_has_expected_keys():
    expected = {
        "watch_directory",
        "destination_directory",
        "llm_provider",
        "anthropic_api_key",
        "anthropic_model",
        "openai_api_key",
        "openai_model",
        "slack_webhook_url",
        "video_extensions",
        "whisper_model",
        "icloud_base_url",
    }
    assert expected.issubset(set(DEFAULT_CONFIG.keys()))


def test_default_provider_is_claude():
    assert DEFAULT_CONFIG["llm_provider"] == "claude"
    assert DEFAULT_CONFIG["anthropic_model"] == "claude-haiku-4-5-20251001"
    assert DEFAULT_CONFIG["openai_model"] == "gpt-4o-mini"
    assert DEFAULT_CONFIG["whisper_model"] == "large-v3-turbo"


def test_load_config_creates_default_when_missing(patched_config_paths, capsys):
    _config_dir, config_file = patched_config_paths
    assert not config_file.exists()

    config = load_config()

    # File was created with the defaults serialized as YAML
    assert config_file.exists()
    assert config == DEFAULT_CONFIG
    on_disk = yaml.safe_load(config_file.read_text())
    assert on_disk == DEFAULT_CONFIG

    out = capsys.readouterr().out
    assert "Created default config" in out


def test_load_config_reads_existing_file(patched_config_paths):
    config_dir, config_file = patched_config_paths
    config_dir.mkdir(parents=True, exist_ok=True)
    custom = dict(DEFAULT_CONFIG)
    custom["openai_api_key"] = "sk-existing"
    custom["llm_provider"] = "openai"
    config_file.write_text(yaml.dump(custom))

    config = load_config()

    assert config["openai_api_key"] == "sk-existing"
    assert config["llm_provider"] == "openai"


def test_load_config_merges_missing_defaults(patched_config_paths):
    """An older config missing the new keys is back-filled from DEFAULT_CONFIG."""
    config_dir, config_file = patched_config_paths
    config_dir.mkdir(parents=True, exist_ok=True)
    # Simulate a legacy config that still has explicit watch + both keys, so the
    # OpenAI back-compat default does NOT trigger (anthropic key present).
    legacy = {
        "watch_directory": "/legacy/watch",
        "openai_api_key": "sk-old",
        "anthropic_api_key": "sk-ant",
    }
    config_file.write_text(yaml.dump(legacy))

    config = load_config()

    # Existing values preserved
    assert config["watch_directory"] == "/legacy/watch"
    assert config["openai_api_key"] == "sk-old"
    # Newer keys merged from defaults
    assert config["llm_provider"] == DEFAULT_CONFIG["llm_provider"]
    assert config["anthropic_model"] == DEFAULT_CONFIG["anthropic_model"]
    assert config["whisper_model"] == DEFAULT_CONFIG["whisper_model"]


def test_load_config_openai_only_legacy_defaults_to_openai(patched_config_paths):
    """A legacy OpenAI-only config (no anthropic key, no explicit provider)
    defaults llm_provider to 'openai' so existing users keep summaries."""
    config_dir, config_file = patched_config_paths
    config_dir.mkdir(parents=True, exist_ok=True)
    legacy = {"watch_directory": "/legacy/watch", "openai_api_key": "sk-old"}
    config_file.write_text(yaml.dump(legacy))

    config = load_config()

    assert config["llm_provider"] == "openai"
    assert config["openai_api_key"] == "sk-old"


def test_load_config_openai_only_respects_explicit_provider(patched_config_paths):
    """If the user explicitly set llm_provider, back-compat must not override it."""
    config_dir, config_file = patched_config_paths
    config_dir.mkdir(parents=True, exist_ok=True)
    legacy = {"openai_api_key": "sk-old", "llm_provider": "claude"}
    config_file.write_text(yaml.dump(legacy))

    config = load_config()

    assert config["llm_provider"] == "claude"


def test_load_config_keeps_claude_default_when_no_keys(patched_config_paths):
    """No keys at all -> provider stays the default 'claude'."""
    config_dir, config_file = patched_config_paths
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text(yaml.dump({"watch_directory": "/w"}))

    config = load_config()

    assert config["llm_provider"] == "claude"


def test_load_config_does_not_overwrite_present_keys(patched_config_paths):
    config_dir, config_file = patched_config_paths
    config_dir.mkdir(parents=True, exist_ok=True)
    custom = {"llm_provider": "openai"}
    # Provide all keys so merge does nothing for llm_provider specifically
    config_file.write_text(yaml.dump(custom))

    config = load_config()
    assert config["llm_provider"] == "openai"  # not clobbered by default "claude"


def test_save_config_round_trips(patched_config_paths):
    _config_dir, config_file = patched_config_paths
    cfg = dict(DEFAULT_CONFIG)
    cfg["anthropic_api_key"] = "sk-ant-123"

    save_config(cfg)

    assert config_file.exists()
    reloaded = yaml.safe_load(config_file.read_text())
    assert reloaded["anthropic_api_key"] == "sk-ant-123"


def test_save_config_creates_dir_if_absent(patched_config_paths):
    config_dir, config_file = patched_config_paths
    assert not config_dir.exists()

    save_config(dict(DEFAULT_CONFIG))

    assert config_dir.exists()
    assert config_file.exists()


def test_save_config_sets_restrictive_permissions(patched_config_paths):
    config_dir, config_file = patched_config_paths

    save_config(dict(DEFAULT_CONFIG))

    # Config holds secrets: dir 0700, file 0600.
    assert (config_dir.stat().st_mode & 0o777) == 0o700
    assert (config_file.stat().st_mode & 0o777) == 0o600


def test_load_config_default_creation_sets_restrictive_permissions(patched_config_paths):
    config_dir, config_file = patched_config_paths
    assert not config_file.exists()

    load_config()

    assert (config_dir.stat().st_mode & 0o777) == 0o700
    assert (config_file.stat().st_mode & 0o777) == 0o600


def test_config_file_path_under_home():
    # Module-level constants point at ~/.transcribe/config.yaml
    assert config_mod.CONFIG_DIR.name == ".transcribe"
    assert config_mod.CONFIG_FILE.name == "config.yaml"
