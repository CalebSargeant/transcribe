# Transcribe

Automated video/audio transcription tool with OpenAI summarization and Slack notifications.

📚 **[Full Installation & Configuration Guide](INSTALL.md)** | 🐛 [Issues](https://github.com/CalebSargeant/transcribe/issues) | 📦 [Releases](https://github.com/CalebSargeant/transcribe/releases)

## Features

- 🎤 **Local Transcription**: Uses `whisper-cpp` for fast, privacy-focused transcription
- 👁️ **Auto-Watch**: Monitors directories for new video files and processes them automatically
- 🤖 **AI Summarization**: Generates summaries with timestamps and action items using OpenAI
- 📁 **Smart Organization**: Automatically moves processed files to configured destination
- 💬 **Slack Notifications**: Sends formatted notifications with file links when processing completes
- 🎬 **Multi-Format**: Supports all video formats supported by ffmpeg (MOV, MP4, AVI, MKV, etc.)

## Quick Start

### Installation

```bash
# Add the tap and install
brew tap CalebSargeant/tap
brew install transcribe

# Download Whisper model (~140MB)
mkdir -p ~/.whisper-models
curl -L -o ~/.whisper-models/ggml-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

# Configure
transcribe config  # Opens ~/.transcribe/config.yaml
```

**📚 For detailed installation instructions, see [INSTALL.md](INSTALL.md)**

### Basic Usage

**Transcribe a single file:**

```bash
transcribe video.mov
```

**Watch a directory:**

```bash
transcribe watch ~/Movies  # Press Ctrl+C to stop
```

**Setup as background daemon (recommended):**

```bash
transcribe setup-daemon
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# View logs
tail -f ~/Library/Logs/transcribe.log
```

Now any video dropped into your watch directory will be automatically processed!

## Configuration

Configuration file: `~/.transcribe/config.yaml`

```yaml
watch_directory: /Users/you/Movies
destination_directory: /Users/you/Library/Mobile Documents/com~apple~CloudDocs/Movies
openai_api_key: sk-...
slack_webhook_url: https://hooks.slack.com/services/...
video_extensions:
  - .mov
  - .mp4
  - .avi
  - .mkv
  - .m4v
icloud_base_url: https://www.icloud.com/iclouddrive/
```

### Getting API Keys

**OpenAI API Key:**
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Add to config file

**Slack Webhook:**
1. Go to https://api.slack.com/messaging/webhooks
2. Create an incoming webhook
3. Choose the channel for notifications
4. Add webhook URL to config file

## Usage Examples

```bash
# Transcribe a single file
transcribe meeting.mov

# Watch a directory manually
transcribe watch ~/Desktop/Videos

# Setup background daemon
transcribe setup-daemon

# View current configuration
transcribe config

# Stop the daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Output Files

For each video file, three files are created:

1. **`video.mov`** - Original video
2. **`video_transcript.txt`** - Full transcription
3. **`video_summary.txt`** - AI-generated summary with timestamps and action items

All files are moved to your configured destination directory (e.g., iCloud).

## Whisper Model Options

By default, the `base` model is used. You can download other models:

- `tiny` - Fastest, least accurate
- `base` - Balanced (default)
- `small` - Better accuracy
- `medium` - Very good accuracy
- `large` - Best accuracy, slowest

## Requirements

- macOS
- Python 3.9+
- ffmpeg
- whisper-cpp
- OpenAI API key (optional, for summarization)
- Slack webhook (optional, for notifications)

## Troubleshooting

**See the [Full Installation Guide](INSTALL.md#troubleshooting)** for detailed troubleshooting steps.

Quick checks:

```bash
# Check daemon status
launchctl list | grep transcribe

# View logs
tail -f ~/Library/Logs/transcribe.log

# Verify model exists
ls -lh ~/.whisper-models/ggml-base.bin

# Restart daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Privacy

- Video transcription happens **locally** using whisper-cpp
- Only the text transcript is sent to OpenAI for summarization (if enabled)
- Original videos never leave your machine (except when moved to iCloud)

## License

MIT
