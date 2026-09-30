"""
demo_trigger
────────────
POST /demo/calls   body: {"sample_id": "<one of six preset ids>"}

Copies a preset Polly sample from the samples bucket into the voicemails
bucket, which kicks off the real intake pipeline (start_transcription →
Transcribe → process_transcript → routing) exactly as if a real voicemail
had arrived. No arbitrary uploads are accepted — only these six sample_ids
are valid, so the endpoint can be public without becoming a free file-drop.

The call_id is minted here (not by start_transcription) and embedded in the
destination S3 key as "demo-<call_id>.mp3". start_transcription recognizes
that pattern and reuses the embedded id, so this response can hand the
caller a call_id to poll GET /calls/{id}/timeline immediately.

A daily cap (DynamoDB atomic counter, see shared.dynamo.increment_daily_counter)
protects Transcribe/Claude cost from a public endpoint with no auth.
"""

import json
import logging
import os
import uuid

import boto3
from botocore.exceptions import ClientError

from shared.dynamo import increment_daily_counter

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))

SAMPLES_BUCKET = os.environ.get("SAMPLES_BUCKET")
VOICEMAILS_BUCKET = os.environ.get("VOICEMAILS_BUCKET")
DAILY_CAP = int(os.environ.get("DEMO_DAILY_CAP", "50"))

# The only sample_ids this endpoint will ever copy — matches the six MP3s
# scripts/make_samples.py generates. No other key is ever accepted.
ALLOWED_SAMPLE_IDS = frozenset({
    "breakdown_tow",
    "comeback",
    "repair_status",
    "billing",
    "parts_vendor",
    "spam_other",
})


def _json(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event: dict, context) -> dict:
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON body"})

    sample_id = payload.get("sample_id")
    if sample_id not in ALLOWED_SAMPLE_IDS:
        return _json(400, {"error": f"sample_id must be one of {sorted(ALLOWED_SAMPLE_IDS)}"})

    if not increment_daily_counter("demo-calls", DAILY_CAP):
        logger.warning("Daily demo cap (%d) reached — rejecting sample_id=%s", DAILY_CAP, sample_id)
        return _json(429, {"error": "daily demo call limit reached, try again tomorrow"})

    call_id = str(uuid.uuid4())
    dest_key = f"demo-{call_id}.mp3"

    try:
        _s3.copy_object(
            Bucket=VOICEMAILS_BUCKET,
            Key=dest_key,
            CopySource={"Bucket": SAMPLES_BUCKET, "Key": f"{sample_id}.mp3"},
        )
    except ClientError:
        logger.exception("Failed to copy sample %s to voicemails bucket", sample_id)
        return _json(502, {"error": "could not start demo call"})

    logger.info("demo_trigger: sample_id=%s -> call_id=%s key=%s", sample_id, call_id, dest_key)
    return _json(200, {"call_id": call_id, "sample_id": sample_id})
