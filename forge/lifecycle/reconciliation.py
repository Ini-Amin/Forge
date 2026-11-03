"""forge.lifecycle.reconciliation - Internal vs external event comparison.

Reconciliation is an independent concern: it compares the lifecycle's
internal records against a supplied external/mock record set and returns a
report. It never mutates lifecycle state, never touches the engine, and
never writes to any lifecycle history.

Both inputs use the event-file JSON shape (`{"events": [...]}`). Records
are joined by `event_id` only; `event_id` is never diffed. The four diffed
fields are exactly `type`, `occurred_at`, `amount_units`, `currency`.
Engine metadata (`result`, `reason`, `source`) is never diffed.

Row order is deterministic: one row per internal record (in internal
order), then one row per external-only record (in external order).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

DIFF_FIELDS = ("type", "occurred_at", "amount_units", "currency")

MATCH = "match"
MISMATCH = "mismatch"
MISSING_EXTERNAL = "missing_external"
UNEXPECTED_EXTERNAL = "unexpected_external"


@dataclass(frozen=True)
class ReconRow:
    event_id: str
    status: str
    diffs: tuple[str, ...]


@dataclass(frozen=True)
class ReconciliationReport:
    rows: tuple[ReconRow, ...]
    counts: dict[str, int]
    matches: int
    mismatches: int
    missing_external: int
    unexpected_external: int


def reconcile(internal: list[dict], external: list[dict]) -> ReconciliationReport:
    external_by_id = {}
    for event in external:
        external_by_id.setdefault(event.get("event_id"), event)

    internal_ids = {event.get("event_id") for event in internal}

    rows: list[ReconRow] = []

    for event in internal:
        event_id = event.get("event_id")
        other = external_by_id.get(event_id)
        if other is None:
            rows.append(ReconRow(event_id=event_id, status=MISSING_EXTERNAL, diffs=()))
            continue
        diffs = tuple(f for f in DIFF_FIELDS if event.get(f) != other.get(f))
        status = MISMATCH if diffs else MATCH
        rows.append(ReconRow(event_id=event_id, status=status, diffs=diffs))

    for event in external:
        event_id = event.get("event_id")
        if event_id not in internal_ids:
            rows.append(ReconRow(event_id=event_id, status=UNEXPECTED_EXTERNAL, diffs=()))

    counts = {MATCH: 0, MISMATCH: 0, MISSING_EXTERNAL: 0, UNEXPECTED_EXTERNAL: 0}
    for row in rows:
        counts[row.status] += 1

    return ReconciliationReport(
        rows=tuple(rows),
        counts=counts,
        matches=counts[MATCH],
        mismatches=counts[MISMATCH],
        missing_external=counts[MISSING_EXTERNAL],
        unexpected_external=counts[UNEXPECTED_EXTERNAL],
    )


def events_from_file(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    events = data["events"]
    if isinstance(events, list) and not all(isinstance(event, dict) for event in events):
        raise ValueError("'events' must contain only JSON objects")
    return events
