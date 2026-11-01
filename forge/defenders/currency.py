"""forge.defenders.currency - Currency truncation and decimal precision auditor.

Validates ISO 4217 zero-decimal, three-decimal, and fractional currency conversion rules:
- Zero-decimal currencies (JPY, KRW, VND, etc.) where smallest unit is 1, not 100
- Three-decimal currencies (KWD, BHD, OMR, etc.) where smallest unit is 1000
- Fractional rounding hazards (e.g. $10.555 -> 1055 vs 1056 cents)
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CurrencyPrecisionCheck:
    currency: str
    input_amount: float
    expected_integer_units: int
    is_zero_decimal: bool
    is_three_decimal: bool
    potential_truncation_loss: float
    has_rounding_hazard: bool
    recommendation: str


class CurrencyPrecisionAuditor:
    """Audits currency conversion and integer unit conversions for payment gateways."""

    ZERO_DECIMAL_CURRENCIES = {
        "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW",
        "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
    }

    THREE_DECIMAL_CURRENCIES = {
        "BHD", "JOD", "KWD", "OMR", "TND",
    }

    @classmethod
    def audit_amount_to_units(cls, currency: str, amount: float | str) -> CurrencyPrecisionCheck:
        """Convert standard currency amount to smallest integer units (e.g. cents) and check for truncation."""
        curr = currency.upper().strip()
        dec_amount = Decimal(str(amount))

        is_zero = curr in cls.ZERO_DECIMAL_CURRENCIES
        is_three = curr in cls.THREE_DECIMAL_CURRENCIES

        if is_zero:
            multiplier = Decimal("1")
            expected_units = int(dec_amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            loss = float(dec_amount - expected_units)
            hazard = (dec_amount % 1 != 0)
            rec = "Zero-decimal currency: Amount must be an integer (e.g. ¥1000 = 1000, not 100000)."
        elif is_three:
            multiplier = Decimal("1000")
            units_raw = dec_amount * multiplier
            expected_units = int(units_raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            loss = float(units_raw - expected_units)
            hazard = (units_raw % 1 != 0)
            rec = "Three-decimal currency: Multiply by 1000 for smallest units."
        else:
            # Standard two-decimal currency (USD, EUR, IDR in gateway APIs)
            multiplier = Decimal("100")
            units_raw = dec_amount * multiplier
            expected_units = int(units_raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            loss = float(units_raw - expected_units)
            # Rounding hazard occurs if fractional cents were present (e.g. 10.555)
            hazard = (units_raw % 1 != 0)
            rec = "Two-decimal currency: Multiply by 100. Ensure no fractional cents exist."

        return CurrencyPrecisionCheck(
            currency=curr,
            input_amount=float(amount),
            expected_integer_units=expected_units,
            is_zero_decimal=is_zero,
            is_three_decimal=is_three,
            potential_truncation_loss=abs(loss),
            has_rounding_hazard=hazard,
            recommendation=rec,
        )

    @classmethod
    def test_rounding_edge_cases(cls, currency: str = "USD") -> list[CurrencyPrecisionCheck]:
        """Audit common fractional rounding edge cases."""
        test_amounts = [10.00, 10.55, 10.554, 10.555, 10.559, 1000.0, 1000.49]
        return [cls.audit_amount_to_units(currency, a) for a in test_amounts]
