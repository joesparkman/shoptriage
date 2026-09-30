"""
routing_dispatcher
──────────────────
Triggered by EventBridge rule(s) on the custom bus 'shop-triage-bus'
for every CallTriaged event (source=autoshop.triage, detail-type=CallTriaged).

What this Lambda does:
  1. Reads the classification from the event detail
  2. Determines the routing decision (which channel this call goes to)
  3. Updates the DynamoDB call record: status → "routed", assigns routing_channel
  4. Writes a STAGE_ROUTED timeline event with the routing decision

What this Lambda does NOT do:
  - Publish to SNS or SQS directly — that's handled by the EventBridge rules
    (RouteEmergencyRule, RouteComebackRule, RouteFrontOfficeRule, etc.).
    The rules and this Lambda fire independently from the same bus event.
  - Start the Step Functions escalation workflow — that's Day 4.

Why have a Lambda at all if the rules do the fan-out?
  EventBridge rules can target SNS/SQS but can't update DynamoDB or write
  timeline events. This Lambda handles the application state side: marking
  the call as routed, recording which channel, and appending the timeline
  entry that the demo console shows in real time.

EventBridge event shape (detail field):
  {
    "call_id": "<uuid>",
    "category": "comeback" | "breakdown_tow" | "repair_status" | ...,
    "urgency":  "emergency" | "high" | "normal" | "low",
    "is_comeback": true | false,
    "status": "new" | "needs_review",
    "caller_name": "...",
    "callback_number": "...",
    "vehicle": "...",
    "summary": "..."
  }
"""

import json
import logging
import os
import uuid

import boto3
from botocore.exceptions import ClientError

from shared.dynamo import update_call_status
from shared.timeline import log_event, STAGE_ROUTED

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_sfn = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION", "us-east-1"))

# ── Environment variables injected by SAM template ───────────────────────────
ONCALL_TOPIC_ARN      = os.environ.get("ONCALL_TOPIC_ARN", "")
OWNER_TOPIC_ARN       = os.environ.get("OWNER_TOPIC_ARN", "")
FRONT_OFFICE_QUEUE_URL = os.environ.get("FRONT_OFFICE_QUEUE_URL", "")
VENDOR_QUEUE_URL      = os.environ.get("VENDOR_QUEUE_URL", "")
DYNAMO_TABLE          = os.environ.get("DYNAMO_TABLE", "shoptriage")
STATE_MACHINE_ARN     = os.environ.get("STATE_MACHINE_ARN", "")

# Ack-window timeouts (seconds). Demo mode uses short windows so escalation
# is watchable live instead of waiting the real 15min / 2hr windows.
EMERGENCY_ACK_SECONDS    = int(os.environ.get("EMERGENCY_ACK_SECONDS", "60"))
COMEBACK_ACK_SECONDS     = int(os.environ.get("COMEBACK_ACK_SECONDS", "90"))
NEEDS_REVIEW_ACK_SECONDS = int(os.environ.get("NEEDS_REVIEW_ACK_SECONDS", "90"))

# Front-office categories that go to the front-office queue
FRONT_OFFICE_CATEGORIES = frozenset({
    "repair_status", "scheduling", "billing", "estimate"
})


def handler(event: dict, context) -> dict:
    """
    Lambda entry point — called by EventBridge with a CallTriaged event.

    EventBridge wraps our published detail in the standard envelope:
      event["source"]      == "autoshop.triage"
      event["detail-type"] == "CallTriaged"
      event["detail"]      == { ... our fields ... }
    """
    logger.info("Received event: %s", json.dumps(event))

    detail = event.get("detail", {})
    call_id = detail.get("call_id")

    if not call_id:
        logger.error("Missing call_id in event detail — skipping")
        return {"status": "error", "reason": "missing_call_id"}

    category   = detail.get("category", "spam_other")
    urgency    = detail.get("urgency", "normal")
    is_comeback = detail.get("is_comeback", False)
    status     = detail.get("status", "new")

    # ── Determine routing channel ─────────────────────────────────────────
    # This mirrors exactly what the EventBridge rules do, so the DynamoDB
    # record always reflects what actually happened on the bus.
    routing_channel = _determine_channel(category, urgency, is_comeback, status)
    logger.info(
        "call_id=%s  category=%s  urgency=%s  is_comeback=%s  → channel=%s",
        call_id, category, urgency, is_comeback, routing_channel,
    )

    # ── Update DynamoDB: status=routed + routing_channel ──────────────────
    # We use UpdateItem (via update_call_status) rather than overwriting the
    # whole record — process_transcript already wrote all the classification
    # fields and we don't want to clobber them.
    try:
        update_call_status(call_id, "routed", extra={
            "routing_channel": routing_channel,
        })
        logger.info("DynamoDB updated: call_id=%s  status=routed  channel=%s",
                    call_id, routing_channel)
    except ClientError as exc:
        # Don't fail the invocation — routing already happened via EventBridge
        # rules. Losing the status update is recoverable; losing the SNS/SQS
        # delivery is not.
        logger.exception("DynamoDB update failed for call_id=%s: %s", call_id, exc)

    # ── Write STAGE_ROUTED timeline event ─────────────────────────────────
    try:
        log_event(call_id, STAGE_ROUTED, {
            "routing_channel": routing_channel,
            "category": category,
            "urgency": urgency,
            "is_comeback": is_comeback,
        })
    except ClientError as exc:
        logger.exception("Timeline write failed for call_id=%s: %s", call_id, exc)

    # ── Start the escalation workflow for the three paths that need a human
    #    to acknowledge: emergency, comeback, and needs_review ──────────────
    primary_role, ack_window_seconds = _escalation_params(category, urgency, is_comeback, status)
    if primary_role:
        _start_escalation(
            call_id, category, urgency, is_comeback, status, detail,
            primary_role, ack_window_seconds,
        )

    return {
        "status": "ok",
        "call_id": call_id,
        "routing_channel": routing_channel,
    }


# ── Routing logic ─────────────────────────────────────────────────────────────

def _determine_channel(category: str, urgency: str, is_comeback: bool, status: str = "") -> str:
    """
    Return a human-readable routing channel string that mirrors the
    EventBridge rule set.

    Priority order (same as the rules):
      1. status=needs_review        → owner_alerts  (unclassified: must reach a person)
      2. urgency=emergency          → oncall_and_owner
      3. is_comeback AND non-emergency → owner_alerts
      4. front-office categories    → front_office_queue
      5. parts_vendor               → vendor_queue
      6. everything else (spam_other, breakdown_tow non-emergency, unknown) → logged_only

    NOTE: needs_review is checked first so a Claude failure always pages the owner,
    regardless of whatever partial urgency/category may have been set.
    """
    # Mirrors RouteNeedsReviewRule — unclassified calls must reach a person
    if status == "needs_review":
        return "owner_alerts"

    if urgency == "emergency":
        return "oncall_and_owner"

    if is_comeback:
        return "owner_alerts"

    if category in FRONT_OFFICE_CATEGORIES:
        return "front_office_queue"

    if category == "parts_vendor":
        return "vendor_queue"

    # spam_other, breakdown_tow (non-emergency), unknown categories
    return "logged_only"


def _escalation_params(category: str, urgency: str, is_comeback: bool, status: str):
    """
    Decide whether this call needs the Step Functions escalation workflow,
    and if so, who gets notified first and how long they have to acknowledge.

    Only three paths escalate — a call that only reaches the front-office or
    vendor queue is fine to sit until someone checks the queue manually.
    Returns (primary_role, ack_window_seconds) or (None, None) if no
    escalation is needed.
    """
    if status == "needs_review":
        return "owner", NEEDS_REVIEW_ACK_SECONDS
    if urgency == "emergency":
        return "oncall", EMERGENCY_ACK_SECONDS
    if is_comeback:
        return "owner", COMEBACK_ACK_SECONDS
    return None, None


def _start_escalation(call_id, category, urgency, is_comeback, status, detail,
                       primary_role, ack_window_seconds) -> None:
    """Start one Step Functions execution of the escalation workflow."""
    if not STATE_MACHINE_ARN:
        logger.warning("STATE_MACHINE_ARN not set — skipping escalation for call_id=%s", call_id)
        return

    execution_input = {
        "call_id": call_id,
        "category": category,
        "urgency": urgency,
        "is_comeback": is_comeback,
        "status": status,
        "caller_name": detail.get("caller_name"),
        "callback_number": detail.get("callback_number"),
        "summary": detail.get("summary"),
        "primary_role": primary_role,
        "escalation_role": "owner",
        "ack_window_seconds": ack_window_seconds,
    }
    # Execution names must be unique per state machine; call_id alone isn't
    # enough if a call is ever re-triaged (e.g. via archive replay).
    execution_name = f"escalation-{call_id}-{uuid.uuid4().hex[:8]}"[:80]

    try:
        _sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=execution_name,
            input=json.dumps(execution_input),
        )
        logger.info(
            "Escalation started: call_id=%s primary_role=%s ack_window=%ss",
            call_id, primary_role, ack_window_seconds,
        )
    except ClientError as exc:
        logger.exception("Failed to start escalation for call_id=%s: %s", call_id, exc)
