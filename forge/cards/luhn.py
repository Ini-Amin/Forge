"""forge.cards.luhn - ISO/IEC 7812 Luhn checksum validator and card generator."""
from __future__ import annotations

import hashlib
import json
import random
import string
from typing import Any, Dict, List, Optional

from forge.cards.bins import card_length, issuer_lookup
from forge.cards.storage import CardStorage, storage


def luhn_check_digit(partial: str) -> str:
    """Compute the Luhn check digit for a partial number."""
    total = 0
    for i, d in enumerate([int(c) for c in partial][::-1]):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - (total % 10)) % 10)


def is_luhn_valid(pan: str) -> bool:
    """Validate whether PAN satisfies ISO/IEC 7812 Luhn checksum."""
    if not pan or not pan.isdigit():
        return False
    total = 0
    for i, d in enumerate([int(c) for c in pan][::-1]):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_hash(pan: str) -> str:
    """Compute truncated SHA-256 fingerprint for deduplication."""
    return hashlib.sha256(pan.encode()).hexdigest()[:16]


def format_card(card: dict[str, Any], fmt: str = "pipe") -> str:
    """Format card dictionary into pipe, csv, or json format."""
    if fmt == "pipe":
        return f"{card['pan']}|{card['mm']}|{card['yy']}|{card['cvv']}"
    if fmt == "csv":
        return ",".join([
            card["pan"], card["mm"], card["yy"], card["cvv"],
            card.get("issuer", "Unknown"), card.get("network", "Unknown")
        ])
    if fmt == "json":
        return json.dumps(card)
    return f"{card['pan']}|{card['mm']}|{card['yy']}|{card['cvv']}"


def generate_random(
    bin_: str,
    exp_m: str,
    exp_y: str,
    count: int,
    card_storage: Optional[CardStorage] = None,
    seed: Optional[int] = None
) -> list[dict[str, Any]]:
    """Generate `count` unique, Luhn-valid card fixtures for the specified BIN."""
    rnd = random.Random(seed) if seed is not None else random
    length = card_length(bin_)
    cvv_len = 4 if bin_.startswith(("34", "37")) else 3
    mid_len = length - len(bin_) - 1

    cs = card_storage or storage
    out: list[dict[str, Any]] = []
    attempts = 0

    while len(out) < count and attempts < count * 20:
        attempts += 1
        mid = "".join(rnd.choices(string.digits, k=mid_len))
        partial = bin_ + mid
        pan = partial + luhn_check_digit(partial)
        h = card_hash(pan)

        if cs.has_seen(h):
            continue

        cs.record_card(h, pan, bin_)
        cvv = "".join(rnd.choices(string.digits, k=cvv_len))
        meta = issuer_lookup(pan)
        out.append({
            "pan": pan,
            "mm": exp_m,
            "yy": exp_y,
            "cvv": cvv,
            "issuer": meta["issuer"],
            "network": meta["network"],
        })

    return out


def generate_sequential(
    bin_: str,
    exp_m: str,
    exp_y: str,
    count: int,
    start_pan: Optional[str] = None
) -> list[dict[str, Any]]:
    """Generate sequential card numbers starting from optional seed PAN."""
    length = card_length(bin_)
    cvv_len = 4 if bin_.startswith(("34", "37")) else 3
    mid_len = length - len(bin_) - 1

    if start_pan:
        mid_start = int(start_pan[len(bin_):len(bin_) + mid_len])
    else:
        mid_start = 1

    out: list[dict[str, Any]] = []
    for i in range(count):
        mid = str(mid_start + i).zfill(mid_len)
        if len(mid) > mid_len:
            break
        partial = bin_ + mid
        pan = partial + luhn_check_digit(partial)
        cvv = "".join(random.choices(string.digits, k=cvv_len))
        meta = issuer_lookup(pan)
        out.append({
            "pan": pan,
            "mm": exp_m,
            "yy": exp_y,
            "cvv": cvv,
            "issuer": meta["issuer"],
            "network": meta["network"],
        })

    return out
