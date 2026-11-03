"""forge.lifecycle.rates - Mock currency rate table for $1.00 conversions.

Mock-only rates used by the lifecycle engine to express a $1.00 charge in
each supported currency, in ISO 4217 minor units. ISO 4217 precision rules
(JPY zero-decimal, IDR two-decimal) come from the existing
CurrencyPrecisionAuditor — do not special-case them here.
"""
from __future__ import annotations

from forge.defenders.currency import CurrencyPrecisionAuditor

COUNTRY_CURRENCY: dict[str, str] = {"US": "USD", "JP": "JPY", "DE": "EUR", "GB": "GBP", "ID": "IDR"}

# Amount of currency per $1.00 (mock rates, not live FX).
RATES: dict[str, str] = {"USD": "1.00", "JPY": "150.00", "EUR": "0.92", "GBP": "0.79", "IDR": "15500.00"}


def converted_units(currency: str) -> int:
    """Minor units of $1.00 in `currency`, per ISO 4217 via CurrencyPrecisionAuditor."""
    curr = currency.upper().strip()
    if curr not in RATES:
        raise ValueError(f"Unknown currency: {currency!r}")
    amount = RATES[curr]
    return CurrencyPrecisionAuditor.audit_amount_to_units(curr, amount).expected_integer_units
