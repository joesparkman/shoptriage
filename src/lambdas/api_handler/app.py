"""
api_handler
───────────
Serves the read/write routes on ShopTriageApi (HTTP API, payload format 2.0):
  GET  /calls?status=...      → calls in one status, or status=open for every open call
                                 (GSI1 queries via shared.dynamo, no Scan)
  GET  /calls/{id}/timeline   → stage-by-stage timeline events for one call
  GET  /inbox/{role}          → staff inbox rows for one role
  POST /calls/{id}/status     → mark called_back or resolved
  POST /calls/{id}/notes      → append a note to the call's timeline
  POST /calls/{id}/attempts   → log a callback attempt (call stays open)
  GET  /stats                 → dashboard aggregates (one GSI1 query per status, no Scan)

Each route is registered as its own HttpApi event in template.yaml, all
pointing at this one function; routeKey dispatches inside the handler
rather than separate Lambdas, since none of these need different
IAM permissions from each other.
"""

import json
import logging
import os
from decimal import Decimal

from shared.dynamo import (
    query_by_status,
    query_all_by_status,
    get_call,
    update_call_status,
    record_attempt,
    query_inbox,
)
from shared.timeline import (
    get_timeline,
    log_event,
    STAGE_CALLED_BACK,
    STAGE_RESOLVED,
    STAGE_NOTE,
    STAGE_ATTEMPT,
)
from notes import parse_note, parse_attempt, MAX_EVENTS_PER_CALL
from stats import compute_stats, OPEN_STATUSES, CLOSED_STATUSES

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

ALLOWED_STATUSES = {"called_back", "resolved"}


class _DecimalEncoder(json.JSONEncoder):
    """DynamoDB returns numbers as Decimal; json.dumps can't serialize those natively."""

    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _json(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, cls=_DecimalEncoder),
    }


def handler(event: dict, context) -> dict:
    route_key = event.get("routeKey", "")
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}

    logger.info("routeKey=%s", route_key)

    try:
        if route_key == "GET /calls":
            return _list_calls(query_params)
        if route_key == "GET /calls/{id}/timeline":
            return _get_timeline(path_params.get("id"))
        if route_key == "GET /stats":
            return _get_stats()
        if route_key == "GET /inbox/{role}":
            return _get_inbox(path_params.get("role"))
        if route_key == "POST /calls/{id}/status":
            return _update_status(path_params.get("id"), event.get("body"))
        if route_key == "POST /calls/{id}/notes":
            return _add_history(path_params.get("id"), event.get("body"), parse_note, STAGE_NOTE)
        if route_key == "POST /calls/{id}/attempts":
            return _add_history(path_params.get("id"), event.get("body"), parse_attempt, STAGE_ATTEMPT)
    except Exception:
        logger.exception("Unhandled error for routeKey=%s", route_key)
        return _json(500, {"error": "internal_error"})

    return _json(404, {"error": "not_found"})


def _list_calls(query_params: dict) -> dict:
    status = query_params.get("status")
    if not status:
        return _json(400, {"error": "status query parameter is required"})
    if status == "open":
        # One request for the whole callback board. The board used to send one
        # request per status, which alone could exceed the API's 2 rps / burst 5
        # throttle (5 requests per poll, plus 5 more after every action).
        calls = []
        for open_status in sorted(OPEN_STATUSES):
            calls.extend(query_by_status(open_status))
        calls.sort(key=lambda c: c.get("received_at") or "", reverse=True)
        return _json(200, {"calls": calls})
    return _json(200, {"calls": query_by_status(status)})


def _get_stats() -> dict:
    calls = []
    for status in sorted(OPEN_STATUSES | CLOSED_STATUSES):
        calls.extend(query_all_by_status(status))
    return _json(200, compute_stats(calls))


def _get_timeline(call_id) -> dict:
    if not call_id:
        return _json(400, {"error": "missing call id"})
    if not get_call(call_id):
        return _json(404, {"error": "call not found"})
    return _json(200, {"call_id": call_id, "events": get_timeline(call_id)})


def _get_inbox(role) -> dict:
    if not role:
        return _json(400, {"error": "missing role"})
    return _json(200, {"role": role, "items": query_inbox(role)})


def _update_status(call_id, body) -> dict:
    if not call_id:
        return _json(400, {"error": "missing call id"})

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON body"})

    new_status = payload.get("status")
    if new_status not in ALLOWED_STATUSES:
        return _json(400, {"error": "status must be called_back or resolved"})

    if not get_call(call_id):
        return _json(404, {"error": "call not found"})

    update_call_status(call_id, new_status)
    log_event(call_id, STAGE_CALLED_BACK if new_status == "called_back" else STAGE_RESOLVED)

    return _json(200, {"call_id": call_id, "status": new_status})


def _add_history(call_id, body, parse, stage) -> dict:
    """Shared write path for notes and attempts: validate, cap, then log to the timeline."""
    if not call_id:
        return _json(400, {"error": "missing call id"})

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON body"})

    detail, error = parse(payload)
    if error:
        return _json(400, {"error": error})

    if not get_call(call_id):
        return _json(404, {"error": "call not found"})

    if len(get_timeline(call_id)) >= MAX_EVENTS_PER_CALL:
        return _json(429, {"error": "this call has reached its history limit"})

    result = {"call_id": call_id}
    if stage == STAGE_ATTEMPT:
        result["attempt_count"] = record_attempt(call_id, detail["outcome"])
        detail["attempt_number"] = result["attempt_count"]

    log_event(call_id, stage, detail)
    return _json(201, result)
