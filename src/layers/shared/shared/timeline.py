"""
shared.timeline
───────────────
Timeline event logger for the ShopTriage demo console.

Every stage of the pipeline writes one EVENT item to DynamoDB.
The frontend polls GET /calls/{id}/timeline and shows these events
as a live stage-by-stage log.

SK format: EVENT#<iso_ts>#<stage>
  - The iso_ts in the SK ensures uniqueness even if two stages fire
    in the same second.
  - Lexicographic sort on SK gives chronological order for free.
"""

import logging
import os
import time
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)

_TABLE_NAME = os.environ.get("DYNAMO_TABLE", "shoptriage")
_TTL_DAYS = 7
_resource = None


def _table():
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _resource.Table(_TABLE_NAME)


def _ttl() -> int:
    return int(time.time()) + _TTL_DAYS * 86400


# Valid stage names — the frontend maps these to badge labels and icons.
STAGE_UPLOADED      = "uploaded"
STAGE_TRANSCRIBING  = "transcribing"
STAGE_CLASSIFIED    = "classified"
STAGE_ROUTED        = "routed"
STAGE_NOTIFIED      = "notified"
STAGE_ACKNOWLEDGED  = "acknowledged"
STAGE_ESCALATED     = "escalated"
STAGE_SUMMARY_FAILED = "summary_failed"
STAGE_CALLED_BACK   = "called_back"
STAGE_RESOLVED      = "resolved"
STAGE_NOTE          = "note"
STAGE_ATTEMPT       = "attempt"


def log_event(call_id: str, stage: str, detail: dict | None = None) -> None:
    """
    Append a timeline event for call_id.

    Parameters
    ----------
    call_id : str
        The call identifier (without the CALL# prefix).
    stage : str
        One of the STAGE_* constants above.
    detail : dict, optional
        Any extra context to store (e.g. job_name, category, urgency).
    """
    now = datetime.now(timezone.utc).isoformat()
    sk = f"EVENT#{now}#{stage}"

    item = {
        "PK": f"CALL#{call_id}",
        "SK": sk,
        "call_id": call_id,
        "stage": stage,
        "ts": now,
        "ttl": _ttl(),
    }
    if detail:
        item["detail"] = detail

    _table().put_item(Item=item)
    logger.info("timeline: CALL#%s stage=%s", call_id, stage)


def get_timeline(call_id: str) -> list[dict]:
    """
    Return all timeline events for a call, in chronological order.
    Used by the API handler for GET /calls/{id}/timeline.
    """
    from boto3.dynamodb.conditions import Key

    resp = _table().query(
        KeyConditionExpression=(
            Key("PK").eq(f"CALL#{call_id}") & Key("SK").begins_with("EVENT#")
        ),
        ScanIndexForward=True,
    )
    return resp.get("Items", [])
