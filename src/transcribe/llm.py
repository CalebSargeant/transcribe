"""LLM-backed summarization, structured notes, and action-item extraction.

Supports two providers, selected via the ``llm_provider`` config key:

* ``claude``  (default) -> Anthropic Messages API (``anthropic`` SDK)
* ``openai``           -> OpenAI Chat Completions API (``openai`` SDK)

Setting ``openai_base_url`` points the ``openai`` provider at any OpenAI-compatible
endpoint -- a LiteLLM gateway, Ollama, vLLM, LM Studio, OpenRouter -- which is how
you route through a self-hosted proxy or run a model locally.

Two shapes of call are used. Plain text completions back the legacy
summary/title/action-item helpers. Schema-constrained JSON completions back the
meeting notes: those need a fixed structure, so the schema is enforced by the
provider (Anthropic tool use, OpenAI JSON mode) rather than parsed hopefully out
of prose.

If no API key is configured for the selected provider, every function degrades
gracefully (returns ``None`` / ``[]`` / ``{}``) rather than failing the run --
the transcript is still worth having on its own.
"""

import json

# Default models per provider. ``claude-haiku-4-5-20251001`` is the current
# Claude Haiku 4.5 model id.
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _provider(config):
    """Return the configured provider name, defaulting to 'claude'."""
    if not config:
        return "claude"
    return (config.get("llm_provider") or "claude").strip().lower()


def api_key_for(config):
    """Return the API key for the selected provider, or '' when unset."""
    if _provider(config) == "openai":
        return (config or {}).get("openai_api_key") or ""
    return (config or {}).get("anthropic_api_key") or ""


def is_configured(config):
    """True when a key is set for the selected LLM provider."""
    return bool(api_key_for(config))


def _model_for(config):
    """Return the model id for the selected provider."""
    if _provider(config) == "openai":
        return (config or {}).get("openai_model") or DEFAULT_OPENAI_MODEL
    return (config or {}).get("anthropic_model") or DEFAULT_ANTHROPIC_MODEL


def _client_options(config):
    """Client kwargs shared by both SDKs: base URL, timeout, retry count.

    The SDK defaults (600s, 2 retries) mean one slow call can stall a run for
    half an hour before failing. A reasoning model on a long transcript is
    genuinely slow, so the timeout is generous but bounded.
    """
    options = {}
    base_url = _base_url_for(config)
    if base_url:
        options["base_url"] = base_url
    options["timeout"] = float((config or {}).get("llm_timeout_seconds", 600))
    options["max_retries"] = int((config or {}).get("llm_max_retries", 2))
    return options


def _base_url_for(config):
    """Return the API base URL override, or None to use the provider default.

    Lets the ``openai`` provider talk to any OpenAI-compatible endpoint: a
    LiteLLM gateway, Ollama, vLLM, LM Studio, OpenRouter.
    """
    if _provider(config) == "openai":
        return (config or {}).get("openai_base_url") or None
    return (config or {}).get("anthropic_base_url") or None


# --- Anthropic backend ------------------------------------------------------


def _anthropic_complete(system, user, api_key, model, max_tokens, temperature, options=None):
    """Run a single-turn Anthropic completion and return the text, or None."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, **(options or {}))
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "".join(parts)


def _anthropic_complete_json(
    system, user, schema, api_key, model, max_tokens, temperature, options=None
):
    """Get structured output from Anthropic by forcing a tool call.

    Forcing the tool makes the provider validate against ``schema``, which is
    far more dependable than asking for JSON in prose and parsing the result.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, **(options or {}))
    tool = {
        "name": "record_result",
        "description": "Record the structured result.",
        "input_schema": schema,
    }
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_result"},
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    return None


# --- OpenAI backend ---------------------------------------------------------


def _openai_complete(system, user, api_key, model, max_tokens, temperature, options=None):
    """Run a single-turn OpenAI completion and return the text, or None."""
    import openai

    client = openai.OpenAI(api_key=api_key, **(options or {}))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def _openai_complete_json(
    system, user, schema, api_key, model, max_tokens, temperature, options=None
):
    """Get structured output from OpenAI using JSON mode."""
    import openai

    client = openai.OpenAI(api_key=api_key, **(options or {}))
    # JSON mode requires the word "json" to appear in the prompt, and does not
    # itself enforce the schema, so the schema is also spelled out inline.
    system_with_schema = (
        f"{system}\n\nRespond with a single JSON object matching this JSON schema "
        f"exactly:\n{json.dumps(schema)}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_with_schema},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        # Reasoning models spend completion tokens on their chain of thought, so
        # a truncated response comes back with no content at all.
        raise ValueError(
            f"model returned no content (finish_reason={choice.finish_reason!r}); "
            "raise notes_max_tokens if this is a reasoning model"
        )
    return json.loads(content)


def _complete(config, system, user, max_tokens, temperature):
    """Dispatch a text completion to the configured provider.

    Returns the generated text, or None if no key is configured for the
    selected provider (graceful skip, matching the original behavior).
    """
    api_key = api_key_for(config)
    if not api_key:
        return None
    model = _model_for(config)
    backend = _openai_complete if _provider(config) == "openai" else _anthropic_complete
    return backend(system, user, api_key, model, max_tokens, temperature, _client_options(config))


def complete_json(config, system, user, schema, max_tokens=8000, temperature=0.2):
    """Dispatch a schema-constrained completion, returning a dict (or None)."""
    api_key = api_key_for(config)
    if not api_key:
        return None
    model = _model_for(config)
    backend = _openai_complete_json if _provider(config) == "openai" else _anthropic_complete_json
    try:
        return backend(
            system, user, schema, api_key, model, max_tokens, temperature, _client_options(config)
        )
    except Exception as e:
        print(f"Warning: structured LLM call failed ({type(e).__name__}: {e})")
        return None


def summarize_with_openai(transcript, config):
    """Summarize transcript using the configured LLM provider.

    The function name is retained for backwards compatibility; the provider is
    chosen from ``config`` (Claude by default, OpenAI if configured).
    """
    try:
        system = "You are a helpful assistant that summarizes video transcripts. Include key topics, action items, and notable timestamps if mentioned in the transcript."  # noqa: E501
        user = f"Please summarize this video transcript, including any action items and key timestamps:\n\n{transcript}"  # noqa: E501
        return _complete(config, system, user, max_tokens=1000, temperature=0.7)
    except Exception as e:
        print(f"Warning: Failed to summarize ({type(e).__name__}: {e})")
        return None


def generate_title_description_with_openai(transcript, config):
    """Generate a short title and description for Slack notification."""
    try:
        system = "You are a helpful assistant that creates concise titles and descriptions for video transcripts. The title should be 5-10 words, and the description should be 1-2 sentences (max 100 words) summarizing the key topic."  # noqa: E501
        user = f"Create a short title and 1-2 sentence description for this video transcript:\n\n{transcript}\n\nFormat your response as:\nTitle: [your title]\nDescription: [your description]"  # noqa: E501
        content = _complete(config, system, user, max_tokens=200, temperature=0.7)
        if not content:
            return None, None

        # Parse title and description
        lines = content.strip().split("\n")
        title = ""
        description = ""

        for line in lines:
            if line.startswith("Title:"):
                title = line.replace("Title:", "").strip()
            elif line.startswith("Description:"):
                description = line.replace("Description:", "").strip()

        return title, description
    except Exception as e:
        print(f"Warning: Failed to generate title/description ({type(e).__name__}: {e})")
        return None, None


def extract_action_items_with_openai(transcript, config):
    """Extract clear, actionable items from transcript."""
    try:
        system = "You are a helpful assistant that extracts actionable items from meeting transcripts. Only include items that are clearly actionable and should be acted upon. Each action item should be specific, clear, and include who should do it if mentioned. Format as a simple bullet list."  # noqa: E501
        user = f"Extract ONLY the clear, actionable items from this transcript. Do not include general discussion points or vague items. Each item should be something specific that needs to be done.\n\nTranscript:\n{transcript}\n\nFormat your response as a bullet list, one action per line starting with '- '. If there are no clear action items, respond with 'No specific action items identified.'"  # noqa: E501
        # Lower temperature for more focused output
        content = _complete(config, system, user, max_tokens=300, temperature=0.3)
        if not content:
            return []
        content = content.strip()

        # Check if there are actual action items
        if "no specific action items" in content.lower() or "no action items" in content.lower():
            return []

        # Parse action items
        action_items = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("•"):
                # Remove bullet and clean up
                item = line[1:].strip()
                if item:
                    action_items.append(item)

        return action_items
    except Exception as e:
        print(f"Warning: Failed to extract action items ({type(e).__name__}: {e})")
        return []
