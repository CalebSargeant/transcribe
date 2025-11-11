#!/bin/bash
# Test script for transcribe v2.0.0

set -e

echo "================================"
echo "Testing transcribe v2.0.0"
echo "================================"
echo ""

# Check if transcribe is installed
echo "1. Checking installation..."
if ! command -v transcribe &> /dev/null; then
    echo "❌ transcribe not found. Install with:"
    echo "   cd ~/Nextcloud/repos/calebsargeant/transcribe"
    echo "   pip install -e ."
    exit 1
fi
echo "✓ transcribe found"
echo ""

# Test config command
echo "2. Testing config command..."
transcribe config
echo "✓ Config command works"
echo ""

# Check if config file was created
echo "3. Checking config file..."
if [ -f ~/.transcribe/config.yaml ]; then
    echo "✓ Config file exists at ~/.transcribe/config.yaml"
else
    echo "❌ Config file not created"
    exit 1
fi
echo ""

# Test setup-daemon command
echo "4. Testing daemon setup..."
transcribe setup-daemon
if [ -f ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist ]; then
    echo "✓ Daemon plist created"
else
    echo "❌ Daemon plist not created"
    exit 1
fi
echo ""

# Check dependencies
echo "5. Checking Python dependencies..."
python3 -c "import yaml; print('✓ yaml imported')"
python3 -c "import watchdog; print('✓ watchdog imported')"
python3 -c "import openai; print('✓ openai imported')"
python3 -c "import requests; print('✓ requests imported')"
echo ""

# Check system dependencies
echo "6. Checking system dependencies..."
if command -v ffmpeg &> /dev/null; then
    echo "✓ ffmpeg found"
else
    echo "❌ ffmpeg not found. Install with: brew install ffmpeg"
    exit 1
fi

if command -v whisper-cli &> /dev/null; then
    echo "✓ whisper-cli found"
else
    echo "❌ whisper-cli not found. Install with: brew install whisper-cpp"
    exit 1
fi
echo ""

echo "================================"
echo "✓ All tests passed!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Edit ~/.transcribe/config.yaml to add your API keys"
echo "2. Test with a video: transcribe /path/to/video.mov"
echo "3. Start daemon: launchctl load ~/Library/LaunchAgents/com.calebsargeant.transcribe.plist"
