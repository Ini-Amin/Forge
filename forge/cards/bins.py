"""forge.cards.bins - Bank Identification Number (BIN) database and card specs."""
from __future__ import annotations

from typing import Any, Dict

BIN_DB: dict[str, dict[str, Any]] = {
    "414720": {"network": "Visa", "issuer": "Chase", "country": "US"},
    "424242": {"network": "Visa", "issuer": "Stripe Test", "country": "US", "is_test": True},
    "411111": {"network": "Visa", "issuer": "Various (generic test)", "country": "US", "is_test": True},
    "517805": {"network": "Mastercard", "issuer": "Capital One", "country": "US"},
    "552134": {"network": "Mastercard", "issuer": "Citi", "country": "US"},
    "378282": {"network": "American Express", "issuer": "Amex Centurion", "country": "US"},
    "601100": {"network": "Discover", "issuer": "Discover Financial", "country": "US"},
    "353011": {"network": "JCB", "issuer": "JCB International", "country": "JP"},
    "401288": {"network": "Visa", "issuer": "Bank of America", "country": "US"},
}


def card_length(bin_: str) -> int:
    """Determine standard card PAN length by prefix."""
    if bin_.startswith(("34", "37")):
        return 15  # Amex
    if bin_.startswith(("30", "36", "38")):
        return 14  # Diners
    return 16      # Standard Visa/MC/Discover/JCB


def issuer_lookup(bin_or_pan: str) -> dict[str, Any]:
    """Look up issuer metadata by BIN prefix (evaluates 8, 6, and 4 digits)."""
    for prefix_len in (8, 6, 4):
        prefix = bin_or_pan[:prefix_len]
        if prefix in BIN_DB:
            return BIN_DB[prefix]
    return {"network": "Unknown", "issuer": "Unknown", "country": "??"}
