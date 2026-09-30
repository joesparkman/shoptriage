"""
inbox_writer
────────────
Invoked directly (plain Lambda Task, no waitForTaskToken) by the escalation
Step Functions workflow every time an alert goes out — once for the primary
role, again if it escalates. Writes one row per alert so the staff inbox
panel (Day 5 frontend) can list pending alerts per role.

DynamoDB key: PK = INBOX#<role>   SK = <iso_ts>#<call_id>
"""

import logging
import os
import time
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_TABLE_NAME = os.environ.get("DYNAMO_TABLE", "shoptriage")
_TTL_DAYS = 7
_dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def handler(event: dict, context) -> dict:
    call_id = event["call_id"]
    role = event.get("role", "owner")
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "PK": f"INBOX#{role}",
        "SK": f"{now}#{call_id}",
        "call_id": call_id,
        "role": role,
        "category": event.get("category"),
        "urgency": event.get("urgency"),
        "summary": event.get("summary"),
        "caller_name": event.get("caller_name"),
        "callback_number": event.get("callback_number"),
        "alert_stage": event.get("alert_stage", "primary"),
        "created_at": now,
        "ttl": int(time.time()) + _TTL_DAYS * 86400,
    }

    _dynamodb.Table(_TABLE_NAME).put_item(Item=item)
    logger.info(
        "inbox_writer: INBOX#%s written for call_id=%s stage=%s",
        role, call_id, item["alert_stage"],
    )

    return {"status": "ok"}
