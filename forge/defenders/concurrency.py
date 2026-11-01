"""forge.defenders.concurrency - Race condition, TOCTOU, and distributed locking auditor.

Tests whether staging checkout endpoints properly implement distributed locking:
- Sends parallel burst requests with identical Idempotency-Key or cart/intent token
- Detects double-spend, duplicate order creation, or unhandled race conditions
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from forge.transport.session import AsyncTLSSession


@dataclass
class RaceConditionAuditResult:
    total_burst_requests: int
    successful_authorizations: int
    conflict_or_dedup_responses: int
    error_responses: int
    latencies_ms: list[float]
    has_race_vulnerability: bool
    summary: str


class RaceConditionAuditor:
    """Audits staging payment endpoints for Time-of-Check to Time-of-Use (TOCTOU) and double authorization."""

    @classmethod
    async def audit_endpoint(
        cls,
        target_url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        concurrency: int = 10,
        proxy_url: Optional[str] = None,
    ) -> RaceConditionAuditResult:
        """Fire a parallel burst of requests with identical payload/headers to check for race conditions."""
        latencies: list[float] = []
        statuses: list[int] = []

        async def _fire():
            start = time.monotonic()
            try:
                async with AsyncTLSSession(proxy=proxy_url, strict_proxy=bool(proxy_url)) as session:
                    resp = await session.post(target_url, json=payload, headers=headers, timeout=10.0)
                    elapsed = (time.monotonic() - start) * 1000.0
                    latencies.append(round(elapsed, 2))
                    statuses.append(resp.status_code)
            except Exception:
                latencies.append(-1.0)
                statuses.append(0)

        # Dispatch all concurrent requests simultaneously
        await asyncio.gather(*[_fire() for _ in range(concurrency)])

        successes = sum(1 for s in statuses if 200 <= s < 300)
        conflicts = sum(1 for s in statuses if s in (409, 429, 400))
        errors = sum(1 for s in statuses if s >= 500 or s == 0)

        # A secure payment backend MUST ensure only ONE mutation succeeds for the same idempotency key or cart
        has_vuln = (successes > 1)
        if has_vuln:
            summary = (
                f"VULNERABILITY DETECTED: {successes}/{concurrency} concurrent requests succeeded. "
                "Backend lacks pessimistic or distributed locking (TOCTOU double-spend risk)."
            )
        elif successes == 1:
            summary = (
                f"PROTECTED: Exactly 1/{concurrency} request succeeded; "
                f"{conflicts} absorbed as conflict/dedup. Backend locking is intact."
            )
        else:
            summary = f"INCONCLUSIVE: {errors} errors encountered during burst test."

        return RaceConditionAuditResult(
            total_burst_requests=concurrency,
            successful_authorizations=successes,
            conflict_or_dedup_responses=conflicts,
            error_responses=errors,
            latencies_ms=latencies,
            has_race_vulnerability=has_vuln,
            summary=summary,
        )
