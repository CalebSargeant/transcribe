# Background daemon

Run Transcribe as a macOS `launchd` agent so videos dropped into your watch directory are
processed automatically, with the service starting on login and restarting if it crashes.

> macOS only.

## Setup

```bash
# Generate the launchd plist (uses watch_directory from your config)
transcribe setup-daemon

# Start the daemon
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Confirm it is running
launchctl list | grep transcribe
# e.g. 12345   0   com.calebsargeant.transcribe
```

`setup-daemon` writes `~/Library/LaunchAgents/com.calebsargeant.transcribe.plist`. The agent
runs `transcribe watch <watch_directory>` with `RunAtLoad` and `KeepAlive` enabled, and sets
`PYTHONUNBUFFERED=1` so logs stream live.

Once loaded, any video dropped into the watch directory is transcribed, summarized, moved to
the destination, and announced in Slack automatically.

## Logs

```bash
# Standard output and error logs
tail -f ~/Library/Logs/transcribe.log
tail -f ~/Library/Logs/transcribe.error.log

# Both at once
tail -f ~/Library/Logs/transcribe.log ~/Library/Logs/transcribe.error.log
```

On startup you should see lines like:

```
Watching directory: /Users/you/Movies
Video extensions: .mov, .mp4, .avi, .mkv, .m4v
```

and, when a file appears:

```
Detected new file: test.mp4
Waiting for file to finish writing...
```

followed by transcription progress.

## Stop / restart

```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Restart
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Testing

Drop a small file into the watch directory and watch the logs:

```bash
# Watch the logs in one terminal
tail -f ~/Library/Logs/transcribe.log ~/Library/Logs/transcribe.error.log

# In another terminal, create a tiny test video
ffmpeg -f lavfi -i testsrc=duration=5:size=320x240:rate=30 \
       -f lavfi -i sine=frequency=1000:duration=5 \
       -pix_fmt yuv420p ~/Movies/test.mp4
```

In the destination folder you should then see:

- `test.mp4` — original video
- `test_transcript.txt` — transcription
- `test_summary.txt` — LLM summary (if a provider key is configured)
- a Slack notification (if configured)

## Troubleshooting

```bash
# Is it running?
launchctl list | grep transcribe
ps aux | grep "transcribe watch"

# Recent logs / errors
tail -n 50 ~/Library/Logs/transcribe.log
tail -n 50 ~/Library/Logs/transcribe.error.log

# Verify the plist exists and is valid
ls -la ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
plutil -lint ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist

# Run the watcher in the foreground for live debugging
transcribe watch ~/Movies
```

If the daemon does not pick up files, confirm the watched directory matches your config:

```bash
transcribe config | grep watch_directory
```
