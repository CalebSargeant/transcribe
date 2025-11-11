# Transcribe

Automated video/audio transcription tool with OpenAI summarization and Slack notifications.

## Features

- 🎤 **Local Transcription**: Uses `whisper-cpp` for fast, privacy-focused transcription
- 👁️ **Auto-Watch**: Monitors directories for new video files and processes them automatically
- 🤖 **AI Summarization**: Generates summaries with timestamps and action items using OpenAI
- 📁 **iCloud Integration**: Automatically moves processed files to iCloud for storage
- 💬 **Slack Notifications**: Sends formatted notifications with file links when processing completes
- 🎬 **Multi-Format**: Supports all video formats supported by ffmpeg (MOV, MP4, AVI, MKV, etc.)

## Installation

### Via Homebrew (recommended)

```bash
brew install calebsargeant/tap/transcribe
```

### Manual Installation

```bash
# Install system dependencies
brew install whisper-cpp ffmpeg

# Clone and install
git clone https://github.com/calebsargeant/transcribe.git
cd transcribe
pip install -e .

# Download Whisper model
mkdir -p models
curl -L -o models/ggml-base.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
```

## Quick Start

### 1. Configure

First time setup - configure your settings:

```bash
transcribe config
```

This creates `~/.transcribe/config.yaml`. Edit it to add:
- `openai_api_key`: Your OpenAI API key (for summarization)
- `slack_webhook_url`: Your Slack webhook URL (for notifications)
- `destination_directory`: Where to move processed files (default: iCloud/Movies)
- `watch_directory`: Directory to monitor (default: ~/Movies)

### 2. Transcribe a Single File

```bash
transcribe video.mov
```

This will:
1. Extract audio from the video
2. Transcribe using Whisper (local)
3. Summarize with OpenAI (if configured)
4. Move files to iCloud (if configured)
5. Send Slack notification (if configured)

### 3. Watch a Directory

Monitor a directory for new videos:

```bash
transcribe watch ~/Movies
```

Any new video files will be automatically processed.

### 4. Setup Background Daemon (Recommended)

For fully automated transcription on login:

```bash
transcribe setup-daemon
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

Now any video dropped into ~/Movies will be automatically:
1. Transcribed
2. Summarized
3. Moved to iCloud
4. Announced in Slack

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

### Check daemon status
```bash
launchctl list | grep transcribe
```

### View logs
```bash
tail -f ~/Library/Logs/transcribe.log
```

### Restart daemon
```bash
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Privacy

- Video transcription happens **locally** using whisper-cpp
- Only the text transcript is sent to OpenAI for summarization (if enabled)
- Original videos never leave your machine (except when moved to iCloud)

## License

MIT
