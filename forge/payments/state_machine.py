"""forge.payments.state_machine - Modern PaymentIntent state machine & next_action evaluator.

Provides compliant parsing and tracking of modern payment lifecycle states:
- requires_payment_method
- requires_confirmation
- requires_action (evaluates 3DS next_action metadata)
- processing
- succeeded / requires_capture
- canceled / failed
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from forge.payments.decline_codes import DeclineAnalysis, DeclineCodeTaxonomy


@dataclass
class NextActionInspection:
    action_type: str
    is_3ds: bool
    redirect_url: Optional[str] = None
    three_ds_method_url: Optional[str] = None
    server_trans_id: Optional[str] = None
    requires_user_interaction: bool = False
    details: Optional[dict[str, Any]] = None


class PaymentStateMachine:
    """Evaluates and transitions payment lifecycle states compliant with modern gateways."""

    VALID_STATES = {
        "requires_payment_method",
        "requires_confirmation",
        "requires_action",
        "processing",
        "requires_capture",
        "succeeded",
        "canceled",
    }

    # Card-rail vocabulary for a transaction snapshot. The snapshot is taken at
    # authorization time, so it never propagates a card past "authorized".
    RAIL_STATES: tuple = ("authorized", "captured", "cleared", "settled", "action_required", "failed")

    @classmethod
    def rails_state(cls, final_disposition: str, funding: str = "") -> str:
        """Map a funnel final disposition to a card-rail state.

        Exact precedence:
          "AUTHORIZED"               -> "authorized"  (snapshot; funding is NOT consulted)
          "CHALLENGE_3DS"            -> "action_required"
          startswith("REJECTED_BY_") -> "failed"
          anything else              -> "unknown"
        funding is accepted because the funnel calls with it, but it must never
        change the result — capture/clearing/settlement happen after the snapshot.
        """
        if final_disposition == "AUTHORIZED":
            return "authorized"
        if final_disposition == "CHALLENGE_3DS":
            return "action_required"
        if final_disposition.startswith("REJECTED_BY_"):
            return "failed"
        return "unknown"

    @classmethod
    def state_for_decline(cls, analysis: DeclineAnalysis) -> str:
        """Map a decline analysis category to a card-rail state."""
        if analysis.category == DeclineCodeTaxonomy.CAT_SCA:
            return "action_required"
        return "failed"

    @staticmethod
    def parse_next_action(next_action: dict[str, Any]) -> NextActionInspection:
        """Inspect and categorize payment next_action payloads without executing unauthorized actions."""
        if not next_action or not isinstance(next_action, dict):
            return NextActionInspection(action_type="none", is_3ds=False)

        action_type = next_action.get("type", "unknown")
        is_3ds = False
        redirect_url = None
        method_url = None
        trans_id = None
        requires_user = False

        if action_type == "use_stripe_sdk":
            is_3ds = True
            sdk_data = next_action.get("use_stripe_sdk") or {}
            method_url = sdk_data.get("three_ds_method_url")
            trans_id = sdk_data.get("three_ds_server_trans_id") or sdk_data.get("three_ds_2_server_trans_id")
            # In SDK mode, if method_url alone is provided it's fingerprinting; challenge requires modal
            requires_user = "three_ds_2_challenge" in str(sdk_data)

        elif action_type == "redirect_to_url":
            is_3ds = True
            redirect_url = next_action.get("redirect_to_url", {}).get("url")
            requires_user = True

        elif action_type == "verify_with_microdeposits":
            requires_user = True

        return NextActionInspection(
            action_type=action_type,
            is_3ds=is_3ds,
            redirect_url=redirect_url,
            three_ds_method_url=method_url,
            server_trans_id=trans_id,
            requires_user_interaction=requires_user,
            details=next_action,
        )

    @classmethod
    def evaluate_response(cls, response_data: dict[str, Any]) -> dict[str, Any]:
        """Evaluate gateway API response, extract lifecycle status, and inspect next actions."""
        status = response_data.get("status") or response_data.get("state") or "unknown"
        intent_id = response_data.get("id") or "unknown"
        client_secret = response_data.get("client_secret")

        next_action_raw = response_data.get("next_action")
        inspection = cls.parse_next_action(next_action_raw) if next_action_raw else None

        terminal = status in {"succeeded", "canceled", "requires_capture"}
        action_required = (status == "requires_action")

        return {
            "intent_id": intent_id,
            "status": status,
            "is_terminal": terminal,
            "action_required": action_required,
            "client_secret_present": bool(client_secret),
            "next_action": inspection.__dict__ if inspection else None,
        }
