# Architecture

How Transcribe processes a video, how data flows, and how the package is structured.

> macOS only.

## Pipeline overview

```
User saves video to ~/Movies
        │
        ▼
launchd daemon (or `transcribe watch`) detects the new file
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Local transcription                                      │
│    video ──ffmpeg──► temp.wav ──whisper-cpp──► transcript   │
│    Privacy: fully local, nothing uploaded                   │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. LLM summarization (if a provider key is set)             │
│    transcript ──Claude (default) / OpenAI──►                │
│        summary + title/description + action items           │
│    Cloud: only the text transcript is sent                  │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. File management                                          │
│    Move video + transcript + summary into                   │
│    destination_directory/<video-name>/                      │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Notification (if Slack configured)                       │
│    Title, description, action items, folder link → Slack    │
└─────────────────────────────────────────────────────────────┘
```

With `--json` (single-file mode), step 2's outputs plus the transcript and source path are
also written to `<video>_result.json`.

## Data flow

```
User action (save video.mov)
        │
        ▼
watchdog FileSystemEventHandler ──reads──► ~/.transcribe/config.yaml
        │
        ▼
transcribe_video()  ── ffmpeg + whisper-cpp (local) ──► transcript.txt
        │
        ▼
llm._complete()  ── Anthropic (default) or OpenAI ──► summary / title / actions
        │
        ▼
move_files_to_destination()  ──► destination_directory/<name>/
        │
        ▼
send_slack_notification()  ── webhook or bot token ──► Slack channel
        │
        └── (gdrive) optional Google Drive folder link
```

## LLM provider selection

Summarization, title/description, and action-item extraction are provider-agnostic. The
`_complete()` dispatcher in `llm.py` reads `llm_provider` from config:

- `claude` (default) → Anthropic Messages API (`anthropic` SDK), model
  `anthropic_model` (default `claude-haiku-4-5-20251001`).
- `openai` → OpenAI Chat Completions API (`openai` SDK), model `openai_model`
  (default `gpt-4o-mini`).

If no key is configured for the selected provider, the LLM steps return `None`/`[]` and are
skipped gracefully — the transcript is still produced.

## Whisper model resolution

`whisper._ensure_model()` resolves the ggml model in this order:

1. A model bundled next to the package (or inside the PyInstaller bundle under `_MEIPASS`).
2. `~/.whisper-models/ggml-<whisper_model>.bin` — **downloaded on demand** from Hugging Face
   if missing, with a progress indicator, written atomically via a `.part` temp file.

## Execution modes

```
One-off:   transcribe video.mov [--json]
             └─► process_video_file()

Watch:     transcribe watch ~/Movies
             └─► watchdog Observer ─► VideoHandler.on_created ─► process_video_file()

Daemon:    launchd ─► transcribe watch <watch_directory> (on login)
             └─► (same Observer loop, KeepAlive + RunAtLoad)
```

## Error handling

- Local transcription fails → log error, stop processing that file.
- LLM call fails or no key → warn, continue without that artifact.
- File move fails → log error; files stay in the watch directory.
- Slack notification fails → warn; files are already processed.

All daemon output goes to `~/Library/Logs/transcribe.log` and `transcribe.error.log`.

## Package layout

```
src/transcribe/
├── __init__.py      # package metadata / __version__
├── __main__.py      # `python -m transcribe`
├── cli.py           # argument parsing, command dispatch, --json / --version
├── config.py        # load/save ~/.transcribe/config.yaml + DEFAULT_CONFIG
├── whisper.py       # ffmpeg audio extraction, whisper-cli, model auto-download
├── llm.py           # provider dispatch (Claude default / OpenAI), prompts
├── processing.py    # end-to-end pipeline + file moves + JSON output
├── watch.py         # watchdog directory watcher
├── daemon.py        # launchd plist generation (setup-daemon)
├── slack.py         # Slack webhook / bot-token notifications
├── gdrive.py        # optional Google Drive folder URL resolution
└── tls.py           # TLS CA bundle fixup for frozen binaries
```

Other paths:

```
~/.transcribe/config.yaml                              # user configuration
~/.whisper-models/ggml-<model>.bin                     # auto-downloaded models
~/Library/LaunchAgents/com.calebsargeant.transcribe.plist  # daemon definition
~/Library/Logs/transcribe.log, transcribe.error.log    # daemon logs
```

## Dependencies

Runtime (Python, from `pyproject.toml`):

- `pyyaml` — config parsing
- `watchdog` — directory monitoring
- `anthropic` — Claude summarization (default provider)
- `openai` — OpenAI summarization (alternative provider)
- `requests` — Slack notifications

Optional extra `gdrive`:

- `google-auth`, `google-api-python-client` — Google Drive folder links

System (Homebrew):

- `whisper-cpp` — local transcription
- `ffmpeg` — audio extraction

## Security considerations

1. **API keys** live in plaintext in `~/.transcribe/config.yaml` (standard for CLI tools).
   Consider `chmod 600 ~/.transcribe/config.yaml`. Do not commit it.
2. **Slack webhook / bot token** are secrets — keep them out of version control.
3. **Video privacy** — videos are processed locally; only the text transcript is sent to
   the LLM provider, and only when a key is configured.
4. **Network calls** — Anthropic/OpenAI and Slack are all over HTTPS/TLS.
