"""forge.payments.idempotency - Idempotency-Key and request correlation management."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class IdempotencyRecord:
    key: str
    created_at: float
    endpoint: str
    last_status: Optional[int] = None
    response_hash: Optional[str] = None


class IdempotencyManager:
    """Manages unique request identifiers to prevent duplicate processing in distributed payment systems."""

    def __init__(self, key_prefix: str = "forge_req"):
        self.key_prefix = key_prefix
        self._records: dict[str, IdempotencyRecord] = {}

    def generate_key(self, endpoint: str) -> str:
        """Generate an RFC 4122 UUIDv4 idempotency key."""
        unique_id = uuid.uuid4().hex
        key = f"{self.key_prefix}_{unique_id}"
        self._records[key] = IdempotencyRecord(
            key=key,
            created_at=time.time(),
            endpoint=endpoint,
        )
        return key

    def get_headers(self, key: Optional[str] = None, endpoint: str = "") -> dict[str, str]:
        """Construct standard idempotency and correlation headers."""
        active_key = key or self.generate_key(endpoint)
        return {
            "Idempotency-Key": active_key,
            "X-Request-Id": f"req_{uuid.uuid4().hex[:16]}",
            "X-Client-Timestamp": str(int(time.time())),
        }

    def record_outcome(self, key: str, status_code: int, response_hash: Optional[str] = None) -> None:
        if key in self._records:
            self._records[key].last_status = status_code
            self._records[key].response_hash = response_hash
