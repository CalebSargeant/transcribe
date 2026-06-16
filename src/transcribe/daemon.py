"""macOS launchd daemon setup."""

import shutil
from pathlib import Path


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
        <string>{shutil.which("transcribe")}</string>
        <string>watch</string>
        <string>{config["watch_directory"]}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
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
