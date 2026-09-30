"""
notes
─────
Input validation for the two write routes that add to a call's history:

  POST /calls/{id}/notes     {"text": "...", "author": "optional name"}
  POST /calls/{id}/attempts  {"outcome": "reached" | "no_answer", "note": "...", "author": "..."}

Pure functions (no AWS calls) so the rules are easy to test. The API is public
and has no login, so everything is length-capped and a call's history is
bounded (MAX_EVENTS_PER_CALL) to keep a bad actor from filling the table.
"""

MAX_TEXT_CHARS = 500
MAX_AUTHOR_CHARS = 40
MAX_EVENTS_PER_CALL = 100
OUTCOMES = {"reached", "no_answer"}


def _clean(value, limit: int, field: str):
    """Return (stripped string or None, error). Non-strings are rejected."""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"{field} must be text"
    value = value.strip()
    if len(value) > limit:
        return None, f"{field} must be {limit} characters or fewer"
    return (value or None), None


def parse_note(payload):
    """Validate a note body. Returns (detail dict, None) or (None, error message)."""
    if not isinstance(payload, dict):
        return None, "body must be a JSON object"
    text, err = _clean(payload.get("text"), MAX_TEXT_CHARS, "text")
    if err:
        return None, err
    if not text:
        return None, "text is required"
    author, err = _clean(payload.get("author"), MAX_AUTHOR_CHARS, "author")
    if err:
        return None, err
    detail = {"text": text}
    if author:
        detail["author"] = author
    return detail, None


def parse_attempt(payload):
    """Validate an attempt body. Returns (detail dict, None) or (None, error message)."""
    if not isinstance(payload, dict):
        return None, "body must be a JSON object"
    outcome = payload.get("outcome")
    if outcome not in OUTCOMES:
        return None, "outcome must be reached or no_answer"
    note, err = _clean(payload.get("note"), MAX_TEXT_CHARS, "note")
    if err:
        return None, err
    author, err = _clean(payload.get("author"), MAX_AUTHOR_CHARS, "author")
    if err:
        return None, err
    detail = {"outcome": outcome}
    if note:
        detail["text"] = note
    if author:
        detail["author"] = author
    return detail, None
