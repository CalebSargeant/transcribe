# Quick Setup Guide

Get started with automated video transcription in 5 minutes.

## Step 1: Install

```bash
brew install calebsargeant/tap/transcribe
```

## Step 2: Configure

Run the config command to create your configuration file:

```bash
transcribe config
```

This creates `~/.transcribe/config.yaml`. Open it in your editor:

```bash
nano ~/.transcribe/config.yaml
# or
code ~/.transcribe/config.yaml
```

### Required Configuration

Add your API keys:

```yaml
openai_api_key: sk-your-openai-api-key-here
slack_webhook_url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**Get OpenAI API Key:**
- Go to https://platform.openai.com/api-keys
- Click "Create new secret key"
- Copy the key and paste into config

**Get Slack Webhook:**
- Go to https://api.slack.com/messaging/webhooks
- Click "Create New App" → "From scratch"
- Enable "Incoming Webhooks"
- Click "Add New Webhook to Workspace"
- Select your channel and authorize
- Copy the webhook URL and paste into config

### Optional Configuration

Customize directories if needed:

```yaml
watch_directory: /Users/yourusername/Movies
destination_directory: /Users/yourusername/Library/Mobile Documents/com~apple~CloudDocs/Movies
```

## Step 3: Test

Test with a single video file:

```bash
transcribe ~/Movies/test-video.mov
```

You should see:
1. ✓ Transcription complete
2. ✓ Summary generated
3. ✓ Files moved to iCloud
4. ✓ Slack notification sent

## Step 4: Setup Automated Watching

Install the background daemon:

```bash
transcribe setup-daemon
```

Start the daemon:

```bash
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Step 5: Verify

Check that the daemon is running:

```bash
launchctl list | grep transcribe
```

You should see output like:
```
12345   0   com.calebsargeant.transcribe
```

## Done! 🎉

Now whenever you drop a video into `~/Movies`, it will automatically:
1. Transcribe using local Whisper
2. Summarize with OpenAI
3. Move to iCloud
4. Notify you in Slack

## Troubleshooting

### Check logs
```bash
tail -f ~/Library/Logs/transcribe.log
```

### Restart daemon
```bash
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

### Stop daemon
```bash
launchctl unload ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist
```

## Manual Watch Mode

If you prefer not to use the daemon, you can watch manually:

```bash
transcribe watch ~/Movies
```

Press Ctrl+C to stop.

## Privacy Note

- Transcription happens **locally** on your Mac
- Only the text transcript is sent to OpenAI
- Videos never leave your machine (except to iCloud if configured)
