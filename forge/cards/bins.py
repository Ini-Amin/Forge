"""forge.cards.bins - Bank Identification Number (BIN) database and card specs.

Every entry carries `source`, which names the reference the issuer/country/
currency claim was checked against: "binlist" (binlist.net data repo — CC-BY
4.0) or "test-panel". An entry with a placeholder issuer ("test", "unknown",
"?") is a broken record, not a BIN, and validate_bin_db() refuses it.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

BIN_DB: dict[str, dict[str, Any]] = {
    # ── United States ────────────────────────────────────────────────────────
    "414720": {"network": "Visa", "issuer": "JPMorgan Chase", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "517805": {"network": "Mastercard", "issuer": "Capital One", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 8, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "401804": {"network": "Visa", "issuer": "Citi", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "378282": {"network": "American Express", "issuer": "American Express", "country": "US", "currency": "USD",
               "pan_length": 15, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "test-panel"},
    "601100": {"network": "Discover", "issuer": "Discover Financial", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "400022": {"network": "Visa", "issuer": "Navy Federal Credit Union", "country": "US", "currency": "USD",
               "pan_length": 16, "bin_length": 6, "funding": "debit", "is_prepaid": False,
               "source": "binlist"},
    # ── United Kingdom ───────────────────────────────────────────────────────
    "475127": {"network": "Visa", "issuer": "NatWest", "country": "GB", "currency": "GBP",
               "pan_length": 16, "bin_length": 6, "funding": "debit", "is_prepaid": False,
               "source": "binlist"},
    # ── Japan ────────────────────────────────────────────────────────────────
    "353011": {"network": "JCB", "issuer": "JCB International", "country": "JP", "currency": "JPY",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Indonesia ────────────────────────────────────────────────────────────
    "461700": {"network": "Visa", "issuer": "Bank Mandiri", "country": "ID", "currency": "IDR",
               "pan_length": 16, "bin_length": 6, "funding": "debit", "is_prepaid": False,
               "source": "binlist"},
    "455632": {"network": "Visa", "issuer": "Bank Central Asia", "country": "ID", "currency": "IDR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Germany ──────────────────────────────────────────────────────────────
    "454618": {"network": "Visa", "issuer": "Commerzbank", "country": "DE", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "447590": {"network": "Visa", "issuer": "Stadtsparkasse Dusseldorf", "country": "DE", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "debit", "is_prepaid": False,
               "source": "binlist"},
    # ── Brazil ───────────────────────────────────────────────────────────────
    "544828": {"network": "Mastercard", "issuer": "Itau Unibanco", "country": "BR", "currency": "BRL",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "400163": {"network": "Visa", "issuer": "Banco do Brasil", "country": "BR", "currency": "BRL",
               "pan_length": 16, "bin_length": 6, "funding": "debit", "is_prepaid": False,
               "source": "binlist"},
    # ── Canada ───────────────────────────────────────────────────────────────
    "451013": {"network": "Visa", "issuer": "Royal Bank of Canada", "country": "CA", "currency": "CAD",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "528061": {"network": "Mastercard", "issuer": "Bank of Montreal", "country": "CA", "currency": "CAD",
               "pan_length": 16, "bin_length": 6, "funding": "debit", "is_prepaid": False,
               "source": "binlist"},
    # ── France ───────────────────────────────────────────────────────────────
    "497490": {"network": "Visa", "issuer": "BNP Paribas", "country": "FR", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "513200": {"network": "Mastercard", "issuer": "Credit Mutuel", "country": "FR", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Italy ────────────────────────────────────────────────────────────────
    "490824": {"network": "Visa", "issuer": "Intesa Sanpaolo", "country": "IT", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "482498": {"network": "Visa", "issuer": "Unicredit", "country": "IT", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Spain ────────────────────────────────────────────────────────────────
    "409015": {"network": "Visa", "issuer": "BBVA", "country": "ES", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "410626": {"network": "Visa", "issuer": "Banco Sabadell", "country": "ES", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Australia ────────────────────────────────────────────────────────────
    "456462": {"network": "Visa", "issuer": "ANZ Banking Group", "country": "AU", "currency": "AUD",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "456471": {"network": "Visa", "issuer": "Westpac Banking", "country": "AU", "currency": "AUD",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Singapore ────────────────────────────────────────────────────────────
    "411911": {"network": "Visa", "issuer": "DBS Bank", "country": "SG", "currency": "SGD",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "524040": {"network": "Mastercard", "issuer": "OCBC Bank", "country": "SG", "currency": "SGD",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Netherlands ──────────────────────────────────────────────────────────
    "456353": {"network": "Visa", "issuer": "ABN AMRO", "country": "NL", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "520953": {"network": "Mastercard", "issuer": "Rabobank", "country": "NL", "currency": "EUR",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Sweden ───────────────────────────────────────────────────────────────
    "453903": {"network": "Visa", "issuer": "Nordea", "country": "SE", "currency": "SEK",
               "pan_length": 16, "bin_length": 6, "funding": "debit", "is_prepaid": False,
               "source": "binlist"},
    "522661": {"network": "Mastercard", "issuer": "Handelsbanken", "country": "SE", "currency": "SEK",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Switzerland (data only: identity pipeline has no CH profile) ────────
    "490118": {"network": "Visa", "issuer": "UBS", "country": "CH", "currency": "CHF",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "540444": {"network": "Mastercard", "issuer": "Credit Suisse", "country": "CH", "currency": "CHF",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    # ── Mexico (data only: identity pipeline has no MX profile) ─────────────
    "491573": {"network": "Visa", "issuer": "Santander Mexico", "country": "MX", "currency": "MXN",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
    "410180": {"network": "Visa", "issuer": "BBVA Bancomer", "country": "MX", "currency": "MXN",
               "pan_length": 16, "bin_length": 6, "funding": "credit", "is_prepaid": False,
               "source": "binlist"},
}

# Defaults exist only where the identity pipeline can generate a coherent
# buyer; a BIN for a country with no identity profile lives in the DB (queryable
# via --bin) but never becomes a country default.
COUNTRY_DEFAULT_BIN: dict[str, str] = {
    "US": "414720",
    "GB": "475127",
    "JP": "353011",
    "ID": "461700",
    "DE": "454618",
    "BR": "544828",
    "CA": "451013",
    "FR": "497490",
    "IT": "490824",
    "ES": "409015",
    "AU": "456462",
    "SG": "411911",
    "NL": "456353",
    "SE": "453903",
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


def validate_bin_db() -> list[str]:
    """Return every integrity violation in BIN_DB; empty list means it is sound.

    This is the gate that keeps fabricated prefixes and misattributed issuers
    out of the database. It checks structure and self-consistency only — the
    truthfulness of each source-verified record is whatever its `source` says.
    """
    from forge.cards.luhn import is_luhn_valid, luhn_check_digit

    errors: list[str] = []
    seen: set[str] = set()
    known_countries = {
        "US", "GB", "JP", "ID", "DE", "BR", "CA", "FR", "IT", "ES",
        "AU", "SG", "NL", "SE", "CH", "MX", "AE", "AR", "AT", "BE", "CL",
        "CO", "CZ", "DK", "EE", "FI", "GR", "HK", "HU", "IE", "IL", "IN",
        "IS", "KR", "LT", "LU", "LV", "MT", "MY", "NO", "NZ", "PE", "PH",
        "PL", "PT", "QA", "RO", "SA", "SK", "TH", "TR", "TW", "UA", "VN", "ZA",
    }
    # A record whose issuer is a placeholder token is a hole in the data, not
    # a real attribution. Catch whole-word placeholders plus prefixed ones
    # ("Test Bank") via a word boundary; plain "^test$" would miss the second.
    placeholder = re.compile(
        r"^(\?)$|^(unknown|test|mock|dummy|example|fake|placeholder)(\b|$)|^$",
        re.IGNORECASE,
    )

    for prefix, meta in sorted(BIN_DB.items()):
        where = f"BIN {prefix}"
        if not prefix.isdigit() or not 4 <= len(prefix) <= 8:
            errors.append(f"{where}: prefix must be 4-8 digits")
        if prefix in seen:
            errors.append(f"{where}: duplicate prefix")
        seen.add(prefix)
        if not isinstance(meta, dict):
            errors.append(f"{where}: metadata must be a dict")
            continue

        issuer = str(meta.get("issuer", "")).strip()
        if placeholder.match(issuer):
            errors.append(f"{where}: issuer {issuer!r} is a placeholder, not a real issuer")
        if not str(meta.get("country", "")).strip() or not str(meta.get("currency", "")).strip():
            errors.append(f"{where}: country/currency must not be empty")
        if str(meta.get("country", "")).upper() not in known_countries:
            errors.append(f"{where}: country {meta.get('country')!r} is not an ISO alpha-2 code")
        if not str(meta.get("source", "")).strip():
            errors.append(f"{where}: missing source (provenance of the issuer claim)")

        funding = str(meta.get("funding", "unknown")).lower()
        if funding not in ("credit", "debit", "prepaid"):
            errors.append(f"{where}: funding {funding!r} not in credit/debit/prepaid")
        if bool(meta.get("is_prepaid")) != (funding == "prepaid"):
            errors.append(f"{where}: is_prepaid contradicts funding {funding!r}")

        net = str(meta.get("network", ""))
        inferred = infer_network(prefix)
        if net and inferred and net.lower() != inferred.lower():
            errors.append(f"{where}: network {net!r} contradicts IIN {inferred!r}")

        # A real BIN must be able to produce a Luhn-valid PAN of its own length:
        # pad the prefix to pan_length-1, append the check digit, verify.
        pan_len = int(meta.get("pan_length") or 16)
        if len(prefix) > pan_len:
            errors.append(f"{where}: pan_length {pan_len} shorter than the prefix")
            continue
        partial = prefix + "0" * (pan_len - 1 - len(prefix))
        pan = partial + luhn_check_digit(partial)
        if not (pan.startswith(prefix) and len(pan) == pan_len and is_luhn_valid(pan)):
            errors.append(f"{where}: cannot form a Luhn-valid PAN of length {pan_len}")
    return errors


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

