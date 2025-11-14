# Transcribe Quick Start Guide

Get up and running with transcribe in 5 minutes!

## Step 1: Install (2 minutes)

```bash
# Add the Homebrew tap
brew tap CalebSargeant/tap

# Install transcribe (includes dependencies: whisper-cpp, ffmpeg)
brew install transcribe

# Download the Whisper model (~140MB, one-time download)
mkdir -p ~/.whisper-models
curl -L -o ~/.whisper-models/ggml-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
```

## Step 2: Configure (1 minute)

```bash
# Create config file
transcribe config

# Edit the config file (optional but recommended)
open ~/.transcribe/config.yaml
```

**Minimal configuration** (everything else is optional):
```yaml
watch_directory: /Users/yourname/Movies
destination_directory: /Users/yourname/Documents/Transcriptions
```

**Add OpenAI key for summaries** (recommended):
```yaml
openai_api_key: sk-your-key-here  # Get from https://platform.openai.com/api-keys
```

**Add Slack for notifications** (optional):
```yaml
slack_webhook_url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## Step 3: Test (1 minute)

Try transcribing a single file:

```bash
transcribe /path/to/your/video.mov
```

You'll see:
- Audio extraction progress
- Transcription in progress
- Files saved to your destination directory

## Step 4: Go Automatic (1 minute)

Set up the background daemon to process videos automatically:

```bash
# Setup daemon
transcribe setup-daemon

# Start it
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Watch it work
tail -f ~/Library/Logs/transcribe.log
```

Now drop a video into `~/Movies` and watch it process automatically!

## What You Get

After processing a video named `meeting.mov`, you'll find:

```
your_destination_directory/
└── meeting/
    ├── meeting.mov              # Original video
    ├── meeting_transcript.txt   # Full transcription
    └── meeting_summary.txt      # AI summary (if OpenAI configured)
```

Plus a Slack notification if configured!

## Common Commands

```bash
# Process one file
transcribe video.mov

# Watch a folder (foreground)
transcribe watch ~/Desktop/Recordings

# View configuration
transcribe config

# Check daemon status
launchctl list | grep transcribe

# View logs
tail -f ~/Library/Logs/transcribe.log

# Stop daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Restart daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Troubleshooting

**"Model not found" error?**
```bash
# Check if model exists
ls -lh ~/.whisper-models/ggml-base.bin

# If not, download it
curl -L -o ~/.whisper-models/ggml-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
```

**Daemon not processing files?**
```bash
# Check if running
ps aux | grep "transcribe watch"

# Check logs for errors
tail -50 ~/Library/Logs/transcribe.error.log

# Restart daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

**Need more help?**
- See the [Full Installation Guide](INSTALL.md) for detailed instructions
- Check [Issues](https://github.com/CalebSargeant/transcribe/issues) for known problems
- Open a new issue if you're stuck

## Next Steps

- **[Full Installation Guide](INSTALL.md)** - Detailed setup instructions
- **[Configuration Options](INSTALL.md#configuration)** - All config settings explained
- **[Slack Setup](INSTALL.md#6-setup-slack-notifications-optional)** - Get notifications
- **[Google Drive Links](INSTALL.md#7-setup-google-drive-links-optional)** - Link to Drive files

---

**That's it!** You're now automatically transcribing videos. Drop a video in your watch folder and see the magic happen! ✨
