"""
start_transcription
───────────────────
Triggered by S3 ObjectCreated on the shoptriage-voicemails bucket.

Flow:
  1. Validate the uploaded file (extension must be one Transcribe supports; see
     SUPPORTED_FORMATS)
  2. Mint a call_id (UUID4)
  3. Write CALL#<call_id>/META to DynamoDB with status=new
  4. Write timeline event: stage=uploaded
  5. Start an Amazon Transcribe job named shoptriage-<call_id>
  6. Write timeline event: stage=transcribing
  7. Return — no polling. EventBridge fires when the job completes.

The call_id is embedded in the Transcribe job name so process_transcript
can extract it from the EventBridge event without an extra DB lookup.
"""

import json
import logging
import os
import re
import urllib.parse
import uuid
from datetime import datetime, timezone

import boto3

# Shared layer modules (installed via Lambda Layer)
from shared.dynamo import put_call_record
from shared.timeline import log_event, STAGE_UPLOADED, STAGE_TRANSCRIBING

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

TRANSCRIBE = boto3.client("transcribe", region_name=os.environ.get("AWS_REGION", "us-east-1"))

# Where Transcribe will write its JSON output. We use a dedicated prefix
# in the same account so process_transcript can read it with a scoped policy.
OUTPUT_BUCKET = os.environ.get(
    "TRANSCRIBE_OUTPUT_BUCKET",
    f"shoptriage-transcribe-output-{boto3.client('sts').get_caller_identity()['Account']}"
    if os.environ.get("AWS_EXECUTION_ENV")   # only call STS inside Lambda
    else "shoptriage-transcribe-output-placeholder"
)

# demo_trigger (Day 5) mints the call_id itself and embeds it in the S3 key
# as "demo-<call_id>.mp3", so its API response can hand the caller a call_id
# to poll GET /calls/{id}/timeline immediately — before Transcribe even
# starts. Recognize that pattern and reuse the embedded id instead of
# minting a new one; any other filename still gets a fresh UUID4.
_DEMO_KEY_RE = re.compile(r"^demo-([0-9a-fA-F-]{36})\.mp3$")

# File extension -> Transcribe MediaFormat. Keep in sync with the per-suffix S3
# notification filters on VoicemailsBucket in template.yaml (S3 filters take one
# suffix each, so each extension here needs its own trigger there).
SUPPORTED_FORMATS = {
    ".mp3": "mp3",
    ".wav": "wav",
    ".m4a": "m4a",
}


def _media_format(key: str):
    """Return the Transcribe MediaFormat for an S3 key, or None if unsupported."""
    lowered = key.lower()
    for ext, media_format in SUPPORTED_FORMATS.items():
        if lowered.endswith(ext):
            return media_format
    return None


def handler(event: dict, context) -> dict:
    """Lambda entry point — called once per S3 ObjectCreated event."""
    logger.info("Event: %s", json.dumps(event))

    results = []
    for record in event.get("Records", []):
        try:
            result = _process_record(record)
            results.append(result)
        except Exception as exc:
            logger.exception("Failed to process record: %s", record)
            # Re-raise so Lambda marks the invocation as failed and we get
            # a CloudWatch alarm. Don't silently swallow intake errors.
            raise

    return {"processed": len(results), "call_ids": results}


def _process_record(record: dict) -> str:
    """Process one S3 event record. Returns the call_id."""

    # ── 1. Extract S3 coordinates ─────────────────────────────────────────
    bucket = record["s3"]["bucket"]["name"]
    # S3 URL-encodes the key (spaces → +, etc.) — decode it
    key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
    size_bytes = record["s3"]["object"].get("size", 0)

    logger.info("Processing s3://%s/%s (%d bytes)", bucket, key, size_bytes)

    # ── 2. Validate ────────────────────────────────────────────────────────
    media_format = _media_format(key)
    if media_format is None:
        logger.warning(
            "Ignoring unsupported file type: %s (supported: %s)",
            key, ", ".join(SUPPORTED_FORMATS),
        )
        return f"skipped:{key}"

    if size_bytes == 0:
        raise ValueError(f"Zero-byte file: {key}")

    # ── 3. Mint call_id (or reuse one embedded by demo_trigger) ────────────
    demo_match = _DEMO_KEY_RE.match(key)
    call_id = demo_match.group(1) if demo_match else str(uuid.uuid4())
    received_at = datetime.now(timezone.utc).isoformat()
    job_name = f"shoptriage-{call_id}"

    logger.info("call_id=%s  job_name=%s", call_id, job_name)

    # ── 4. Write initial call record to DynamoDB ──────────────────────────
    # status=new, received_at set now. process_transcript will overwrite
    # with the full classification fields once Claude responds.
    put_call_record(call_id, {
        "status": "new",
        "received_at": received_at,
        "s3_bucket": bucket,
        "s3_key": key,
        "transcribe_job": job_name,
        "file_size_bytes": size_bytes,
    })

    # ── 5. Timeline: uploaded ─────────────────────────────────────────────
    log_event(call_id, STAGE_UPLOADED, {
        "s3_bucket": bucket,
        "s3_key": key,
        "size_bytes": size_bytes,
    })

    # ── 6. Start Transcribe job ────────────────────────────────────────────
    # OutputBucketName: Transcribe will write a JSON file here when done.
    # Tags let us filter cost by project in Cost Explorer.
    # IdentifyLanguage=False + LanguageCode=en-US is faster and cheaper
    # than auto-detection for a single-language app.
    s3_uri = f"s3://{bucket}/{key}"

    # Determine output bucket — use env var if set, otherwise derive from account
    output_bucket = os.environ.get("TRANSCRIBE_OUTPUT_BUCKET")
    if not output_bucket:
        account_id = boto3.client("sts").get_caller_identity()["Account"]
        output_bucket = f"shoptriage-transcribe-output-{account_id}"

    TRANSCRIBE.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        MediaFormat=media_format,
        LanguageCode="en-US",
        OutputBucketName=output_bucket,
        OutputKey=f"transcripts/{call_id}.json",
        Tags=[{"Key": "project", "Value": "shoptriage"}],
        Settings={
            "ShowSpeakerLabels": False,
            "ChannelIdentification": False,
        },
    )

    logger.info("Transcribe job started: %s → s3://%s/transcripts/%s.json",
                job_name, output_bucket, call_id)

    # ── 7. Timeline: transcribing ─────────────────────────────────────────
    log_event(call_id, STAGE_TRANSCRIBING, {
        "job_name": job_name,
        "output_bucket": output_bucket,
    })

    return call_id
