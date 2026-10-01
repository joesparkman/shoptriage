"""
stats
─────
Pure aggregation for GET /stats. Takes the call records already fetched from
GSI1 and returns the numbers the dashboard shows. No AWS calls in here, so it
can be unit-tested with plain dicts.

Every number is derived from real call records. Nothing is estimated:
  - "open" means the same statuses the callback board treats as open
  - avg_close_minutes is received_at → updated_at for calls now marked
    called_back or resolved (updated_at is when that status was set)
  - the window is whatever the table still holds (the RETENTION_DAYS setting)
"""

from datetime import datetime, timedelta, timezone

OPEN_STATUSES = {"new", "needs_review", "routed", "acknowledged", "overdue"}
CLOSED_STATUSES = {"called_back", "resolved"}
# An emergency that nobody has acknowledged yet.
UNACKED_STATUSES = {"new", "needs_review", "routed", "overdue"}

RECENT_LIMIT = 8


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_stats(calls: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)

    by_status: dict[str, int] = {}
    by_urgency: dict[str, int] = {}
    routes: dict[str, int] = {}
    calls_last_hour = 0
    calls_last_24h = 0
    close_minutes: list[float] = []
    urgent_unacked = overdue = needs_review = open_comebacks = open_count = 0

    for c in calls:
        status = c.get("status", "unknown")
        urgency = c.get("urgency", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_urgency[urgency] = by_urgency.get(urgency, 0) + 1

        channel = c.get("routing_channel")
        if channel:
            routes[channel] = routes.get(channel, 0) + 1

        received = _parse(c.get("received_at"))
        if received:
            if received >= hour_ago:
                calls_last_hour += 1
            if received >= day_ago:
                calls_last_24h += 1

        if status in OPEN_STATUSES:
            open_count += 1
            if urgency == "emergency" and status in UNACKED_STATUSES:
                urgent_unacked += 1
            if status == "overdue":
                overdue += 1
            if status == "needs_review":
                needs_review += 1
            if c.get("is_comeback"):
                open_comebacks += 1

        if status in CLOSED_STATUSES:
            closed = _parse(c.get("updated_at"))
            if received and closed and closed >= received:
                close_minutes.append((closed - received).total_seconds() / 60)

    oldest = datetime.min.replace(tzinfo=timezone.utc)
    recent = sorted(
        calls, key=lambda c: _parse(c.get("received_at")) or oldest, reverse=True
    )[:RECENT_LIMIT]

    return {
        "generated_at": now.isoformat(),
        "calls_total": len(calls),
        "calls_last_24h": calls_last_24h,
        "calls_last_hour": calls_last_hour,
        "open_count": open_count,
        "closed_count": len(close_minutes),
        "avg_close_minutes": (
            round(sum(close_minutes) / len(close_minutes), 1) if close_minutes else None
        ),
        "by_status": by_status,
        "by_urgency": by_urgency,
        "routes": [
            {"name": name, "count": count}
            for name, count in sorted(routes.items(), key=lambda kv: -kv[1])
        ],
        "lights": {
            "urgent_unacked": urgent_unacked,
            "overdue": overdue,
            "needs_review": needs_review,
            "open_comebacks": open_comebacks,
        },
        "recent": [
            {
                "call_id": c.get("call_id"),
                "caller_name": c.get("caller_name"),
                "callback_number": c.get("callback_number"),
                "summary": c.get("summary"),
                "urgency": c.get("urgency"),
                "category": c.get("category"),
                "status": c.get("status"),
                "routing_channel": c.get("routing_channel"),
                "received_at": c.get("received_at"),
            }
            for c in recent
        ],
    }
