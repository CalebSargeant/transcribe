"""Slack notification delivery."""

from datetime import datetime

from .gdrive import get_google_drive_folder_url


def send_slack_notification(video_name, folder_path, title, description, action_items, config):
    """Send notification to Slack with Google Drive folder link and action items."""
    try:
        import urllib.parse

        import requests

        # Check for bot token first, then webhook URL
        bot_token = config.get("slack_bot_token")
        channel_id = config.get("slack_channel_id")
        webhook_url = config.get("slack_webhook_url")

        if not bot_token and not webhook_url:
            print(
                "Warning: No Slack credentials configured "
                "(need bot_token+channel_id or webhook_url)"
            )
            return

        # Get Google Drive URL
        folder_link = get_google_drive_folder_url(folder_path)

        # Fall back to file:// if Drive API fails
        if not folder_link:
            folder_link = f"file://{urllib.parse.quote(str(folder_path))}"

        # Use title from OpenAI or fallback to video name
        header_text = title if title else f"📹 {video_name}"

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": header_text}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{description if description else 'Video transcribed and summarized'}\n\n<{folder_link}|Open folder in Google Drive>",  # noqa: E501
                },
            },
        ]

        # Add action items if any
        if action_items:
            action_text = "*Action Items:*\n" + "\n".join([f"• {item}" for item in action_items])
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": action_text}})

        # Add timestamp at the end
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Processed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    }
                ],
            }
        )

        # Send via bot token or webhook
        if bot_token and channel_id:
            # Use chat.postMessage API
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {bot_token}",
                    "Content-Type": "application/json",
                },
                json={"channel": channel_id, "blocks": blocks},
            )
            result = response.json()
            if not result.get("ok"):
                raise Exception(f"Slack API error: {result.get('error')}")
        else:
            # Use webhook
            response = requests.post(webhook_url, json={"blocks": blocks})
            response.raise_for_status()

        print("✓ Slack notification sent")

    except Exception as e:
        print(f"Warning: Failed to send Slack notification: {e}")
