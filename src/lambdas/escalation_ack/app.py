"""
escalation_ack
──────────────
GET /ack?token=...&call_id=...

0. Verifies the token matches the call's currently-active task token (written
   by send_alert on every alert stage) before doing anything else. This stops
   a tampered call_id/token pair from resuming the wrong call's workflow.
1. Calls Step Functions SendTaskSuccess with the token — this resumes the
   paused Notify* state in the escalation workflow, so it stops waiting and
   never re-alerts or marks the call overdue.
2. Marks the call acknowledged in DynamoDB directly (status=acknowledged,
   acknowledged_at=now) and writes an "acknowledged" timeline event. The
   workflow's success path doesn't touch DynamoDB itself, so this Lambda is
   the single place that records the ack.

A stale or already-used link raises TaskTimedOut or TaskDoesNotExist from
SendTaskSuccess — both are treated as "nothing left to do" rather than an
error, so clicking an old link twice doesn't show a scary 500 page.
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from shared.dynamo import get_call, update_call_status
from shared.timeline import log_event, STAGE_ACKNOWLEDGED

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_sfn = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION", "us-east-1"))

_PAGE = """<!doctype html><html><body style="font-family:sans-serif;padding:2rem">
<h2>{title}</h2><p>{message}</p></body></html>"""


def _response(status: int, title: str, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "text/html"},
        "body": _PAGE.format(title=title, message=message),
    }


def handler(event: dict, context) -> dict:
    qs = event.get("queryStringParameters") or {}
    token = qs.get("token")
    call_id = qs.get("call_id")

    if not token or not call_id:
        return _response(400, "Missing parameters", "This acknowledge link is malformed.")

    # Verify the token actually belongs to this call_id before trusting either.
    # Without this, a token for call B combined with call A's call_id would
    # resume B's real workflow (silently killing its escalation) while marking
    # the unrelated call A as acknowledged — confirmed live during Day 7 testing.
    call = get_call(call_id)
    if not call:
        return _response(404, "Call not found", "No call matches this acknowledge link.")
    if call.get("active_task_token") != token:
        logger.warning("escalation_ack: token/call_id mismatch for call_id=%s", call_id)
        return _response(
            400, "Link mismatch",
            "This acknowledge link doesn't match this call. It may be stale or altered.",
        )

    try:
        _sfn.send_task_success(taskToken=token, output=json.dumps({"acknowledged": True}))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("TaskTimedOut", "TaskDoesNotExist"):
            logger.warning(
                "send_task_success: token already resolved for call_id=%s (%s)",
                call_id, code,
            )
            return _response(
                200, "Already handled",
                "This call was already acknowledged, or the alert already escalated.",
            )
        logger.exception("send_task_success failed for call_id=%s", call_id)
        return _response(500, "Error", "Could not acknowledge this call. Please call the shop directly.")

    try:
        update_call_status(call_id, "acknowledged", extra={
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        })
        log_event(call_id, STAGE_ACKNOWLEDGED)
    except ClientError:
        logger.exception("DynamoDB update failed for call_id=%s (workflow already resumed)", call_id)

    logger.info("escalation_ack: call_id=%s acknowledged", call_id)
    return _response(200, "Acknowledged", f"Call {call_id} marked as acknowledged. You can close this window.")
