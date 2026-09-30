"""
process_transcript
──────────────────
Triggered by EventBridge when an Amazon Transcribe job with name
prefix "shoptriage-" transitions to COMPLETED.

Flow:
  1. Extract call_id from the Transcribe job name
  2. Fetch the transcript JSON from S3
  3. Flatten the transcript text
  4. Send to Claude for classification (strict JSON output)
  5. Validate the Claude response
  6. Write the full call record to DynamoDB (status=new → routed)
  7. Write timeline event: stage=classified
  8. Publish CallTriaged event to the custom EventBridge bus
  9. Write timeline event: stage=routed

Fallback (if Claude fails):
  - Write transcript text to DynamoDB anyway
  - Set status=needs_review
  - Write timeline event: stage=summary_failed
  - Still publish CallTriaged with needs_review category so routing
    can handle it without losing the call

EventBridge event shape (from aws.transcribe):
{
  "source": "aws.transcribe",
  "detail-type": "Transcribe Job State Change",
  "detail": {
    "TranscriptionJobName": "shoptriage-<uuid>",
    "TranscriptionJobStatus": "COMPLETED",
    "Transcript": { "TranscriptFileUri": "s3://..." }
  }
}
"""

import json
import logging
import os
import urllib.parse
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from shared.claude_client import classify_transcript
from shared.dynamo import put_call_record, update_call_status
from shared.timeline import (
    log_event,
    STAGE_CLASSIFIED,
    STAGE_ROUTED,
    STAGE_SUMMARY_FAILED,
)

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

S3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
EVENTS = boto3.client("events", region_name=os.environ.get("AWS_REGION", "us-east-1"))

TRANSCRIBE_OUTPUT_BUCKET = os.environ.get("TRANSCRIBE_OUTPUT_BUCKET", "")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "shop-triage-bus")
DYNAMO_TABLE = os.environ.get("DYNAMO_TABLE", "shoptriage")

# TTL for demo data: 7 days
TTL_DAYS = 7


def handler(event: dict, context) -> dict:
    """Lambda entry point — called by EventBridge on Transcribe COMPLETED."""
    logger.info("Event: %s", json.dumps(event))

    detail = event.get("detail", {})
    job_name = detail.get("TranscriptionJobName", "")
    job_status = detail.get("TranscriptionJobStatus", "")

    # Guard: only process COMPLETED jobs with our prefix
    # (The EventBridge rule already filters this, but defence-in-depth)
    if job_status != "COMPLETED":
        logger.warning("Ignoring non-COMPLETED status: %s", job_status)
        return {"status": "skipped", "reason": "not COMPLETED"}

    if not job_name.startswith("shoptriage-"):
        logger.warning("Ignoring job with unexpected name: %s", job_name)
        return {"status": "skipped", "reason": "unexpected job name"}

    # Extract call_id from job name: "shoptriage-<uuid>" → "<uuid>"
    call_id = job_name[len("shoptriage-"):]
    logger.info("Processing call_id=%s  job=%s", call_id, job_name)

    # ── Step 1: Fetch transcript from S3 ─────────────────────────────────
    transcript_text = _fetch_transcript(call_id)
    if not transcript_text:
        logger.error("Empty transcript for call_id=%s", call_id)
        _handle_failure(call_id, "Empty transcript text", transcript_text="")
        return {"status": "error", "call_id": call_id, "reason": "empty_transcript"}

    logger.info("Transcript (%d chars): %.300s …", len(transcript_text), transcript_text)

    # ── Step 2: Classify with Claude ─────────────────────────────────────
    classification = None
    classification_error = None

    try:
        classification = classify_transcript(transcript_text)
        logger.info("Classification: %s", json.dumps(classification))
    except Exception as exc:
        classification_error = str(exc)
        logger.exception("Claude classification failed: %s", exc)

    if classification is None:
        _handle_failure(call_id, classification_error, transcript_text)
        return {"status": "needs_review", "call_id": call_id}

    # ── Step 3: Write full call record to DynamoDB ────────────────────────
    received_at = datetime.now(timezone.utc).isoformat()

    import time
    ttl = int(time.time()) + TTL_DAYS * 86400

    call_record = {
        "status": "new",
        "received_at": received_at,
        "transcript": transcript_text,
        "transcribe_job": job_name,
        # Classification fields
        "category": classification["category"],
        "urgency": classification["urgency"],
        "is_comeback": classification["is_comeback"],
        "caller_name": classification.get("caller_name"),
        "callback_number": classification.get("callback_number"),
        "vehicle": classification.get("vehicle"),
        "summary": classification["summary"],
        "action_items": classification.get("action_items", []),
        "ttl": ttl,
    }

    # put_call_record does a full overwrite of the META item — this is
    # intentional. start_transcription wrote a minimal stub; now we replace
    # it with the full record. DynamoDB conditional writes aren't needed here
    # because only this function writes the full record (no race condition).
    put_call_record(call_id, call_record)

    # ── Step 4: Timeline — classified ─────────────────────────────────────
    log_event(call_id, STAGE_CLASSIFIED, {
        "category": classification["category"],
        "urgency": classification["urgency"],
        "is_comeback": classification["is_comeback"],
        "summary": classification["summary"],
    })

    # ── Step 5: Publish CallTriaged to custom EventBridge bus ─────────────
    _publish_call_triaged(call_id, call_record)

    # ── Step 6: Timeline — routed ─────────────────────────────────────────
    log_event(call_id, STAGE_ROUTED, {"event_bus": EVENT_BUS_NAME})

    return {
        "status": "ok",
        "call_id": call_id,
        "category": classification["category"],
        "urgency": classification["urgency"],
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _fetch_transcript(call_id: str) -> str:
    """
    Download the Transcribe output JSON from S3 and return the flattened
    transcript text.

    Transcribe output structure:
    {
      "results": {
        "transcripts": [{"transcript": "full text here"}],
        ...
      }
    }
    We use the top-level transcript string rather than word-by-word items
    because Claude needs readable prose, not a token list.
    """
    key = f"transcripts/{call_id}.json"
    bucket = TRANSCRIBE_OUTPUT_BUCKET

    try:
        response = S3.get_object(Bucket=bucket, Key=key)
        body = json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as exc:
        logger.error("Failed to fetch transcript s3://%s/%s: %s", bucket, key, exc)
        return ""
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in transcript s3://%s/%s: %s", bucket, key, exc)
        return ""

    transcripts = body.get("results", {}).get("transcripts", [])
    if not transcripts:
        return ""

    return transcripts[0].get("transcript", "").strip()


def _handle_failure(call_id: str, error_msg: str | None, transcript_text: str) -> None:
    """
    Fallback path when Claude fails or transcript is empty.
    Writes/updates the call record with status=needs_review and
    logs the summary_failed timeline event.
    """
    import time
    ttl = int(time.time()) + TTL_DAYS * 86400
    received_at = datetime.now(timezone.utc).isoformat()

    put_call_record(call_id, {
        "status": "needs_review",
        "received_at": received_at,
        "transcript": transcript_text,
        "classification_error": error_msg or "unknown",
        # Provide safe defaults so routing rules don't crash on missing keys
        "category": "spam_other",
        "urgency": "high",       # escalate unknown — better to over-alert
        "is_comeback": False,
        "summary": "Classification failed — manual review required.",
        "action_items": ["Review voicemail manually"],
        "ttl": ttl,
    })

    log_event(call_id, STAGE_SUMMARY_FAILED, {
        "error": error_msg or "unknown",
        "has_transcript": bool(transcript_text),
    })

    # Still publish so routing/Day 3 can handle needs_review calls
    _publish_call_triaged(call_id, {
        "status": "needs_review",
        "category": "spam_other",
        "urgency": "high",
        "is_comeback": False,
    })


def _publish_call_triaged(call_id: str, call_record: dict) -> None:
    """
    Publish a CallTriaged event to the custom EventBridge bus.

    If the bus doesn't exist yet (Day 3 creates it), we log a warning
    instead of failing — the call record is already safe in DynamoDB.
    """
    event_detail = {
        "call_id": call_id,
        "category": call_record.get("category"),
        "urgency": call_record.get("urgency"),
        "is_comeback": call_record.get("is_comeback", False),
        "status": call_record.get("status", "new"),
        "caller_name": call_record.get("caller_name"),
        "callback_number": call_record.get("callback_number"),
        "vehicle": call_record.get("vehicle"),
        "summary": call_record.get("summary"),
    }

    try:
        resp = EVENTS.put_events(
            Entries=[
                {
                    "Source": "autoshop.triage",
                    "DetailType": "CallTriaged",
                    "Detail": json.dumps(event_detail),
                    "EventBusName": EVENT_BUS_NAME,
                }
            ]
        )
        failed = resp.get("FailedEntryCount", 0)
        if failed:
            logger.error("EventBridge PutEvents failed: %s", resp["Entries"])
        else:
            logger.info("CallTriaged event published for call_id=%s", call_id)

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            # Expected until Day 3 creates the custom bus
            logger.warning(
                "Custom bus '%s' not found — event not published. "
                "Call record is safe in DynamoDB. (Will work after Day 3 deploy.)",
                EVENT_BUS_NAME,
            )
        else:
            # Unexpected error — log but don't fail the Lambda invocation.
            # The call record is already written; losing the event is recoverable
            # once the EventBridge archive (Day 3) is set up for replay.
            logger.exception(
                "Unexpected EventBridge error for call_id=%s: %s", call_id, exc
            )
