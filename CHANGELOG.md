# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-11-11

### Added
- **Watch Mode**: Monitor directories for new video files with `transcribe watch <directory>`
- **Background Daemon**: Auto-start transcription service with `transcribe setup-daemon`
- **OpenAI Integration**: Automatic summarization of transcripts with timestamps and action items
- **Slack Notifications**: Send formatted notifications when processing completes
- **File Management**: Automatically move processed files to configurable destination (e.g., iCloud)
- **Configuration System**: YAML-based config at `~/.transcribe/config.yaml`
- **Multi-file Output**: Generate transcript + AI summary for each video
- `transcribe config` command to view/edit configuration
- Support for multiple video formats (.mov, .mp4, .avi, .mkv, .m4v)
- Example configuration file (`config.example.yaml`)

### Changed
- Refactored main transcription logic into `process_video_file()` function
- Enhanced output with progress indicators and emoji
- Improved error handling and logging
- Updated README with comprehensive documentation
- Version bumped to 2.0.0 to reflect major feature additions

### Dependencies
- Added `pyyaml>=6.0` for configuration management
- Added `watchdog>=3.0.0` for directory monitoring
- Added `openai>=1.0.0` for AI summarization
- Added `requests>=2.31.0` for Slack notifications

### Technical
- Implemented FileSystemEventHandler for robust file watching
- Added launchd plist generation for macOS daemon support
- Structured code with separate functions for each workflow step
- Added configuration validation and defaults

## [1.0.0] - 2024-10-29

### Added
- Initial release
- Basic video/audio transcription using whisper-cpp
- Command-line interface: `transcribe <video_file>`
- Automatic audio extraction from video files
- Transcript saved as text file alongside original video
- Support for local Whisper model (ggml-base.bin)
- Homebrew tap formula for easy installation

### Requirements
- macOS
- Python 3.9+
- whisper-cpp
- ffmpeg
