"""Slack notification delivery."""

from datetime import datetime

from .links import describe_location


def _location_block(folder_path, config):
    """Render where the meeting was filed, as a link when one is possible.

    Slack does not linkify ``file://``, so a local path is shown as code rather
    than as a link that renders dead.
    """
    url, label, local_path = describe_location(folder_path, config)
    if url:
        return f"<{url}|{label}>\n`{local_path}`"
    return f"`{local_path}`"


def send_slack_notification(video_name, folder_path, title, description, action_items, config):
    """Send notification to Slack with a folder link and action items."""
    try:
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

        # Use title from the LLM, or fall back to the file name
        header_text = title if title else f"📹 {video_name}"

        body = description if description else "Video transcribed and summarized"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": header_text}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{body}\n\n{_location_block(folder_path, config)}",
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
                json={"channel": channel_id, "blocks": blocks, "text": header_text},
            )
            result = response.json()
            if not result.get("ok"):
                raise Exception(f"Slack API error: {result.get('error')}")
        else:
            # Use webhook
            response = requests.post(webhook_url, json={"blocks": blocks, "text": header_text})
            response.raise_for_status()

        print("✓ Slack notification sent")

    except Exception as e:
        print(f"Warning: Failed to send Slack notification: {e}")
