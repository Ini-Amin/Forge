"""forge.cards.bins - Bank Identification Number (BIN) database and card specs."""
from __future__ import annotations

from typing import Any, Dict, Optional

BIN_DB: dict[str, dict[str, Any]] = {
    "414720": {"network": "Visa", "issuer": "Chase", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "517805": {"network": "Mastercard", "issuer": "Capital One", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "552134": {"network": "Mastercard", "issuer": "Citi", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 8, "funding": "debit", "is_prepaid": False},
    "378282": {"network": "American Express", "issuer": "Amex Centurion", "country": "US", "currency": "USD",
               "pan_length": 15, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "601100": {"network": "Discover", "issuer": "Discover Financial", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "353011": {"network": "JCB", "issuer": "JCB International", "country": "JP", "currency": "JPY",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "401288": {"network": "Visa", "issuer": "Bank of America", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 8, "funding": "debit", "is_prepaid": False},
    "461700": {"network": "Visa", "issuer": "Bank Mandiri", "country": "ID", "currency": "IDR",
               "pan_length": 16, "bin_length": 8, "funding": "debit", "is_prepaid": False},
    "521114": {"network": "Mastercard", "issuer": "Bank Central Asia", "country": "ID", "currency": "IDR",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "455642": {"network": "Visa", "issuer": "Deutsche Bank", "country": "DE", "currency": "EUR",
               "pan_length": 16, "bin_length": 8, "funding": "debit", "is_prepaid": False},
    "510001": {"network": "Mastercard", "issuer": "Commerzbank", "country": "DE", "currency": "EUR",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "400403": {"network": "Visa", "issuer": "Banco do Brasil", "country": "BR", "currency": "BRL",
               "pan_length": 16, "bin_length": 8, "funding": "debit", "is_prepaid": False},
    "544828": {"network": "Mastercard", "issuer": "Itau Unibanco", "country": "BR", "currency": "BRL",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "475127": {"network": "Visa", "issuer": "Barclays Bank", "country": "GB", "currency": "GBP",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False},
    "400022": {"network": "Visa", "issuer": "HSBC UK", "country": "GB", "currency": "GBP",
               "pan_length": 16, "bin_length": 8, "funding": "prepaid", "is_prepaid": True},
}

COUNTRY_DEFAULT_BIN: dict[str, str] = {
    "US": "414720",
    "JP": "353011",
    "ID": "461700",
    "DE": "455642",
    "BR": "400403",
    "GB": "475127",
}


def get_default_bin_for_country(country: str) -> str:
    """Return a geo-coherent default BIN matching the target country."""
    return COUNTRY_DEFAULT_BIN.get(country.upper(), "414720")


def bins_by(network: Optional[str] = None, country: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Filter BIN_DB by network and/or country (case-insensitive substring match)."""
    net = (network or "").lower()
    ctry = (country or "").upper()
    return {
        b: meta for b, meta in BIN_DB.items()
        if (not net or net in meta["network"].lower())
        and (not ctry or meta["country"] == ctry)
    }


def card_length(bin_: str) -> int:
    """Determine standard card PAN length by prefix."""
    meta = issuer_lookup(bin_)
    if meta["bin"] != "Unknown":
        return meta["pan_length"]
    if bin_.startswith(("34", "37")):
        return 15  # Amex
    if bin_.startswith(("30", "36", "38")):
        return 14  # Diners
    return 16      # Standard Visa/MC/Discover/JCB


_UNKNOWN_META: dict[str, Any] = {
    "bin": "Unknown", "network": "Unknown", "issuer": "Unknown", "country": "??",
    "currency": "?", "pan_length": 16, "bin_length": 6, "funding": "unknown", "is_prepaid": False,
}


def issuer_lookup(bin_or_pan: str) -> dict[str, Any]:
    """Look up issuer metadata by BIN prefix (evaluates 8, 6, and 4 digits)."""
    for prefix_len in (8, 6, 4):
        prefix = bin_or_pan[:prefix_len]
        if prefix in BIN_DB:
            return {"bin": prefix, **BIN_DB[prefix]}
    return dict(_UNKNOWN_META)
