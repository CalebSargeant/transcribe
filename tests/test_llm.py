"""Tests for transcribe.llm: provider dispatch, graceful skip, parsing."""

from transcribe import llm
from transcribe.llm import (
    _complete,
    _provider,
    extract_action_items_with_openai,
    generate_title_description_with_openai,
    summarize_with_openai,
)

# --- _provider --------------------------------------------------------------


def test_provider_defaults_to_claude_for_empty_config():
    assert _provider({}) == "claude"
    assert _provider(None) == "claude"


def test_provider_reads_config_and_normalizes():
    assert _provider({"llm_provider": "openai"}) == "openai"
    assert _provider({"llm_provider": "  OpenAI  "}) == "openai"
    assert _provider({"llm_provider": "CLAUDE"}) == "claude"


def test_provider_none_value_falls_back_to_claude():
    assert _provider({"llm_provider": None}) == "claude"


# --- _complete dispatch -----------------------------------------------------


def test_complete_dispatches_to_anthropic_by_default(fake_anthropic, base_config):
    fake_anthropic["set_text"]("hello from claude")
    base_config["anthropic_api_key"] = "sk-ant"

    result = _complete(base_config, "sys", "user", max_tokens=100, temperature=0.5)

    assert result == "hello from claude"
    assert fake_anthropic["init_keys"] == ["sk-ant"]
    call = fake_anthropic["calls"][0]
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["max_tokens"] == 100
    assert call["temperature"] == 0.5
    assert call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "user"}]


def test_complete_joins_only_text_blocks(fake_anthropic, base_config):
    fake_anthropic["set_text"]("part1 ", "part2", include_nontext=True)
    base_config["anthropic_api_key"] = "sk-ant"

    result = _complete(base_config, "s", "u", max_tokens=10, temperature=0.1)
    # The non-text (thinking) block is excluded.
    assert result == "part1 part2"


def test_complete_dispatches_to_openai_when_selected(fake_openai, base_config):
    fake_openai["set_content"]("hello from openai")
    base_config["llm_provider"] = "openai"
    base_config["openai_api_key"] = "sk-oai"

    result = _complete(base_config, "sys", "user", max_tokens=50, temperature=0.2)

    assert result == "hello from openai"
    assert fake_openai["init_keys"] == ["sk-oai"]
    call = fake_openai["calls"][0]
    assert call["model"] == "gpt-4o-mini"
    assert call["max_tokens"] == 50
    assert call["temperature"] == 0.2
    assert call["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]


def test_complete_returns_none_when_claude_key_missing(fake_anthropic, base_config):
    base_config["anthropic_api_key"] = ""
    result = _complete(base_config, "s", "u", max_tokens=10, temperature=0.1)
    assert result is None
    # SDK client was never constructed
    assert fake_anthropic["init_keys"] == []


def test_complete_returns_none_when_openai_key_missing(fake_openai, base_config):
    base_config["llm_provider"] = "openai"
    base_config["openai_api_key"] = ""
    result = _complete(base_config, "s", "u", max_tokens=10, temperature=0.1)
    assert result is None
    assert fake_openai["init_keys"] == []


def test_complete_respects_custom_models(fake_anthropic, fake_openai, base_config):
    base_config["anthropic_api_key"] = "k"
    base_config["anthropic_model"] = "claude-haiku-4-5"
    _complete(base_config, "s", "u", max_tokens=1, temperature=0.0)
    assert fake_anthropic["calls"][0]["model"] == "claude-haiku-4-5"

    base_config["llm_provider"] = "openai"
    base_config["openai_api_key"] = "k"
    base_config["openai_model"] = "gpt-4o"
    _complete(base_config, "s", "u", max_tokens=1, temperature=0.0)
    assert fake_openai["calls"][0]["model"] == "gpt-4o"


def test_complete_falls_back_to_default_model_when_blank(fake_anthropic, base_config):
    base_config["anthropic_api_key"] = "k"
    base_config["anthropic_model"] = ""
    _complete(base_config, "s", "u", max_tokens=1, temperature=0.0)
    assert fake_anthropic["calls"][0]["model"] == llm.DEFAULT_ANTHROPIC_MODEL


# --- summarize_with_openai --------------------------------------------------


def test_summarize_returns_text(fake_anthropic, base_config):
    fake_anthropic["set_text"]("a summary")
    base_config["anthropic_api_key"] = "k"
    assert summarize_with_openai("transcript text", base_config) == "a summary"
    # Transcript embedded in the user prompt
    assert "transcript text" in fake_anthropic["calls"][0]["messages"][0]["content"]


def test_summarize_returns_none_when_no_key(fake_anthropic, base_config):
    base_config["anthropic_api_key"] = ""
    assert summarize_with_openai("x", base_config) is None


def test_summarize_swallows_exceptions(monkeypatch, base_config, capsys):
    base_config["anthropic_api_key"] = "k"

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(llm, "_complete", boom)
    assert summarize_with_openai("x", base_config) is None
    assert "Failed to summarize" in capsys.readouterr().out


# --- generate_title_description_with_openai ---------------------------------


def test_title_description_parsed(fake_anthropic, base_config):
    fake_anthropic["set_text"]("Title: My Video\nDescription: A short blurb.")
    base_config["anthropic_api_key"] = "k"
    title, desc = generate_title_description_with_openai("t", base_config)
    assert title == "My Video"
    assert desc == "A short blurb."


def test_title_description_none_when_no_content(fake_anthropic, base_config):
    base_config["anthropic_api_key"] = ""  # _complete returns None
    title, desc = generate_title_description_with_openai("t", base_config)
    assert title is None
    assert desc is None


def test_title_description_handles_missing_fields(fake_anthropic, base_config):
    fake_anthropic["set_text"]("Title: Only A Title")
    base_config["anthropic_api_key"] = "k"
    title, desc = generate_title_description_with_openai("t", base_config)
    assert title == "Only A Title"
    assert desc == ""


def test_title_description_swallows_exceptions(monkeypatch, base_config, capsys):
    base_config["anthropic_api_key"] = "k"
    monkeypatch.setattr(llm, "_complete", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    title, desc = generate_title_description_with_openai("t", base_config)
    assert (title, desc) == (None, None)
    assert "Failed to generate title/description" in capsys.readouterr().out


# --- extract_action_items_with_openai ---------------------------------------


def test_action_items_parsed(fake_anthropic, base_config):
    fake_anthropic["set_text"]("- First task\n- Second task\n• Third task")
    base_config["anthropic_api_key"] = "k"
    items = extract_action_items_with_openai("t", base_config)
    assert items == ["First task", "Second task", "Third task"]


def test_action_items_empty_when_none_identified(fake_anthropic, base_config):
    fake_anthropic["set_text"]("No specific action items identified.")
    base_config["anthropic_api_key"] = "k"
    assert extract_action_items_with_openai("t", base_config) == []


def test_action_items_empty_when_no_key(fake_anthropic, base_config):
    base_config["anthropic_api_key"] = ""
    assert extract_action_items_with_openai("t", base_config) == []


def test_action_items_ignores_non_bullet_lines(fake_anthropic, base_config):
    fake_anthropic["set_text"]("Here are the items:\n- Do the thing\nrandom line")
    base_config["anthropic_api_key"] = "k"
    assert extract_action_items_with_openai("t", base_config) == ["Do the thing"]


def test_action_items_swallows_exceptions(monkeypatch, base_config, capsys):
    base_config["anthropic_api_key"] = "k"
    monkeypatch.setattr(llm, "_complete", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    assert extract_action_items_with_openai("t", base_config) == []
    assert "Failed to extract action items" in capsys.readouterr().out


def test_action_items_uses_openai_when_selected(fake_openai, base_config):
    fake_openai["set_content"]("- OpenAI task")
    base_config["llm_provider"] = "openai"
    base_config["openai_api_key"] = "k"
    assert extract_action_items_with_openai("t", base_config) == ["OpenAI task"]
    # Lower temperature for action-item extraction is preserved.
    assert fake_openai["calls"][0]["temperature"] == 0.3
