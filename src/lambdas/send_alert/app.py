"""
send_alert
──────────
Invoked by the escalation Step Functions workflow via the
`arn:aws:states:::lambda:invoke.waitForTaskToken` integration. Every
invocation carries a Step Functions task token in the payload.

This function sends the SES email and returns immediately — it does NOT
call SendTaskSuccess itself. The workflow stays paused on this state until
GET /ack (escalation_ack Lambda) resumes it with that same token, or the
state's TimeoutSecondsPath (from the input's ack_window_seconds) elapses
and the workflow moves on to re-alert / mark overdue.

Payload (from the state machine):
  {call_id, role, category, urgency, summary, caller_name, callback_number,
   alert_stage: "primary" | "escalation", task_token}
"""

import logging
import os
import urllib.parse

import boto3

from shared.dynamo import update_call_status
from shared.timeline import log_event, STAGE_NOTIFIED, STAGE_ESCALATED

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))

FROM_EMAIL = os.environ["ALERT_FROM_EMAIL"]
ROLE_EMAILS = {
    "oncall": os.environ.get("ONCALL_EMAIL", FROM_EMAIL),
    "owner": os.environ.get("OWNER_EMAIL", FROM_EMAIL),
}
ACK_BASE_URL = os.environ["ACK_BASE_URL"]


def handler(event: dict, context) -> dict:
    call_id = event["call_id"]
    role = event.get("role", "owner")
    alert_stage = event.get("alert_stage", "primary")
    task_token = event["task_token"]

    # Record which task token is currently "live" for this call, so
    # escalation_ack can reject a token that doesn't belong to the call_id
    # in the query string (see Day 7 DEVLOG: a mismatched token/call_id pair
    # would otherwise resume the wrong workflow while marking the wrong call
    # acknowledged). Re-written on every alert stage, so an old link's token
    # stops matching as soon as a new one goes out.
    update_call_status(call_id, "routed", extra={"active_task_token": task_token})

    to_addr = ROLE_EMAILS.get(role, FROM_EMAIL)
    ack_link = (
        f"{ACK_BASE_URL}/ack"
        f"?token={urllib.parse.quote(task_token, safe='')}"
        f"&call_id={urllib.parse.quote(call_id)}"
    )

    subject_prefix = "RE-ALERT (escalated to owner) — " if alert_stage == "escalation" else ""
    subject = (
        f"{subject_prefix}ShopTriage: {event.get('category', 'call')} "
        f"({event.get('urgency', 'normal')}) needs a callback"
    )
    body = (
        f"Caller: {event.get('caller_name') or 'Unknown'}\n"
        f"Callback number: {event.get('callback_number') or 'Unknown'}\n"
        f"Category: {event.get('category')}   Urgency: {event.get('urgency')}\n\n"
        f"Summary: {event.get('summary') or ''}\n\n"
        f"Acknowledge this call: {ack_link}\n"
    )

    _ses.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": [to_addr]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )
    logger.info(
        "send_alert: call_id=%s role=%s stage=%s → %s",
        call_id, role, alert_stage, to_addr,
    )

    stage = STAGE_ESCALATED if alert_stage == "escalation" else STAGE_NOTIFIED
    log_event(call_id, stage, {"role": role, "email": to_addr})

    return {"status": "sent", "call_id": call_id, "role": role}
