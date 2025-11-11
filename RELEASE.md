# Release Instructions

## Creating a New Release

1. **Update version number** in:
   - `setup.py` (version field)
   - `CHANGELOG.md` (new version section)

2. **Commit and tag**:
   ```bash
   git add .
   git commit -m "Release v2.0.0"
   git tag v2.0.0
   git push origin main --tags
   ```

3. **Create GitHub release**:
   - Go to https://github.com/calebsargeant/transcribe/releases/new
   - Select the tag you just created
   - Add release notes
   - Publish release

4. **Calculate SHA256 for Homebrew formula**:
   ```bash
   # Get the tarball SHA256
   curl -L https://github.com/calebsargeant/transcribe/archive/refs/tags/v2.0.0.tar.gz | shasum -a 256
   
   # Get the model SHA256 (if not already done)
   curl -L https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin | shasum -a 256
   ```

5. **Update Homebrew formula** at `~/Nextcloud/repos/calebsargeant/homebrew-tap/Formula/transcribe.rb`:
   - Replace `REPLACE_WITH_ACTUAL_SHA256` with the tarball SHA256
   - Replace `REPLACE_WITH_MODEL_SHA256` with the model SHA256
   - Update version number in URL (already set to v2.0.0)
   - Python dependencies are already configured

6. **Test the formula locally**:
   ```bash
   # Uninstall old version if installed
   brew uninstall transcribe 2>/dev/null || true
   
   # Install from local formula
   brew install --build-from-source ~/Nextcloud/repos/calebsargeant/homebrew-tap/Formula/transcribe.rb
   
   # Test basic functionality
   transcribe config
   transcribe --help
   ```

7. **Test the new features**:
   ```bash
   # Setup config (edit with your API keys)
   transcribe config
   
   # Test single file transcription
   transcribe /path/to/test-video.mov
   
   # Test watch mode (Ctrl+C to stop)
   transcribe watch ~/Movies
   
   # Test daemon setup
   transcribe setup-daemon
   ```

8. **Push Homebrew formula**:
   ```bash
   cd ~/Nextcloud/repos/calebsargeant/homebrew-tap
   git add Formula/transcribe.rb
   git commit -m "Update transcribe to v2.0.0 - Add watch mode, OpenAI summarization, and Slack notifications"
   git push
   ```

## Local Development Install

```bash
cd ~/repos/calebsargeant/transcribe
pip install -e .
```

## Building a Portable Binary (Alternative)

If you want a single binary instead of Python package:

```bash
# Install PyInstaller
pip install pyinstaller

# Create binary
pyinstaller --onefile --name transcribe transcribe.py

# Binary will be in dist/transcribe
./dist/transcribe video.mov
```

Then you can create a simpler Homebrew formula that just downloads the binary (like maniforge).
