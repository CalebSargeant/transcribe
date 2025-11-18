# Testing Daemon Logging

## Wait for Release
GitHub Actions should create v1.0.6 with the new binaries in a few minutes.
Check: https://github.com/CalebSargeant/transcribe/releases

## Clean Up Existing Daemon

```bash
# Stop and remove old daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
pkill -f "transcribe watch"

# Remove old plist (we'll regenerate it)
rm ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Install New Version

```bash
# If you installed via Homebrew (update tap first)
cd ~/repos/calebsargeant/homebrew-tap
# Update Formula/transcribe.rb to v1.0.6 with new SHA256 checksums
brew upgrade transcribe

# OR install directly from release
cd /tmp
curl -L -o transcribe https://github.com/CalebSargeant/transcribe/releases/download/v1.0.6/transcribe-macos-arm64
chmod +x transcribe
sudo mv transcribe /usr/local/bin/
```

## Setup New Daemon

```bash
# Regenerate plist with PYTHONUNBUFFERED
transcribe setup-daemon

# Verify the plist has EnvironmentVariables
cat ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist | grep -A 3 EnvironmentVariables

# Load the daemon
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Verify it's running
launchctl list | grep transcribe
```

## Test Logging

```bash
# Watch logs in real-time
tail -f ~/Library/Logs/transcribe.log ~/Library/Logs/transcribe.error.log

# In another terminal, trigger a test
# Option 1: Copy a small video file
cp ~/path/to/small-video.mp4 ~/Movies/test.mp4

# Option 2: Create a tiny test video (if you have ffmpeg)
ffmpeg -f lavfi -i testsrc=duration=2:size=320x240:rate=30 \
       -f lavfi -i sine=frequency=1000:duration=2 \
       -pix_fmt yuv420p ~/Movies/test.mp4

# You should see in the logs:
# - "Watching directory: /Users/caleb/Movies"
# - "Video extensions: .mov, .mp4, .avi, .mkv, .m4v"
# - "Detected new file: test.mp4"
# - "Waiting for file to finish writing..."
# - Transcription progress
```

## Expected Behavior

When working correctly, you should see:
1. Startup messages immediately in `transcribe.log`
2. File detection messages when new videos are added
3. Processing logs during transcription
4. Any errors in `transcribe.error.log`

## Troubleshooting

```bash
# Check daemon status
launchctl list | grep transcribe

# View recent logs
tail -n 50 ~/Library/Logs/transcribe.log

# Stop daemon
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Start daemon manually for debugging
transcribe watch ~/Movies
```
