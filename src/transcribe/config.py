"""Configuration loading and saving for transcribe."""

import os
from pathlib import Path

import yaml

# Configuration
CONFIG_DIR = Path.home() / ".transcribe"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DEFAULT_CONFIG = {
    "watch_directory": str(Path.home() / "Movies"),
    "destination_directory": str(
        Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Movies"
    ),
    # LLM provider for summaries/titles/action items: "claude" (default) or "openai".
    "llm_provider": "claude",
    # Anthropic (Claude) settings. Default is the current Claude Haiku 4.5.
    "anthropic_api_key": "",
    "anthropic_model": "claude-haiku-4-5-20251001",
    # OpenAI settings (used when llm_provider is "openai").
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "slack_webhook_url": "",
    "video_extensions": [".mov", ".mp4", ".avi", ".mkv", ".m4v"],
    # Whisper model name (ggml-<name>.bin); auto-downloaded if missing.
    "whisper_model": "base",
    "icloud_base_url": "https://www.icloud.com/iclouddrive/",  # Users can customize this
}


def load_config():
    """Load configuration from file or create default."""
    if not CONFIG_FILE.exists():
        # Config can contain API keys and tokens; keep dir/file private.
        CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
        os.chmod(CONFIG_FILE, 0o600)
        print(f"Created default config at {CONFIG_FILE}")
        print("Please edit it to add your OpenAI API key and Slack webhook URL.")
        return DEFAULT_CONFIG

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    # Capture the on-disk state before merging defaults, so back-compat logic
    # below can distinguish what the user actually configured.
    had_openai_key = bool(config.get("openai_api_key"))
    had_anthropic_key = bool(config.get("anthropic_api_key"))
    had_explicit_provider = "llm_provider" in config

    # Merge with defaults for any missing keys
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value

    # Back-compat: an existing OpenAI-only config (set before Claude became the
    # default provider) had no llm_provider and no Anthropic key. Default such
    # configs to OpenAI so those users keep getting summaries.
    if had_openai_key and not had_anthropic_key and not had_explicit_provider:
        config["llm_provider"] = "openai"

    return config


def save_config(config):
    """Save configuration to file."""
    # Config can contain API keys and tokens; keep dir/file private.
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    os.chmod(CONFIG_FILE, 0o600)
