"""forge.payments.decline_codes - ISO 8583 and gateway decline code taxonomy.

Provides deterministic categorization and remediation advice for payment responses:
- HARD_DECLINE (terminal: stolen, closed, invalid)
- SOFT_DECLINE (retryable: insufficient funds, rate limit, issuer timeout)
- SCA_REQUIRED (actionable: 3DS/Strong Customer Authentication needed)
- CONFIG_ERROR (integration: currency mismatch, invalid API version)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class DeclineAnalysis:
    code: str
    category: str  # HARD_DECLINE, SOFT_DECLINE, SCA_REQUIRED, CONFIG_ERROR, UNKNOWN
    is_retryable: bool
    iso_8583_equivalent: str
    description: str
    recommended_action: str


class DeclineCodeTaxonomy:
    """Standardized mapper and evaluator for gateway and issuer decline codes."""

    CAT_HARD = "HARD_DECLINE"
    CAT_SOFT = "SOFT_DECLINE"
    CAT_SCA = "SCA_REQUIRED"
    CAT_CONFIG = "CONFIG_ERROR"

    CODES: dict[str, dict[str, Any]] = {
        # Strong Customer Authentication / 3DS
        "authentication_required": {
            "category": CAT_SCA,
            "retryable": False,
            "iso": "65",
            "desc": "Issuer requires Strong Customer Authentication (SCA/3DS)",
            "action": "Trigger 3DS challenge flow via PaymentIntent.confirm or NextAction handler",
        },
        "3d_secure_authentication_failed": {
            "category": CAT_HARD,
            "retryable": False,
            "iso": "05",
            "desc": "Cardholder failed or abandoned the 3DS authentication challenge",
            "action": "Prompt customer for alternative payment method",
        },

        # Soft Declines (Retryable)
        "insufficient_funds": {
            "category": CAT_SOFT,
            "retryable": True,
            "iso": "51",
            "desc": "Card has insufficient limit or account balance",
            "action": "Advise cardholder or retry with alternative payment instrument",
        },
        "try_again_later": {
            "category": CAT_SOFT,
            "retryable": True,
            "iso": "19",
            "desc": "Temporary communication or network outage with card issuer",
            "action": "Retry request using exponential backoff with jitter",
        },
        "processing_error": {
            "category": CAT_SOFT,
            "retryable": True,
            "iso": "96",
            "desc": "System malfunction occurred during card network transmission",
            "action": "Retry with identical Idempotency-Key",
        },
        "card_velocity_exceeded": {
            "category": CAT_SOFT,
            "retryable": True,
            "iso": "65",
            "desc": "Activity limit exceeded for this card within velocity window",
            "action": "Delay subsequent attempts until velocity window resets",
        },

        # Hard Declines (Non-retryable)
        "card_declined": {
            "category": CAT_HARD,
            "retryable": False,
            "iso": "05",
            "desc": "Generic Do Not Honor from card issuer",
            "action": "Customer must contact their issuing bank for authorization details",
        },
        "stolen_card": {
            "category": CAT_HARD,
            "retryable": False,
            "iso": "43",
            "desc": "Card reported stolen; issuer requests confiscation/blocking",
            "action": "Block card locally and terminate retry attempts immediately",
        },
        "lost_card": {
            "category": CAT_HARD,
            "retryable": False,
            "iso": "41",
            "desc": "Card reported lost by cardholder",
            "action": "Block card locally; do not retry",
        },
        "expired_card": {
            "category": CAT_HARD,
            "retryable": False,
            "iso": "54",
            "desc": "Card has passed its expiration date",
            "action": "Prompt customer for updated expiration date or reissued card",
        },
        "incorrect_cvc": {
            "category": CAT_HARD,
            "retryable": False,
            "iso": "82",
            "desc": "Card verification code does not match issuer records",
            "action": "Prompt user to re-enter the 3 or 4 digit security code",
        },
        "incorrect_number": {
            "category": CAT_HARD,
            "retryable": False,
            "iso": "14",
            "desc": "Card PAN does not exist in issuer account range",
            "action": "Validate Luhn format and prompt customer to re-enter card number",
        },

        # Configuration / Integration Errors
        "currency_not_supported": {
            "category": CAT_CONFIG,
            "retryable": False,
            "iso": "58",
            "desc": "Target currency code is not enabled on merchant account",
            "action": "Verify supported currencies in gateway dashboard configuration",
        },
    }

    @classmethod
    def analyze(cls, raw_code: str) -> DeclineAnalysis:
        norm = (raw_code or "").lower().strip()
        meta = cls.CODES.get(norm)
        if not meta:
            # Fallback evaluation based on keywords
            if "fund" in norm:
                cat, retry, iso = cls.CAT_SOFT, True, "51"
            elif "auth" in norm:
                cat, retry, iso = cls.CAT_SCA, False, "65"
            else:
                cat, retry, iso = "UNKNOWN", False, "05"

            return DeclineAnalysis(
                code=norm or "unknown",
                category=cat,
                is_retryable=retry,
                iso_8583_equivalent=iso,
                description=f"Uncataloged decline reason: {norm}",
                recommended_action="Inspect raw gateway error payload for details",
            )

        return DeclineAnalysis(
            code=norm,
            category=meta["category"],
            is_retryable=meta["retryable"],
            iso_8583_equivalent=meta["iso"],
            description=meta["desc"],
            recommended_action=meta["action"],
        )
