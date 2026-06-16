"""Tests for transcribe.slack: payload shape, webhook vs bot, graceful skip."""

import sys
import types

import pytest

from transcribe import slack
from transcribe.slack import send_slack_notification


@pytest.fixture
def fake_requests(monkeypatch):
    """Install a fake ``requests`` module; record posts, control the response."""
    state = {"posts": [], "json": {"ok": True}, "raise_status": None}

    class FakeResponse:
        def json(self):
            return state["json"]

        def raise_for_status(self):
            if state["raise_status"]:
                raise state["raise_status"]

    def fake_post(url, **kwargs):
        state["posts"].append({"url": url, **kwargs})
        return FakeResponse()

    fake_mod = types.ModuleType("requests")
    fake_mod.post = fake_post
    monkeypatch.setitem(sys.modules, "requests", fake_mod)
    return state


@pytest.fixture
def no_gdrive(monkeypatch):
    """Force the Google Drive lookup to return None so we hit the file:// fallback."""
    monkeypatch.setattr(slack, "get_google_drive_folder_url", lambda p: None)


def test_webhook_payload_shape(fake_requests, no_gdrive, base_config):
    base_config["slack_webhook_url"] = "https://hooks.slack.com/abc"

    send_slack_notification(
        "video.mov",
        "/dest/video",
        "My Title",
        "My description.",
        ["Do thing A", "Do thing B"],
        base_config,
    )

    assert len(fake_requests["posts"]) == 1
    post = fake_requests["posts"][0]
    assert post["url"] == "https://hooks.slack.com/abc"
    blocks = post["json"]["blocks"]

    # Header uses the provided title.
    assert blocks[0]["type"] == "header"
    assert blocks[0]["text"]["text"] == "My Title"

    # Section contains description + the file:// fallback link.
    section_text = blocks[1]["text"]["text"]
    assert "My description." in section_text
    assert "file://" in section_text

    # Action-items section present with bulleted items.
    action_block = blocks[2]["text"]["text"]
    assert "*Action Items:*" in action_block
    assert "• Do thing A" in action_block
    assert "• Do thing B" in action_block

    # Trailing context block with a "Processed:" timestamp.
    assert blocks[-1]["type"] == "context"
    assert "Processed:" in blocks[-1]["elements"][0]["text"]


def test_header_falls_back_to_video_name(fake_requests, no_gdrive, base_config):
    base_config["slack_webhook_url"] = "https://hooks.slack.com/abc"
    send_slack_notification("clip.mov", "/dest/clip", None, None, [], base_config)
    blocks = fake_requests["posts"][0]["json"]["blocks"]
    assert blocks[0]["text"]["text"] == "📹 clip.mov"
    # Default description text used when none supplied.
    assert "Video transcribed and summarized" in blocks[1]["text"]["text"]


def test_no_action_items_block_when_empty(fake_requests, no_gdrive, base_config):
    base_config["slack_webhook_url"] = "https://hooks.slack.com/abc"
    send_slack_notification("c.mov", "/d/c", "T", "D", [], base_config)
    blocks = fake_requests["posts"][0]["json"]["blocks"]
    # header, section, context => 3 blocks, no action-items section.
    assert len(blocks) == 3
    assert all("Action Items" not in str(b) for b in blocks)


def test_bot_token_uses_chat_post_message(fake_requests, no_gdrive, base_config):
    base_config["slack_bot_token"] = "xoxb-token"
    base_config["slack_channel_id"] = "C123"

    send_slack_notification("v.mov", "/d/v", "T", "D", [], base_config)

    post = fake_requests["posts"][0]
    assert post["url"] == "https://slack.com/api/chat.postMessage"
    assert post["headers"]["Authorization"] == "Bearer xoxb-token"
    assert post["json"]["channel"] == "C123"
    assert "blocks" in post["json"]


def test_bot_token_api_error_is_caught(fake_requests, no_gdrive, base_config, capsys):
    base_config["slack_bot_token"] = "xoxb-token"
    base_config["slack_channel_id"] = "C123"
    fake_requests["json"] = {"ok": False, "error": "channel_not_found"}

    # Should not raise; the error is logged.
    send_slack_notification("v.mov", "/d/v", "T", "D", [], base_config)
    out = capsys.readouterr().out
    assert "Failed to send Slack notification" in out
    assert "channel_not_found" in out


def test_no_credentials_warns_and_skips(fake_requests, no_gdrive, base_config, capsys):
    base_config["slack_webhook_url"] = ""
    send_slack_notification("v.mov", "/d/v", "T", "D", [], base_config)
    assert fake_requests["posts"] == []
    assert "No Slack credentials configured" in capsys.readouterr().out


def test_uses_google_drive_link_when_available(fake_requests, monkeypatch, base_config):
    base_config["slack_webhook_url"] = "https://hooks.slack.com/abc"
    monkeypatch.setattr(
        slack,
        "get_google_drive_folder_url",
        lambda p: "https://drive.google.com/drive/folders/XYZ",
    )
    send_slack_notification("v.mov", "/d/v", "T", "D", [], base_config)
    section_text = fake_requests["posts"][0]["json"]["blocks"][1]["text"]["text"]
    assert "https://drive.google.com/drive/folders/XYZ" in section_text


def test_success_prints_confirmation(fake_requests, no_gdrive, base_config, capsys):
    base_config["slack_webhook_url"] = "https://hooks.slack.com/abc"
    send_slack_notification("v.mov", "/d/v", "T", "D", [], base_config)
    assert "Slack notification sent" in capsys.readouterr().out
