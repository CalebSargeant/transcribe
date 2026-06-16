"""Directory watching via watchdog."""

import sys
import time
from datetime import datetime
from pathlib import Path

from .processing import process_video_file


def watch_directory(directory, config):
    """Watch a directory for new video files and process them."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("Error: watchdog library not installed. Install with: pip install watchdog")
        sys.exit(1)

    # Write startup message to log (for daemon visibility)
    startup_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Transcribe daemon started\n"
    startup_msg += f"Watching: {directory}\n"
    startup_msg += f"Extensions: {', '.join(config.get('video_extensions', []))}\n"
    print(startup_msg, flush=True)

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
                print(f"Detected new file: {Path(file_path).name}", flush=True)
                print("Waiting for file to finish writing...", flush=True)
                time.sleep(2)

                # Check if file still exists and is accessible
                if Path(file_path).exists():
                    process_video_file(file_path, self.config)

                self.processing.discard(file_path)

    print(f"Watching directory: {directory}", flush=True)
    print(f"Video extensions: {', '.join(config.get('video_extensions', []))}", flush=True)
    print("Press Ctrl+C to stop...\n", flush=True)
    sys.stdout.flush()

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
