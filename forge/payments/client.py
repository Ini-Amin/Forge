"""forge.payments.client - Target-agnostic modern PaymentIntent test client.

Provides an end-to-end integration harness for testers, developers, and defenders:
- Target-agnostic: operates against any compliant staging, mock, or custom payment gateway.
- Enforces RFC 4122 Idempotency-Key headers on all state-changing operations.
- Intercepts and parses modern PaymentIntent states and next_action 3DS metadata.
- Integrates with decline code analysis for clear remediation advice.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from forge.payments.decline_codes import DeclineAnalysis, DeclineCodeTaxonomy
from forge.payments.idempotency import IdempotencyManager
from forge.payments.state_machine import PaymentStateMachine
from forge.transport.session import TLSSession


class PaymentGatewayClient:
    """Standardized client for evaluating PaymentIntent lifecycles and response payloads."""

    def __init__(
        self,
        base_url: str,
        api_token: Optional[str] = None,
        proxy_url: Optional[str] = None,
        strict_proxy: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.proxy_url = proxy_url
        self.strict_proxy = strict_proxy
        self.idempotency = IdempotencyManager()

    def _get_headers(self, idempotency_key: Optional[str] = None, endpoint: str = "") -> dict[str, str]:
        headers = self.idempotency.get_headers(key=idempotency_key, endpoint=endpoint)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Accept"] = "application/json"
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}" if not self.api_token.startswith("Bearer ") else self.api_token
        return headers

    def create_payment_method(
        self,
        card: dict[str, Any],
        billing: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Submit a PaymentMethod creation request."""
        endpoint = f"{self.base_url}/v1/payment_methods"
        headers = self._get_headers(idempotency_key, endpoint=endpoint)

        payload = {
            "type": "card",
            "card[number]": card["pan"],
            "card[exp_month]": card["mm"],
            "card[exp_year]": card["yy"],
            "card[cvc]": card["cvv"],
        }
        if billing:
            if "name" in billing:
                payload["billing_details[name]"] = billing["name"]
            if "address" in billing:
                payload["billing_details[address][line1]"] = billing["address"]
            if "city" in billing:
                payload["billing_details[address][city]"] = billing["city"]
            if "state" in billing:
                payload["billing_details[address][state]"] = billing["state"]
            if "zip" in billing:
                payload["billing_details[address][postal_code]"] = billing["zip"]
            if "country" in billing:
                payload["billing_details[address][country]"] = billing["country"]

        with TLSSession(self.proxy_url, strict_proxy=self.strict_proxy) as session:
            resp = session.post(endpoint, data=payload, headers=headers)
            try:
                data = resp.json()
            except Exception:
                data = {"raw_text": resp.text, "status_code": resp.status_code}
            return data

    def confirm_payment_intent(
        self,
        intent_id: str,
        payment_method_id: str,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Confirm a PaymentIntent with the given PaymentMethod."""
        endpoint = f"{self.base_url}/v1/payment_intents/{intent_id}/confirm"
        headers = self._get_headers(idempotency_key, endpoint=endpoint)
        payload = {"payment_method": payment_method_id}

        with TLSSession(self.proxy_url, strict_proxy=self.strict_proxy) as session:
            resp = session.post(endpoint, data=payload, headers=headers)
            try:
                data = resp.json()
            except Exception:
                data = {"raw_text": resp.text, "status_code": resp.status_code}
            return data

    @staticmethod
    def inspect_state(response_payload: dict[str, Any]) -> dict[str, Any]:
        """Analyze lifecycle state and next_action requirements from response."""
        return PaymentStateMachine.evaluate_response(response_payload)

    @staticmethod
    def analyze_decline(error_payload: dict[str, Any]) -> DeclineAnalysis:
        """Extract and categorize error/decline code from failure payload."""
        err = error_payload.get("error", error_payload)
        code = err.get("decline_code") or err.get("code") or "unknown"
        return DeclineCodeTaxonomy.analyze(code)
