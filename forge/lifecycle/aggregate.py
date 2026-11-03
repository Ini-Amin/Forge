"""forge.lifecycle.aggregate - Derived transaction read model.

Computes a one-line view of a transaction from the per-track lifecycle
states produced by the engine. Nothing is stored: the aggregate holds
only derived fields and is rebuilt from `tracks` on every call.

`SETTLED` is terminal only within the Settlement track; it is not a
global "transaction finished" flag. Track-terminal failures
(`CLEARING_FAILED` / `SETTLEMENT_FAILED`) report `needs_handling = True`
and do not mark the transaction `failed`; `failed` is reserved for an
authorization that was `DECLINED`.
"""
from __future__ import annotations

from dataclasses import dataclass

CLEARING_FAILED = "CLEARING_FAILED"
SETTLEMENT_FAILED = "SETTLEMENT_FAILED"


@dataclass(frozen=True)
class LifecycleAggregate:
    authorization: str | None
    capture: str | None
    clearing: str | None
    settlement: str | None
    needs_handling: bool
    failed: bool
    is_settled: bool
    summary: str


def build_aggregate(tracks: dict[str, str | None]) -> LifecycleAggregate:
    authorization = tracks.get("authorization")
    capture = tracks.get("capture")
    clearing = tracks.get("clearing")
    settlement = tracks.get("settlement")

    needs_handling = clearing == CLEARING_FAILED or settlement == SETTLEMENT_FAILED
    failed = authorization == "DECLINED"
    is_settled = settlement == "SETTLED"

    if failed:
        summary = "declined"
    elif needs_handling:
        summary = "needs_handling"
    elif is_settled:
        summary = "settled"
    else:
        furthest = settlement or clearing or capture or authorization
        summary = furthest.lower() if furthest is not None else "none"

    return LifecycleAggregate(
        authorization=authorization,
        capture=capture,
        clearing=clearing,
        settlement=settlement,
        needs_handling=needs_handling,
        failed=failed,
        is_settled=is_settled,
        summary=summary,
    )
