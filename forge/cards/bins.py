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


def get_default_bin_for_country(country: str) -> Optional[str]:
    """Return the default BIN for a country, or None if forge has no BIN there.

    Returning a US BIN for an unrecognised country would hand the caller a
    Chase card labelled US/USD while they asked for somewhere else — a fixture
    that looks coherent and is not. Absence is reported as absence.
    """
    return COUNTRY_DEFAULT_BIN.get(country.upper())


def supported_countries() -> list[str]:
    """Countries forge can produce a geo-coherent card for."""
    return sorted(COUNTRY_DEFAULT_BIN)


def bins_by(network: Optional[str] = None, country: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Filter BIN_DB by network and/or country (case-insensitive substring match)."""
    net = (network or "").lower()
    ctry = (country or "").upper()
    return {
        b: meta for b, meta in BIN_DB.items()
        if (not net or net in meta["network"].lower())
        and (not ctry or meta["country"] == ctry)
    }


def infer_network(pan: str) -> Optional[str]:
    """Derive the card network from the IIN ranges defined in ISO/IEC 7812.

    A prefix missing from BIN_DB still carries its network: '4' is Visa whoever
    issues it. That is real information and dropping it to Unknown would make
    an unlisted BIN look indistinguishable from an unparseable string.
    """
    if not pan or not pan.isdigit() or len(pan) < 4:
        return None
    n2 = int(pan[:2])
    n3 = int(pan[:3])
    n4 = int(pan[:4])
    if pan[0] == "4":
        return "Visa"
    if n2 in (34, 37):
        return "American Express"
    if n2 in (30, 36, 38):
        return "Diners Club"
    if n2 == 35:
        return "JCB"
    if pan[:4] == "6011" or n2 == 65 or 644 <= n3 <= 649:
        return "Discover"
    if 51 <= n2 <= 55 or 2221 <= n4 <= 2720:
        return "Mastercard"
    return None


def card_length(bin_: str) -> int:
    """Determine standard card PAN length by prefix."""
    meta = issuer_lookup(bin_)
    if meta["bin_known"]:
        return meta["pan_length"]
    if bin_.startswith(("34", "37")):
        return 15  # Amex
    if bin_.startswith(("30", "36", "38")):
        return 14  # Diners
    return 16      # Standard Visa/MC/Discover/JCB


def issuer_lookup(bin_or_pan: str) -> dict[str, Any]:
    """Look up issuer metadata by BIN prefix (evaluates 8, 6, and 4 digits).

    `bin_known` says whether the prefix is in the database. When it is not, the
    network is still inferred from IIN ranges, but issuer, country and currency
    stay empty because nothing truthful can be said about them.
    """
    for prefix_len in (8, 6, 4):
        prefix = bin_or_pan[:prefix_len]
        if prefix in BIN_DB:
            return {"bin": prefix, "bin_known": True, **BIN_DB[prefix]}
    return {
        "bin": "Unknown",
        "bin_known": False,
        "network": infer_network(bin_or_pan) or "Unknown",
        "issuer": "Unknown",
        "country": "??",
        "currency": "?",
        "pan_length": card_length_for_network(infer_network(bin_or_pan)),
        "bin_length": 6,
        "funding": "unknown",
        "is_prepaid": False,
    }


def card_length_for_network(network: Optional[str]) -> int:
    """PAN length implied by the network when no issuer record exists."""
    if network == "American Express":
        return 15
    if network == "Diners Club":
        return 14
    return 16

