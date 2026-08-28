"""Assembling a per-recording Whisper prompt from context, not from a hand-kept list.

Whisper's initial prompt is capped at ``n_text_ctx / 2`` tokens, which is 224.
That is a hard ceiling, so a domain vocabulary cannot simply accumulate: every
term added to a global list crowds out another. The prompt has to be *selected*
for the recording in front of you.

Three sources feed it, most specific first:

1. **The calendar event** -- its title and attendee names. A call titled
   "Janeway hosting review" primes "Janeway" with nobody typing anything.
2. **A mined glossary** -- terms that recur across the notes already written to
   the destination folder, which is exactly the domain vocabulary of the person
   running this. It is also where corrections land (see ``notes``), so a word
   the model misheard once is primed correctly the next time.
3. **The configured seed** -- ``whisper_prompt``, for terms that never appear in
   text on their own.

The result is fitted to the budget by priority, so the most specific terms
survive when it overflows.
"""

import contextlib
import json
import re
from pathlib import Path

# whisper caps the initial prompt at n_text_ctx/2 = 224 tokens. Leaving headroom
# avoids the tail being silently truncated mid-term.
DEFAULT_PROMPT_TOKEN_BUDGET = 190

GLOSSARY_FILE = Path.home() / ".transcribe" / "glossary.json"

# Terms worth priming: acronyms, CamelCase, hyphenated technical compounds, and
# anything carrying a digit. Ordinary sentence-case words are excluded because
# whisper already knows them and they would waste the budget.
_ACRONYM = re.compile(r"^[A-Z][A-Z0-9]{1,}$")
_CAMEL = re.compile(r"^[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+$")
_HAS_DIGIT = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]*\d[A-Za-z0-9.\-]*$")
_PROPER = re.compile(r"^[A-Z][a-z]{2,}$")

# Common English words that are capitalised often enough to look like terms.
_STOPWORDS = frozenset(
    [
        "The",
        "This",
        "That",
        "These",
        "Those",
        "There",
        "Their",
        "They",
        "Then",
        "Than",
        "And",
        "But",
        "For",
        "With",
        "From",
        "Into",
        "When",
        "What",
        "Where",
        "Which",
        "While",
        "Who",
        "Whom",
        "Whose",
        "Why",
        "How",
        "All",
        "Any",
        "Are",
        "Was",
        "Were",
        "Been",
        "Being",
        "Have",
        "Has",
        "Had",
        "Will",
        "Would",
        "Should",
        "Could",
        "May",
        "Might",
        "Must",
        "Can",
        "Not",
        "Now",
        "New",
        "Old",
        "One",
        "Two",
        "Three",
        "Yes",
        "No",
        "Okay",
        "Yeah",
        "Meeting",
        "Notes",
        "Summary",
        "Team",
        "Call",
        "Today",
        "Tomorrow",
        "Week",
        "Month",
        "Next",
        "Last",
        "First",
        "Second",
        "Third",
        "Also",
        "Only",
        "Just",
        "Very",
        "Much",
        "More",
        "Most",
        "Some",
        "Such",
        "Each",
        "Both",
        "Other",
        "Because",
        "Before",
        "After",
        "During",
        "Above",
        "Below",
        "Under",
        "Over",
        "Again",
        "Once",
        "Here",
        "Very",
        # Artifacts of this pipeline's own output, not domain vocabulary. Left
        # in, "Speaker" dominates the glossary: it appears in every set of notes
        # that had unnamed voices.
        "Speaker",
        "Unassigned",
        "Unknown",
        "Transcribed",
        "Whisper",
    ]
)


def _looks_like_term(word):
    """True when a word is worth spending prompt budget on."""
    word = word.strip(".,;:!?()[]\"'")
    if len(word) < 2 or word in _STOPWORDS:
        return False
    return bool(
        _ACRONYM.match(word) or _CAMEL.match(word) or _HAS_DIGIT.match(word) or _PROPER.match(word)
    )


def extract_terms(text):
    """Return the distinct domain-looking terms in a block of text."""
    seen = {}
    for word in re.findall(r"[A-Za-z][A-Za-z0-9.\-]*", text or ""):
        cleaned = word.strip(".-")
        if _looks_like_term(cleaned):
            seen.setdefault(cleaned, 0)
            seen[cleaned] += 1
    return seen


def terms_from_calendar(events):
    """Terms drawn from calendar events: titles and attendee names.

    These are the most specific signal available, because they describe the
    meeting actually being transcribed.
    """
    terms = []
    for event in events or []:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9.\-]*", event.get("title") or ""):
            if _looks_like_term(word):
                terms.append(word)
        for attendee in event.get("attendees") or []:
            # Attendee names help both transcription and speaker naming.
            terms.extend(part for part in attendee.split() if _looks_like_term(part))
    return _dedupe(terms)


def _dedupe(terms):
    """Preserve order while removing repeats, case-insensitively."""
    seen = set()
    ordered = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(term)
    return ordered


def load_glossary(path=None):
    """Load the mined glossary: ``{term: {"count": int, "last_seen": str}}``."""
    path = Path(path or GLOSSARY_FILE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_glossary(glossary, path=None):
    """Write the glossary, creating its directory if needed."""
    path = Path(path or GLOSSARY_FILE)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A glossary that cannot be written is a lost optimisation, not a failure.
    with contextlib.suppress(OSError):
        path.write_text(json.dumps(glossary, indent=2, sort_keys=True))


def record_terms(terms, path=None, when=None):
    """Merge terms into the glossary, bumping counts and recency.

    Corrections carry the most weight: a term the model had to be corrected on
    is precisely the one worth priming next time.
    """
    if not terms:
        return load_glossary(path)
    glossary = load_glossary(path)
    stamp = (when or "").strip() or None
    for term, weight in terms.items() if isinstance(terms, dict) else ((t, 1) for t in terms):
        entry = glossary.setdefault(term, {"count": 0, "last_seen": None})
        entry["count"] = int(entry.get("count", 0)) + int(weight)
        if stamp:
            entry["last_seen"] = stamp
    save_glossary(glossary, path)
    return glossary


def mine_notes(destination_dir, limit_files=60):
    """Mine terms from notes already written to the destination folder.

    Notes are LLM-written prose about the user's own work, which makes them a
    much cleaner source of domain vocabulary than raw transcripts.
    """
    directory = Path(destination_dir or ".")
    if not directory.exists():
        return {}

    try:
        files = sorted(
            directory.glob("*/notes.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:limit_files]
    except OSError:
        return {}

    counts = {}
    for path in files:
        try:
            notes = (json.loads(path.read_text()) or {}).get("notes") or {}
        except (OSError, json.JSONDecodeError):
            continue
        text = " ".join(
            [
                notes.get("title") or "",
                notes.get("summary") or "",
                " ".join(s.get("body", "") for s in notes.get("sections") or []),
                " ".join(d.get("body", "") for d in notes.get("details") or []),
            ]
        )
        for term, count in extract_terms(text).items():
            counts[term] = counts.get(term, 0) + count
    return counts


def _rank(glossary, mined):
    """Order terms by how strongly the corpus supports them."""
    combined = {}
    for term, entry in glossary.items():
        combined[term] = int(entry.get("count", 0)) * 3  # corrections weigh more
    for term, count in mined.items():
        combined[term] = combined.get(term, 0) + count
    return [term for term, _ in sorted(combined.items(), key=lambda kv: (-kv[1], kv[0]))]


def _estimate_tokens(words):
    """Rough token count for a comma-separated term list.

    Proper nouns and acronyms tokenise worse than ordinary words, so this
    deliberately overestimates rather than risking silent truncation.
    """
    return sum(max(1, round(len(word) / 3)) for word in words) + len(words)


def build_prompt(config=None, calendar_events=None, glossary_path=None):
    """Assemble the initial prompt for this recording, fitted to the budget.

    Priority is calendar, then the configured seed, then the mined glossary, so
    that when the budget runs out it is the most generic terms that are dropped.
    """
    config = config or {}
    budget = int(config.get("whisper_prompt_token_budget", DEFAULT_PROMPT_TOKEN_BUDGET))

    if not config.get("whisper_auto_prompt", True):
        return config.get("whisper_prompt") or ""

    seed = [
        word.strip()
        for word in re.split(r"[,\n]", config.get("whisper_prompt") or "")
        if word.strip()
    ]
    calendar = terms_from_calendar(calendar_events)
    ranked = _rank(load_glossary(glossary_path), mine_notes(config.get("destination_directory")))

    chosen = []
    for term in _dedupe([*calendar, *seed, *ranked]):
        candidate = [*chosen, term]
        if _estimate_tokens(candidate) > budget:
            if len(chosen) >= len(calendar):
                break
            continue  # never drop a calendar term for length alone
        chosen = candidate
    return ", ".join(chosen)
