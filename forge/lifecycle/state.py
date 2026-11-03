"""forge.lifecycle.state - Track definitions, transitions, and guards.

Per-track payment lifecycle state machine (mock-only). Each track
(authorization, capture, clearing, settlement) advances independently via
events; guards gate transitions on the state of other tracks and on the
run's remaining minor units. Phase-2 vocabulary events are declared in
INACTIVE_EVENT_TYPES so the engine can reject them as "inactive" rather
than "unknown" — they have no transitions and are never applied.
"""
from __future__ import annotations

from dataclasses import dataclass

ACTIVE_TRACKS: tuple = ("authorization", "capture", "clearing", "settlement")


@dataclass(frozen=True)
class Transition:
    event_type: str
    track: str
    from_state: str | None
    to_state: str
    guard: str | None


TRANSITIONS: tuple[Transition, ...] = (
    Transition("auth.accepted", "authorization", "PENDING", "AUTHORIZED", None),
    Transition("auth.declined", "authorization", "PENDING", "DECLINED", None),
    Transition("capture.accepted", "capture", None, "CAPTURED", "eligible_auth"),
    Transition("clearing.submitted", "clearing", None, "CLEARING_PENDING", "clearing_eligible"),
    Transition("clearing.accepted", "clearing", "CLEARING_PENDING", "CLEARED", None),
    Transition("clearing.failed", "clearing", "CLEARING_PENDING", "CLEARING_FAILED", None),
    Transition("settlement.submitted", "settlement", None, "SETTLEMENT_PENDING", "settlement_eligible"),
    Transition("settlement.accepted", "settlement", "SETTLEMENT_PENDING", "SETTLED", None),
    Transition("settlement.failed", "settlement", "SETTLEMENT_PENDING", "SETTLEMENT_FAILED", None),
)

INITIAL_STATES: dict[str, str | None] = {
    "authorization": "PENDING",
    "capture": None,
    "clearing": None,
    "settlement": None,
}

# Phase-2 vocabulary events mapped to their track. Vocabulary declarations
# only — no transitions, never applied.
INACTIVE_EVENT_TYPES: dict[str, str] = {
    "refund.accepted": "refund",
    "refund.partial": "refund",
    "refund.full": "refund",
    "chargeback.received": "dispute",
    "chargeback.won": "dispute",
    "chargeback.lost": "dispute",
    "reversal.submitted": "reversal",
    "void.submitted": "reversal",
}


def find_transition(event_type: str) -> Transition | None:
    """Return the transition for `event_type`, or None if the event has no transition."""
    for transition in TRANSITIONS:
        if transition.event_type == event_type:
            return transition
    return None


def evaluate_guard(guard: str, tracks: dict[str, str | None], remaining_units: int) -> tuple[bool, str]:
    """Evaluate `guard` against current track states and remaining minor units.

    `remaining_units` is the run's expected $1 minor units minus the sum of
    applied capture amounts. Returns (ok, reason).
    """
    if guard == "eligible_auth":
        if tracks.get("authorization") != "AUTHORIZED":
            return False, "no eligible authorization"
        if remaining_units <= 0:
            return False, "remaining must be positive"
        return True, "eligible authorization with remaining units"
    if guard == "clearing_eligible":
        if tracks.get("capture") != "CAPTURED":
            return False, "capture not CAPTURED"
        return True, "capture CAPTURED"
    if guard == "settlement_eligible":
        if tracks.get("clearing") != "CLEARED":
            return False, "clearing not CLEARED"
        return True, "clearing CLEARED"
    raise ValueError(f"Unknown guard: {guard!r}")
