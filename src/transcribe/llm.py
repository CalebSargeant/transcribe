"""LLM-backed summarization, title/description, and action-item extraction.

Supports two providers, selected via the ``llm_provider`` config key:

* ``claude``  (default) -> Anthropic Messages API (``anthropic`` SDK)
* ``openai``           -> OpenAI Chat Completions API (``openai`` SDK)

The three prompt intents (summary, title/description, action items) are
identical across providers; only the backend that produces the text differs.
If no API key is configured for the selected provider, the relevant function
degrades gracefully (returns ``None`` / ``[]``) exactly as the original
OpenAI-only code did for a missing key.
"""

# Default models per provider. ``claude-haiku-4-5-20251001`` is the current
# Claude Haiku 4.5 model id.
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _provider(config):
    """Return the configured provider name, defaulting to 'claude'."""
    if not config:
        return "claude"
    return (config.get("llm_provider") or "claude").strip().lower()


# --- Anthropic backend ------------------------------------------------------


def _anthropic_complete(system, user, api_key, model, max_tokens, temperature):
    """Run a single-turn Anthropic completion and return the text, or None."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "".join(parts)


# --- OpenAI backend ---------------------------------------------------------


def _openai_complete(system, user, api_key, model, max_tokens, temperature):
    """Run a single-turn OpenAI completion and return the text, or None."""
    import openai

    client = openai.OpenAI(api_key=api_key)
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


def _complete(config, system, user, max_tokens, temperature):
    """Dispatch a completion to the configured provider.

    Returns the generated text, or None if no key is configured for the
    selected provider (graceful skip, matching the original behavior).
    """
    provider = _provider(config)
    if provider == "openai":
        api_key = config.get("openai_api_key")
        if not api_key:
            return None
        model = config.get("openai_model") or DEFAULT_OPENAI_MODEL
        return _openai_complete(system, user, api_key, model, max_tokens, temperature)

    # Default: Claude / Anthropic
    api_key = config.get("anthropic_api_key")
    if not api_key:
        return None
    model = config.get("anthropic_model") or DEFAULT_ANTHROPIC_MODEL
    return _anthropic_complete(system, user, api_key, model, max_tokens, temperature)


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
