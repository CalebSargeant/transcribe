"""File movement and end-to-end video processing pipeline."""

import json
import shutil
from pathlib import Path

from .config import load_config
from .llm import (
    extract_action_items_with_openai,
    generate_title_description_with_openai,
    summarize_with_openai,
)
from .slack import send_slack_notification
from .whisper import transcribe_video


def _llm_configured(config):
    """Return True if a key is set for the selected LLM provider."""
    provider = (config.get("llm_provider") or "claude").strip().lower()
    if provider == "openai":
        return bool(config.get("openai_api_key"))
    return bool(config.get("anthropic_api_key"))


def move_files_to_destination(video_path, transcript_path, summary_path, config):
    """Move all files to a dedicated folder in the destination directory."""
    base_dest_dir = Path(config["destination_directory"])

    # Create a folder named after the video file (without extension)
    video_name = Path(video_path).stem
    video_folder = base_dest_dir / video_name
    video_folder.mkdir(parents=True, exist_ok=True)

    moved_files = {}

    # Move video
    video_dest = video_folder / Path(video_path).name
    shutil.move(video_path, video_dest)
    moved_files["video"] = str(video_dest)
    print(f"✓ Moved video to {video_dest}")

    # Move transcript
    if Path(transcript_path).exists():
        transcript_dest = video_folder / Path(transcript_path).name
        shutil.move(transcript_path, transcript_dest)
        moved_files["transcript"] = str(transcript_dest)
        print(f"✓ Moved transcript to {transcript_dest}")

    # Move summary if it exists
    if summary_path and Path(summary_path).exists():
        summary_dest = video_folder / Path(summary_path).name
        shutil.move(summary_path, summary_dest)
        moved_files["summary"] = str(summary_dest)
        print(f"✓ Moved summary to {summary_dest}")

    # Return the folder path as well
    moved_files["folder"] = str(video_folder)

    return moved_files


def process_video_file(video_file, config=None, write_json=False):
    """Process a video file: transcribe, summarize, move, and notify.

    If ``write_json`` is True, also write ``<video>_result.json`` next to the
    video containing title, description, transcript, summary, action items,
    and the source file path.
    """
    if config is None:
        config = load_config()

    print(f"\n{'=' * 60}")
    print(f"Processing: {Path(video_file).name}")
    print(f"{'=' * 60}\n")

    try:
        # Transcribe
        transcript = transcribe_video(video_file, config)
        print("\n--- Transcription Complete ---")

        # Save transcript
        transcript_file = video_file.rsplit(".", 1)[0] + "_transcript.txt"
        with open(transcript_file, "w") as f:
            f.write(transcript)
        print(f"✓ Transcript saved to: {transcript_file}")

        # Generate title and description with the configured LLM provider
        title = None
        description = None
        summary = None
        summary_file = None

        if _llm_configured(config):
            print("\n--- Generating Summary ---")
            summary = summarize_with_openai(transcript, config)
            if summary:
                summary_file = video_file.rsplit(".", 1)[0] + "_summary.txt"
                with open(summary_file, "w") as f:
                    f.write(summary)
                print(f"✓ Summary saved to: {summary_file}")

            print("\n--- Generating Title & Description for Slack ---")
            title, description = generate_title_description_with_openai(transcript, config)
            if title:
                print(f"✓ Title: {title}")
            if description:
                print(f"✓ Description: {description}")

            print("\n--- Extracting Action Items ---")
            action_items = extract_action_items_with_openai(transcript, config)
            if action_items:
                print(f"✓ Found {len(action_items)} action item(s)")
                for i, item in enumerate(action_items, 1):
                    print(f"  {i}. {item}")
            else:
                print("✓ No specific action items identified")
        else:
            action_items = []

        # Build the JSON result payload (written after the move below so it
        # lands in the same destination folder as the transcript/summary).
        result_payload = None
        if write_json:
            result_payload = {
                "title": title,
                "description": description,
                "transcript": transcript,
                "summary": summary,
                "action_items": action_items,
                "source_file": video_file,
            }

        # Move files to destination
        if config.get("destination_directory"):
            print("\n--- Moving Files ---")
            moved_files = move_files_to_destination(
                video_file, transcript_file, summary_file, config
            )

            # Write the JSON result into the same destination folder as the
            # moved transcript/summary, so it is not orphaned at the source.
            if result_payload is not None:
                result_name = Path(video_file).stem + "_result.json"
                result_file = str(Path(moved_files["folder"]) / result_name)
                with open(result_file, "w") as f:
                    json.dump(result_payload, f, indent=2, ensure_ascii=False)
                print(f"✓ JSON result saved to: {result_file}")

            # Send Slack notification
            if config.get("slack_webhook_url") or config.get("slack_bot_token"):
                print("\n--- Sending Notification ---")
                send_slack_notification(
                    Path(video_file).name,
                    moved_files.get("folder"),
                    title,
                    description,
                    action_items,
                    config,
                )
        elif result_payload is not None:
            # No destination configured: fall back to writing the JSON next to
            # the (un-moved) source video so the output is not lost.
            result_file = video_file.rsplit(".", 1)[0] + "_result.json"
            with open(result_file, "w") as f:
                json.dump(result_payload, f, indent=2, ensure_ascii=False)
            print(f"✓ JSON result saved to: {result_file}")

        print(f"\n{'=' * 60}")
        print("✓ Processing complete!")
        print(f"{'=' * 60}\n")

    except Exception as e:
        print(f"\nError processing {video_file}: {e}")
        import traceback

        traceback.print_exc()
