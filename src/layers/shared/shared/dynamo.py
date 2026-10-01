"""
shared.dynamo
─────────────
DynamoDB helpers for the ShopTriage single table.

Table key design (recap):
  PK = CALL#<call_id>   SK = META                   → call record
  PK = CALL#<call_id>   SK = EVENT#<iso_ts>#<stage>  → timeline entry
  PK = INBOX#<role>     SK = <iso_ts>#<call_id>      → staff inbox row

TTL is always set RETENTION_DAYS (default 60) days from now. DynamoDB will garbage-collect
demo data automatically with no Lambda needed.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

_TABLE_NAME = os.environ.get("DYNAMO_TABLE", "shoptriage")
_TTL_DAYS = int(os.environ.get("RETENTION_DAYS", "60"))   # one setting: RETENTION_DAYS in template.yaml
_resource = None


def _table():
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _resource.Table(_TABLE_NAME)


def _ttl() -> int:
    """Unix timestamp RETENTION_DAYS days from now."""
    return int(time.time()) + _TTL_DAYS * 86400


def put_call_record(call_id: str, item: dict[str, Any]) -> None:
    """
    Write (or overwrite) the META item for a call.
    call_id and all classification fields go here.
    """
    record = {
        "PK": f"CALL#{call_id}",
        "SK": "META",
        "call_id": call_id,
        "ttl": _ttl(),
        **item,
    }
    _table().put_item(Item=record)
    logger.info("put_call_record: CALL#%s META written", call_id)


def update_call_status(call_id: str, status: str, extra: dict[str, Any] | None = None) -> None:
    """Update only the status (and optional extra fields) on an existing call record."""
    update_expr = "SET #st = :s, updated_at = :u"
    expr_values: dict = {":s": status, ":u": datetime.now(timezone.utc).isoformat()}
    expr_names: dict = {"#st": "status"}   # 'status' is reserved in DynamoDB

    if extra:
        for k, v in extra.items():
            placeholder = f":{k}"
            update_expr += f", {k} = {placeholder}"
            expr_values[placeholder] = v

    _table().update_item(
        Key={"PK": f"CALL#{call_id}", "SK": "META"},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
        ExpressionAttributeNames=expr_names,
    )
    logger.info("update_call_status: CALL#%s → %s", call_id, status)


# Per-outcome counters kept next to the total, so the board can show
# "2 reached, 1 no answer" instead of one lumped number.
_OUTCOME_COUNTERS = {"reached": "reached_count", "no_answer": "no_answer_count"}


def record_attempt(call_id: str, outcome: str) -> int:
    """
    Atomically bump attempt_count and the counter for this outcome, and stamp
    last_attempt_at. Returns the new total. Deliberately does not touch status
    or updated_at: an attempt keeps the call open, only Resolve closes it.
    """
    counter = _OUTCOME_COUNTERS[outcome]   # KeyError on an unknown outcome is a bug, not input
    resp = _table().update_item(
        Key={"PK": f"CALL#{call_id}", "SK": "META"},
        UpdateExpression="ADD attempt_count :one, #oc :one SET last_attempt_at = :now",
        ExpressionAttributeNames={"#oc": counter},
        ExpressionAttributeValues={
            ":one": 1,
            ":now": datetime.now(timezone.utc).isoformat(),
        },
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["attempt_count"])


def get_call(call_id: str) -> dict | None:
    """Fetch the META record for a call. Returns None if not found."""
    resp = _table().get_item(Key={"PK": f"CALL#{call_id}", "SK": "META"})
    return resp.get("Item")


def query_by_status(status: str, limit: int = 50) -> list[dict]:
    """
    Return up to `limit` calls with the given status, newest first.
    Uses GSI1 (PK=status, SK=received_at) — no scan.
    """
    resp = _table().query(
        IndexName="GSI1",
        KeyConditionExpression=Key("status").eq(status),
        ScanIndexForward=False,  # newest first
        Limit=limit,
    )
    return resp.get("Items", [])


def query_all_by_status(status: str, max_items: int = 500) -> list[dict]:
    """
    Return up to `max_items` calls with the given status, following pagination.
    Same GSI1 query as query_by_status (no Scan); used by the dashboard stats,
    which need every call rather than just the newest page.
    """
    items: list[dict] = []
    kwargs = {
        "IndexName": "GSI1",
        "KeyConditionExpression": Key("status").eq(status),
        "ScanIndexForward": False,
    }
    while len(items) < max_items:
        resp = _table().query(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items[:max_items]


def query_inbox(role: str, limit: int = 50) -> list[dict]:
    """
    Return up to `limit` staff inbox rows for a role, newest first.
    PK = INBOX#<role> — a direct query on the base table, no index needed.
    """
    resp = _table().query(
        KeyConditionExpression=Key("PK").eq(f"INBOX#{role}"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return resp.get("Items", [])


def increment_daily_counter(name: str, cap: int) -> bool:
    """
    Atomically increment a daily counter capped at `cap`.
    PK = COUNTER#<name>  SK = <YYYY-MM-DD>

    Returns True if the increment succeeded (still under cap that day),
    False if the cap was already reached. The conditional UpdateItem is
    the atomic part — DynamoDB rejects the write if call_count is already
    at cap, so concurrent requests can't both slip through.

    Used to protect the public /demo/calls endpoint from cost runaway
    without needing an API Gateway usage plan.
    """
    from botocore.exceptions import ClientError

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        _table().update_item(
            Key={"PK": f"COUNTER#{name}", "SK": today},
            UpdateExpression="SET call_count = if_not_exists(call_count, :zero) + :incr, #ttl = :ttl",
            ConditionExpression="attribute_not_exists(call_count) OR call_count < :cap",
            ExpressionAttributeNames={"#ttl": "ttl"},   # 'ttl' is a reserved keyword in DynamoDB
            ExpressionAttributeValues={
                ":zero": 0,
                ":incr": 1,
                ":cap": cap,
                ":ttl": _ttl(),
            },
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
