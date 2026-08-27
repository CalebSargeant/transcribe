"""macOS launchd agent setup."""

import shutil
from pathlib import Path

AUTORECORD_LABEL = "com.calebsargeant.transcribe.autorecord"


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


def setup_autorecord_daemon(config):
    """Install a launchd agent that records meetings automatically."""
    executable = shutil.which("transcribe") or "transcribe"
    plist_path = Path.home() / f"Library/LaunchAgents/{AUTORECORD_LABEL}.plist"
    logs = Path.home() / "Library/Logs"

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{AUTORECORD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{executable}</string>
        <string>autorecord</string>
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
    <string>{logs}/transcribe-autorecord.log</string>
    <key>StandardErrorPath</key>
    <string>{logs}/transcribe-autorecord.error.log</string>
</dict>
</plist>"""
    )

    print(f"✓ Created launchd plist at {plist_path}")
    print("\nBefore starting, enable the OBS WebSocket server:")
    print("  OBS > Tools > WebSocket Server Settings > Enable, then copy the password into")
    print("  ~/.transcribe/config.yaml as obs_password")
    print("\nTo start:")
    print(f"  launchctl load {plist_path}")
    print("\nTo stop:")
    print(f"  launchctl unload {plist_path}")
    print("\nLogs:")
    print(f"  {logs}/transcribe-autorecord.log")
