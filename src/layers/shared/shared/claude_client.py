"""
shared.claude_client
────────────────────
Thin wrapper around the Anthropic SDK.

The API key is read from SSM Parameter Store exactly once per Lambda
execution environment (cold start) and cached in _api_key. Subsequent
warm invocations skip the SSM call entirely.

Usage:
    from shared.claude_client import classify_transcript
    result = classify_transcript(transcript_text)
"""

import json
import logging
import os

import anthropic
import boto3

logger = logging.getLogger(__name__)

# Module-level cache — populated on first call, reused on warm invocations.
_api_key: str | None = None
_client: anthropic.Anthropic | None = None

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

CLASSIFICATION_SYSTEM_PROMPT = """You are a call-triage assistant for an independent auto repair shop.
You will receive a voicemail transcript. Extract structured information and return ONLY valid JSON — no explanation, no markdown, no preamble.

Return exactly this JSON shape:
{
  "category": "<one of: comeback | breakdown_tow | repair_status | scheduling | estimate | billing | parts_vendor | spam_other>",
  "urgency": "<one of: emergency | high | normal | low>",
  "is_comeback": <true|false>,
  "caller_name": "<name or null>",
  "callback_number": "<phone or null>",
  "vehicle": "<year/make/model or null>",
  "summary": "<one sentence>",
  "action_items": ["<item>"]
}

Category definitions:
- comeback: caller mentions a recent repair at this shop AND reports the same or related problem
- breakdown_tow: vehicle is disabled on the road right now, needs a tow
- repair_status: checking whether their car is ready or asking for a status update
- scheduling: wants to book an appointment
- estimate: wants a price quote
- billing: payment issue, dispute, or question about a charge
- parts_vendor: call is from a parts supplier, not a customer
- spam_other: spam, warranty robo-calls, or anything that doesn't fit

Urgency rules:
- emergency: vehicle disabled on road, safety concern, or caller is stranded
- high: comeback with safety implication, or strong frustration/urgency language
- normal: standard service request with normal tone
- low: informational, vendor, spam

is_comeback: true only when the caller explicitly mentions a previous repair at this shop
AND the same or related problem is occurring again.

caller_name, callback_number, and vehicle: only fill these in when they are explicitly stated
in the transcript. Never infer or guess a value. Use null for any of these three fields that
the transcript does not state."""


def _get_client() -> anthropic.Anthropic:
    """Return a cached Anthropic client, fetching the key from SSM if needed."""
    global _api_key, _client

    if _client is not None:
        return _client

    param_name = os.environ["ANTHROPIC_KEY_PARAM"]
    logger.info("Cold start: fetching Anthropic key from SSM %s", param_name)

    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    response = ssm.get_parameter(Name=param_name, WithDecryption=True)
    _api_key = response["Parameter"]["Value"]
    _client = anthropic.Anthropic(api_key=_api_key)
    logger.info("Anthropic client initialised (model: %s)", MODEL)
    return _client


def classify_transcript(transcript_text: str) -> dict:
    """
    Send transcript_text to Claude and return the parsed classification dict.

    Raises ValueError if the response is not valid JSON or is missing required keys.
    Callers should catch this and fall back to needs_review status.
    """
    client = _get_client()

    message = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=CLASSIFICATION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Voicemail transcript:\n\n{transcript_text}",
            }
        ],
    )

    # Claude Sonnet 5 has adaptive thinking enabled by default, which means
    # the response may contain a thinking block before the text block.
    # Find the first content block of type "text" instead of assuming [0] is text.
    text_block = next(
        (block for block in message.content if getattr(block, "type", None) == "text"),
        None,
    )
    if text_block is None:
        block_types = [getattr(b, "type", "unknown") for b in message.content]
        raise ValueError(f"No text block in Claude response. Block types: {block_types}")

    raw = text_block.text.strip()
    # Claude Sonnet 5 sometimes wraps JSON in markdown code fences (```json ... ```)
    # despite the system prompt saying not to. Strip them if present.
    if raw.startswith("```"):
        lines = raw.splitlines()
        # Drop first line (```json or ```) and last line (```)
        raw = "\n".join(
            line for line in lines[1:]
            if line.strip() != "```"
        ).strip()
    logger.info("Claude raw response (first 200 chars): %s", raw[:200])

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned non-JSON: {raw[:200]}") from exc

    required = {"category", "urgency", "is_comeback", "summary", "action_items"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")

    # Normalise — ensure action_items is always a list
    if not isinstance(data.get("action_items"), list):
        data["action_items"] = [str(data["action_items"])] if data.get("action_items") else []

    return data
