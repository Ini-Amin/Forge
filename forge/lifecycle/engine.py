"""forge.lifecycle.engine - Event engine: processing, validation, idempotency, audit trail.

Drives the per-track payment lifecycle state machine from a JSON event list.
Processing is strictly in FILE ORDER; `occurred_at` is provenance and never
drives ordering. Replayable: same input file produces identical results.
Verdict vocabulary for event results is exactly `applied` / `rejected` /
`duplicate`.
"""
from __future__ import annotations

from dataclasses import dataclass

from forge.lifecycle import rates
from forge.lifecycle.state import (
    ACTIVE_TRACKS,
    INACTIVE_EVENT_TYPES,
    INITIAL_STATES,
    evaluate_guard,
    find_transition,
)

REQUIRED_KEYS = frozenset({"event_id", "type", "occurred_at", "source", "amount_units", "currency"})


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    type: str
    occurred_at: str
    source: str
    amount_units: int
    currency: str
    result: str
    reason: str


@dataclass(frozen=True)
class LifecycleResult:
    tracks: dict[str, str | None]
    history: tuple[EventRecord, ...]
    tracks_history: dict[str, tuple[EventRecord, ...]]
    converted_units_expected: int


def _track_for(event_type: str) -> str | None:
    transition = find_transition(event_type)
    if transition is not None:
        return transition.track
    return INACTIVE_EVENT_TYPES.get(event_type)


class LifecycleEngine:
    def __init__(self, events: list[dict]):
        self.events = list(events)

    def run(self, country: str = "US") -> LifecycleResult:
        run_currency = rates.COUNTRY_CURRENCY[country]
        converted_units_expected = rates.converted_units(run_currency)

        tracks: dict[str, str | None] = dict(INITIAL_STATES)
        seen_ids: set[str] = set()
        captured_total_units = 0
        history: list[EventRecord] = []
        per_track: dict[str, list[EventRecord]] = {track: [] for track in ACTIVE_TRACKS}

        def record(event: dict, result: str, reason: str, track: str | None) -> None:
            rec = EventRecord(
                event_id=str(event.get("event_id", "")),
                type=str(event.get("type", "")),
                occurred_at=str(event.get("occurred_at", "")),
                source=str(event.get("source", "")),
                amount_units=event.get("amount_units", 0) if isinstance(event.get("amount_units"), int) and not isinstance(event.get("amount_units"), bool) else 0,
                currency=str(event.get("currency", "")),
                result=result,
                reason=reason,
            )
            history.append(rec)
            if track in per_track:
                per_track[track].append(rec)

        for event in self.events:
            # 1. shape
            if not self._shape_ok(event):
                record(event if isinstance(event, dict) else {}, "rejected", "invalid event payload",
                       _track_for(event.get("type", "")) if isinstance(event, dict) else None)
                continue

            event_id = event["event_id"]
            event_type = event["type"]
            track = _track_for(event_type)

            # 2. duplicate
            if event_id in seen_ids:
                record(event, "duplicate", f"duplicate event_id {event_id}", track)
                continue
            seen_ids.add(event_id)

            # 3. inactive phase-2 vocabulary
            if event_type in INACTIVE_EVENT_TYPES:
                inactive_track = INACTIVE_EVENT_TYPES[event_type]
                record(event, "rejected", f"track {inactive_track} inactive in phase 1", inactive_track)
                continue

            # 4. unknown event type
            transition = find_transition(event_type)
            if transition is None:
                record(event, "rejected", "unknown event type", None)
                continue

            # 5. transition's track must be an active track (defensive)
            if transition.track not in ACTIVE_TRACKS:
                record(event, "rejected", f"track {transition.track} inactive in phase 1", transition.track)
                continue

            # 6. currency
            if event["currency"] != run_currency:
                record(event, "rejected",
                       f"currency mismatch: file currency {event['currency']} must be {run_currency}",
                       transition.track)
                continue

            # 7. amount
            amount_units = event["amount_units"]
            if amount_units != converted_units_expected:
                record(event, "rejected",
                       f"mock rule: only $1.00 in {run_currency} ({converted_units_expected} minor units); got {amount_units}",
                       transition.track)
                continue

            # 8. own-state precondition
            current = tracks[transition.track]
            if transition.from_state is None:
                if current is not None:
                    record(event, "rejected", f"invalid transition {event_type} from {current}", transition.track)
                    continue
            elif current != transition.from_state:
                record(event, "rejected", f"invalid transition {event_type} from {current}", transition.track)
                continue

            # 9. guard
            if transition.guard is not None:
                remaining_units = converted_units_expected - captured_total_units
                ok, reason = evaluate_guard(transition.guard, tracks, remaining_units)
                if not ok:
                    record(event, "rejected", reason, transition.track)
                    continue

            # success
            tracks[transition.track] = transition.to_state
            if event_type == "capture.accepted":
                captured_total_units += amount_units
            record(event, "applied", "applied", transition.track)

        return LifecycleResult(
            tracks=tracks,
            history=tuple(history),
            tracks_history={track: tuple(records) for track, records in per_track.items()},
            converted_units_expected=converted_units_expected,
        )

    @staticmethod
    def _shape_ok(event) -> bool:
        if not isinstance(event, dict):
            return False
        if set(event) != REQUIRED_KEYS:
            return False
        for key in ("event_id", "type", "occurred_at", "source", "currency"):
            if not isinstance(event[key], str):
                return False
        amount = event["amount_units"]
        if not isinstance(amount, int) or isinstance(amount, bool):
            return False
        return True
