# Transcribe Installation & Configuration Guide

## Overview

Transcribe is an automated video/audio transcription tool that:
- Watches a directory for new video files
- Transcribes audio using Whisper
- Summarizes content with OpenAI
- Sends notifications to Slack
- Moves processed files to a destination folder

## Prerequisites

- macOS (tested on macOS 14+)
- Homebrew package manager
- OpenAI API key (optional, for summaries)
- Slack webhook URL or Bot token (optional, for notifications)
- Google Cloud credentials (optional, for Drive links in Slack)

## Installation

### 1. Install Transcribe via Homebrew

```bash
# Tap the repository
brew tap CalebSargeant/tap

# Install transcribe and dependencies
brew install transcribe

# Dependencies (whisper-cpp and ffmpeg) are installed automatically
```

### 2. Download Whisper Model

The transcribe tool requires a Whisper model file (~140MB):

```bash
mkdir -p ~/.whisper-models
curl -L -o ~/.whisper-models/ggml-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
```

**Model options:**
- `ggml-tiny.bin` - 75MB, fastest, lowest quality
- `ggml-base.bin` - 142MB, good balance (recommended)
- `ggml-small.bin` - 466MB, better quality, slower
- `ggml-medium.bin` - 1.5GB, high quality, much slower

## Configuration

### 3. Initial Setup

Run the configuration command to create the config file:

```bash
transcribe config
```

This creates `~/.transcribe/config.yaml` with default settings.

### 4. Edit Configuration

Open and edit the config file:

```bash
open ~/.transcribe/config.yaml
# or
vim ~/.transcribe/config.yaml
```

**Example configuration:**

```yaml
# Where to watch for new video files
watch_directory: /Users/yourname/Movies

# Where to move processed files (creates a folder per video)
destination_directory: /Users/yourname/Google Drive/My Drive/Meetings

# OpenAI API key for summarization (optional)
openai_api_key: sk-your-key-here

# Slack notification settings (choose ONE method)

# Method 1: Webhook URL (simpler)
slack_webhook_url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Method 2: Bot Token (more features)
slack_bot_token: xoxb-your-bot-token
slack_channel_id: C01234567890

# Video file extensions to watch
video_extensions:
  - .mov
  - .mp4
  - .avi
  - .mkv
  - .m4v

# iCloud base URL (customize if needed)
icloud_base_url: https://www.icloud.com/iclouddrive/
```

### 5. Get OpenAI API Key (Optional)

1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy and paste into `openai_api_key` in config
4. Add billing method at https://platform.openai.com/account/billing

**Cost:** Approximately $0.01-0.05 per video for summarization (using gpt-4o-mini)

### 6. Setup Slack Notifications (Optional)

#### Method A: Webhook URL (Simpler)

1. Go to https://api.slack.com/apps
2. Create New App → From scratch
3. App Name: "Transcribe" → Select workspace
4. Features → Incoming Webhooks → Activate
5. Add New Webhook to Workspace → Select channel
6. Copy the webhook URL
7. Paste into `slack_webhook_url` in config

#### Method B: Bot Token (More Features)

1. Go to https://api.slack.com/apps
2. Create New App → From scratch
3. App Name: "Transcribe" → Select workspace
4. OAuth & Permissions → Bot Token Scopes → Add:
   - `chat:write`
   - `chat:write.public`
5. Install to Workspace
6. Copy the "Bot User OAuth Token" (starts with `xoxb-`)
7. Get your channel ID:
   - Open Slack in browser
   - Navigate to the channel
   - Copy the ID from the URL (e.g., `C01234567890`)
8. Paste token into `slack_bot_token` and ID into `slack_channel_id`

### 7. Setup Google Drive Links (Optional)

If you want Slack notifications to include Google Drive links instead of file:// links:

```bash
# Install Google Cloud SDK if not already installed
brew install google-cloud-sdk

# Authenticate with Google
gcloud auth application-default login

# Follow the browser prompts to authenticate
```

**Note:** If you skip this step, notifications will use `file://` links which work fine for local access.

**Re-authentication:** Required approximately every 6 months if inactive, or when the refresh token expires.

## Running Transcribe

### One-Time Transcription

Transcribe a single file:

```bash
transcribe /path/to/video.mov
```

The tool will:
1. Extract audio
2. Transcribe
3. Generate summary (if OpenAI key configured)
4. Move files to destination directory
5. Send Slack notification (if configured)

### Watch Mode (Manual)

Watch a directory manually (runs in foreground):

```bash
transcribe watch ~/Movies
```

Press Ctrl+C to stop.

### Daemon Mode (Automatic)

Setup as a background daemon that starts automatically:

```bash
# Setup daemon
transcribe setup-daemon

# Start the daemon
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Check if running
launchctl list | grep transcribe

# View logs
tail -f ~/Library/Logs/transcribe.log
tail -f ~/Library/Logs/transcribe.error.log

# Stop daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

The daemon will:
- Start automatically when you log in
- Restart if it crashes
- Watch your configured directory continuously
- Process new videos as soon as they appear

## Testing

Test the daemon with a small video file:

```bash
# Create a test video (5 seconds)
ffmpeg -f lavfi -i testsrc=duration=5:size=320x240:rate=30 \
       -f lavfi -i sine=frequency=1000:duration=5 \
       -pix_fmt yuv420p ~/Movies/test.mp4

# Watch the logs
tail -f ~/Library/Logs/transcribe.log

# Check the destination folder
ls -la "/path/to/your/destination/test/"
```

You should see:
- `test.mp4` - original video
- `test_transcript.txt` - transcription
- `test_summary.txt` - AI summary (if OpenAI configured)
- Slack notification (if configured)

## Troubleshooting

### Video not being processed

Check the daemon is running:
```bash
launchctl list | grep transcribe
ps aux | grep "transcribe watch"
```

Check logs for errors:
```bash
tail -50 ~/Library/Logs/transcribe.error.log
```

Verify watched directory matches config:
```bash
transcribe config | grep watch_directory
```

### "Model not found" error

Download the Whisper model:
```bash
ls -lh ~/.whisper-models/ggml-base.bin
# If not found, download it (see step 2 above)
```

### "Required tool not found" error

This shouldn't happen with Homebrew installation, but if it does:
```bash
brew install whisper-cpp ffmpeg
which ffmpeg whisper-cli
```

### Google Drive link not working

Re-authenticate:
```bash
gcloud auth application-default login
```

Or just use file:// links - they work fine for local access.

### Daemon not starting automatically

Verify plist file exists:
```bash
ls -la ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

Check plist syntax:
```bash
plutil -lint ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

Reload daemon:
```bash
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Upgrading

To upgrade to the latest version:

```bash
# Update tap
brew update

# Upgrade transcribe
brew upgrade transcribe

# Restart daemon if running
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Uninstalling

```bash
# Stop daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Remove daemon plist
rm ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Uninstall transcribe
brew uninstall transcribe

# Optional: Remove config and models
rm -rf ~/.transcribe
rm -rf ~/.whisper-models
```

## File Structure

After processing a video named `meeting.mov`, you'll have:

```
destination_directory/
└── meeting/
    ├── meeting.mov           # Original video
    ├── meeting_transcript.txt  # Full transcription
    └── meeting_summary.txt     # AI summary (if OpenAI configured)
```

## Tips

1. **Start small**: Test with a short video first before processing long recordings
2. **Check costs**: Monitor your OpenAI API usage at https://platform.openai.com/usage
3. **Backup originals**: The tool moves (not copies) files from watch directory
4. **Use specific folders**: Don't watch your entire home directory - use a specific folder like ~/Movies
5. **Model size**: Use `ggml-base.bin` for most cases - only upgrade if quality isn't good enough
6. **Processing time**: Transcription takes roughly 1/4 of the video length on Apple Silicon Macs

## Support

- Issues: https://github.com/CalebSargeant/transcribe/issues
- Discussions: https://github.com/CalebSargeant/transcribe/discussions
- Releases: https://github.com/CalebSargeant/transcribe/releases

## License

MIT License - see LICENSE file in the repository.
