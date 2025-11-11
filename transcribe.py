#!/usr/bin/env python3
"""
Transcribe video/audio files using Whisper CLI with auto-watch, summarization, and notifications.
Usage: 
  transcribe <video_file>           - Transcribe a single file
  transcribe watch <directory>      - Watch directory for new files
  transcribe setup-daemon           - Install background daemon
  transcribe config                 - Configure settings
Requires: brew install whisper-cpp ffmpeg
"""

import sys
import subprocess
import os
import tempfile
import time
import shutil
import json
from pathlib import Path
from datetime import datetime
import yaml

# Configuration
CONFIG_DIR = Path.home() / ".transcribe"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DEFAULT_CONFIG = {
    "watch_directory": str(Path.home() / "Movies"),
    "destination_directory": str(Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Movies"),
    "openai_api_key": "",
    "slack_webhook_url": "",
    "video_extensions": [".mov", ".mp4", ".avi", ".mkv", ".m4v"],
    "icloud_base_url": "https://www.icloud.com/iclouddrive/"  # Users can customize this
}

def load_config():
    """Load configuration from file or create default."""
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
        print(f"Created default config at {CONFIG_FILE}")
        print("Please edit it to add your OpenAI API key and Slack webhook URL.")
        return DEFAULT_CONFIG
    
    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)
    
    # Merge with defaults for any missing keys
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value
    
    return config

def save_config(config):
    """Save configuration to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

def summarize_with_openai(transcript, api_key):
    """Summarize transcript using OpenAI API."""
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes video transcripts. Include key topics, action items, and notable timestamps if mentioned in the transcript."},
                {"role": "user", "content": f"Please summarize this video transcript, including any action items and key timestamps:\n\n{transcript}"}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"Warning: Failed to summarize with OpenAI: {e}")
        return None

def send_slack_notification(video_name, video_path, transcript_path, summary_path, config):
    """Send notification to Slack with file links."""
    try:
        import requests
        
        webhook_url = config.get("slack_webhook_url")
        if not webhook_url:
            print("Warning: No Slack webhook URL configured")
            return
        
        # Create message
        dest_dir = Path(config["destination_directory"])
        icloud_base = config.get("icloud_base_url", "iCloud folder")
        
        message = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📹 Video Transcribed: {video_name}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Processed:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n*Location:* {dest_dir / video_name}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Files:*\n• Video: `{video_name}`\n• Transcript: `{Path(transcript_path).name}`\n• Summary: `{Path(summary_path).name if summary_path else 'N/A'}`"
                    }
                }
            ]
        }
        
        # Add summary if available
        if summary_path and Path(summary_path).exists():
            with open(summary_path, "r") as f:
                summary = f.read()
            if len(summary) > 500:
                summary = summary[:500] + "..."
            message["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary:*\n{summary}"
                }
            })
        
        response = requests.post(webhook_url, json=message)
        response.raise_for_status()
        print("✓ Slack notification sent")
        
    except Exception as e:
        print(f"Warning: Failed to send Slack notification: {e}")

def move_files_to_destination(video_path, transcript_path, summary_path, config):
    """Move all files to the destination directory."""
    dest_dir = Path(config["destination_directory"])
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    moved_files = {}
    
    # Move video
    video_dest = dest_dir / Path(video_path).name
    shutil.move(video_path, video_dest)
    moved_files["video"] = str(video_dest)
    print(f"✓ Moved video to {video_dest}")
    
    # Move transcript
    if Path(transcript_path).exists():
        transcript_dest = dest_dir / Path(transcript_path).name
        shutil.move(transcript_path, transcript_dest)
        moved_files["transcript"] = str(transcript_dest)
        print(f"✓ Moved transcript to {transcript_dest}")
    
    # Move summary if it exists
    if summary_path and Path(summary_path).exists():
        summary_dest = dest_dir / Path(summary_path).name
        shutil.move(summary_path, summary_dest)
        moved_files["summary"] = str(summary_dest)
        print(f"✓ Moved summary to {summary_dest}")
    
    return moved_files

def transcribe_video(video_path):
    """Transcribe a video file and return the text."""
    print(f"Extracting audio from {video_path}...")
    
    # Extract audio to WAV for faster processing
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        audio_path = temp_audio.name
    
    try:
        # Extract audio using ffmpeg
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", audio_path, "-y"],
            check=True,
            capture_output=True
        )
        
        print(f"Transcribing audio (this may take a while for long files)...")
        
        # Find model relative to script location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(script_dir, "models", "ggml-base.bin")
        
        # Fall back to home directory if not found
        if not os.path.exists(model_path):
            model_path = os.path.expanduser("~/.whisper-models/ggml-base.bin")
        
        # Use whisper-cli with progress
        result = subprocess.run(
            ["whisper-cli", "-m", model_path, "-f", audio_path, "-nt", "-pp"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse output - whisper-cli prints transcription to stdout
        lines = result.stdout.strip().split("\n")
        # Filter out debug/info lines and keep only transcription
        text_lines = [line for line in lines if not line.startswith(("whisper_", "ggml_", "["))]
        
        return " ".join(text_lines).strip()
        
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: Required tool not found. Install with: brew install whisper-cpp ffmpeg")
        sys.exit(1)
    finally:
        # Clean up temporary audio file
        if os.path.exists(audio_path):
            os.unlink(audio_path)

def process_video_file(video_file, config=None):
    """Process a video file: transcribe, summarize, move, and notify."""
    if config is None:
        config = load_config()
    
    print(f"\n{'='*60}")
    print(f"Processing: {Path(video_file).name}")
    print(f"{'='*60}\n")
    
    try:
        # Transcribe
        transcript = transcribe_video(video_file)
        print("\n--- Transcription Complete ---")
        
        # Save transcript
        transcript_file = video_file.rsplit(".", 1)[0] + "_transcript.txt"
        with open(transcript_file, "w") as f:
            f.write(transcript)
        print(f"✓ Transcript saved to: {transcript_file}")
        
        # Summarize with OpenAI
        summary_file = None
        if config.get("openai_api_key"):
            print("\n--- Generating Summary with OpenAI ---")
            summary = summarize_with_openai(transcript, config["openai_api_key"])
            if summary:
                summary_file = video_file.rsplit(".", 1)[0] + "_summary.txt"
                with open(summary_file, "w") as f:
                    f.write(summary)
                print(f"✓ Summary saved to: {summary_file}")
                print(f"\n{summary}")
        
        # Move files to destination
        if config.get("destination_directory"):
            print("\n--- Moving Files ---")
            moved_files = move_files_to_destination(video_file, transcript_file, summary_file, config)
            
            # Send Slack notification
            if config.get("slack_webhook_url"):
                print("\n--- Sending Notification ---")
                send_slack_notification(
                    Path(video_file).name,
                    moved_files.get("video"),
                    moved_files.get("transcript"),
                    moved_files.get("summary"),
                    config
                )
        
        print(f"\n{'='*60}")
        print("✓ Processing complete!")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\nError processing {video_file}: {e}")
        import traceback
        traceback.print_exc()

def watch_directory(directory, config):
    """Watch a directory for new video files and process them."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("Error: watchdog library not installed. Install with: pip install watchdog")
        sys.exit(1)
    
    class VideoHandler(FileSystemEventHandler):
        def __init__(self, config):
            self.config = config
            self.processing = set()
        
        def on_created(self, event):
            if event.is_directory:
                return
            
            file_path = event.src_path
            file_ext = Path(file_path).suffix.lower()
            
            # Check if it's a video file
            if file_ext in config.get("video_extensions", [".mov", ".mp4"]):
                # Avoid processing the same file multiple times
                if file_path in self.processing:
                    return
                
                self.processing.add(file_path)
                
                # Wait a bit to ensure file is fully written
                print(f"Detected new file: {Path(file_path).name}")
                print("Waiting for file to finish writing...")
                time.sleep(2)
                
                # Check if file still exists and is accessible
                if Path(file_path).exists():
                    process_video_file(file_path, self.config)
                
                self.processing.discard(file_path)
    
    print(f"Watching directory: {directory}")
    print(f"Video extensions: {', '.join(config.get('video_extensions', []))}")
    print("Press Ctrl+C to stop...\n")
    
    event_handler = VideoHandler(config)
    observer = Observer()
    observer.schedule(event_handler, directory, recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watch...")
        observer.stop()
    observer.join()

def setup_daemon(config):
    """Setup macOS launchd daemon for automatic watching."""
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.calebsargeant.transcribe</string>
    <key>ProgramArguments</key>
    <array>
        <string>{shutil.which('transcribe')}</string>
        <string>watch</string>
        <string>{config['watch_directory']}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/Library/Logs/transcribe.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/Library/Logs/transcribe.error.log</string>
</dict>
</plist>"""
    
    plist_path = Path.home() / "Library/LaunchAgents/com.calebsargeant.transcribe.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(plist_path, "w") as f:
        f.write(plist_content)
    
    print(f"✓ Created launchd plist at {plist_path}")
    print("\nTo start the daemon:")
    print(f"  launchctl load {plist_path}")
    print("\nTo stop the daemon:")
    print(f"  launchctl unload {plist_path}")
    print("\nLogs will be written to:")
    print(f"  {Path.home()}/Library/Logs/transcribe.log")

def configure():
    """Interactive configuration."""
    config = load_config()
    
    print("\nTranscribe Configuration\n" + "="*40)
    print("\nCurrent configuration:")
    for key, value in config.items():
        if "api_key" in key or "webhook" in key:
            display_value = "***" if value else "(not set)"
        else:
            display_value = value
        print(f"  {key}: {display_value}")
    
    print("\nEdit the configuration file at:")
    print(f"  {CONFIG_FILE}")
    print("\nRequired for full functionality:")
    print("  - openai_api_key: For transcript summarization")
    print("  - slack_webhook_url: For notifications")

def main():
    """Main entry point for the transcribe command."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  transcribe <video_file>           - Transcribe a single file")
        print("  transcribe watch [directory]      - Watch directory for new files")
        print("  transcribe setup-daemon           - Install background daemon")
        print("  transcribe config                 - Show/edit configuration")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "config":
        configure()
    elif command == "setup-daemon":
        config = load_config()
        setup_daemon(config)
    elif command == "watch":
        config = load_config()
        directory = sys.argv[2] if len(sys.argv) > 2 else config["watch_directory"]
        watch_directory(directory, config)
    else:
        # Assume it's a video file
        video_file = command
        if not Path(video_file).exists():
            print(f"Error: File not found: {video_file}")
            sys.exit(1)
        
        config = load_config()
        process_video_file(video_file, config)


if __name__ == "__main__":
    main()
