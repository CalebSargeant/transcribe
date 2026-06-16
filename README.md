# Transcribe

Automated video/audio transcription for macOS, with local Whisper transcription, LLM
summarization (Claude by default, OpenAI optional), and Slack notifications.

[Issues](https://github.com/CalebSargeant/transcribe/issues) ·
[Releases](https://github.com/CalebSargeant/transcribe/releases) ·
[Docs](docs/)

> macOS only. Tested on Apple Silicon and Intel Macs.

## What it does

- **Local transcription** — uses `whisper-cpp` for fast, private, on-device transcription.
- **Auto-download model** — the Whisper ggml model is fetched automatically on first use;
  no manual `curl` step required.
- **LLM summarization** — generates a summary, a title/description, and action items.
  Defaults to **Claude (Anthropic)**; OpenAI is supported as an alternative.
- **Auto-watch** — monitors a directory and processes new video files automatically.
- **Background daemon** — runs as a macOS `launchd` agent, starting on login.
- **Smart organization** — moves the video, transcript, and summary into a per-video folder
  in your destination directory (e.g. iCloud or Google Drive).
- **Slack notifications** — posts a formatted message (title, description, action items,
  folder link) when processing finishes.
- **JSON output** — pass `--json` to also emit a machine-readable `<video>_result.json`.
- **Multi-format** — any video format ffmpeg can read (MOV, MP4, AVI, MKV, M4V, ...).

## Quickstart

```bash
# 1. Install via Homebrew (the tap lives under MagmaMoose)
brew tap MagmaMoose/tap
brew install transcribe          # or: brew install magmamoose/tap/transcribe

# 2. Create the config file
transcribe config                # writes ~/.transcribe/config.yaml

# 3. Add an API key (Claude by default) — see Configuration below
#    Edit ~/.transcribe/config.yaml and set anthropic_api_key

# 4. Transcribe a file
transcribe meeting.mov
```

The Whisper model downloads itself on first run, and `whisper-cpp` + `ffmpeg` are pulled in
automatically as Homebrew dependencies.

For step-by-step setup (API keys, Slack, Google Drive), see
**[docs/install.md](docs/install.md)**.

## Configuration

Configuration lives in `~/.transcribe/config.yaml` (created by `transcribe config`).

```yaml
# Where to watch for new video files
watch_directory: /Users/you/Movies

# Where processed files are moved (a folder is created per video)
destination_directory: /Users/you/Library/Mobile Documents/com~apple~CloudDocs/Movies

# LLM provider for summaries/titles/action items: "claude" (default) or "openai"
llm_provider: claude

# Anthropic (Claude) settings — used when llm_provider is "claude" (default)
# Get a key at https://console.anthropic.com/
anthropic_api_key: sk-ant-...
anthropic_model: claude-haiku-4-5-20251001

# OpenAI settings — used when llm_provider is "openai"
openai_api_key: sk-...
openai_model: gpt-4o-mini

# Slack notification (optional) — webhook URL or a bot token + channel id
slack_webhook_url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
# slack_bot_token: xoxb-...
# slack_channel_id: C01234567890

# Video extensions to process
video_extensions:
  - .mov
  - .mp4
  - .avi
  - .mkv
  - .m4v

# Whisper ggml model name -> ggml-<name>.bin; auto-downloaded to ~/.whisper-models/ if missing
whisper_model: base

# Optional iCloud base URL for links in Slack messages
icloud_base_url: https://www.icloud.com/iclouddrive/
```

A documented template is in [`config.example.yaml`](config.example.yaml).

### Key settings

| Key | Default | Notes |
| --- | --- | --- |
| `llm_provider` | `claude` | `claude` (Anthropic) or `openai`. |
| `anthropic_api_key` | _(empty)_ | Required when `llm_provider` is `claude`. From <https://console.anthropic.com/>. |
| `anthropic_model` | `claude-haiku-4-5-20251001` | Anthropic model id. |
| `openai_api_key` | _(empty)_ | Required when `llm_provider` is `openai`. From <https://platform.openai.com/api-keys>. |
| `openai_model` | `gpt-4o-mini` | OpenAI model id. |
| `whisper_model` | `base` | `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` (and `.en` variants). Auto-downloaded if missing. |

If no key is set for the selected provider, summarization is skipped gracefully — you still
get the transcript.

## Usage

```bash
# Transcribe a single file
transcribe meeting.mov

# Also write a machine-readable JSON result next to the outputs
transcribe meeting.mov --json

# Watch a directory in the foreground (Ctrl+C to stop)
transcribe watch ~/Movies

# Install the background daemon (recommended) and start it
transcribe setup-daemon
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Show / locate configuration
transcribe config

# Version
transcribe --version
```

### Output

For a video named `meeting.mov`, processing produces:

```
destination_directory/meeting/
├── meeting.mov              # original video
├── meeting_transcript.txt   # full transcription
└── meeting_summary.txt      # LLM summary (if a provider key is set)
```

With `--json`, a `meeting_result.json` (title, description, transcript, summary, action
items, source path) is also written.

## Whisper models

`whisper_model` accepts `tiny`, `base` (default), `small`, `medium`, `large-v3`, or
`large-v3-turbo` (plus the English-only `.en` variants of the smaller models) — larger is
more accurate but slower. Note there is no bare `large`; use a versioned name such as
`large-v3`. The matching `ggml-<name>.bin` is downloaded automatically to
`~/.whisper-models/` on first use.

## Privacy

- Transcription runs **locally** via `whisper-cpp`; videos never leave your machine.
- Only the **text transcript** is sent to the LLM provider (Claude or OpenAI) for
  summarization, and only if a key is configured.

## Documentation

- [docs/install.md](docs/install.md) — full install, API keys, Slack, Google Drive,
  upgrade, uninstall, troubleshooting.
- [docs/daemon.md](docs/daemon.md) — daemon setup, log inspection, and testing.
- [docs/architecture.md](docs/architecture.md) — pipeline, data flow, modules, security.
- [docs/release.md](docs/release.md) — release and Homebrew-tap process.
- [CHANGELOG.md](CHANGELOG.md) — version history.

## License

MIT — see [LICENSE](LICENSE).
