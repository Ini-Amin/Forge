"""forge.defenders.fraud_audit - Fraud risk scoring & telemetry audit engine.

Enables defenders to evaluate and calibrate fraud detection rulesets against:
1. AVS (Address Verification System) consistency between billing address and card issuer.
2. Geo-IP location vs. Billing address proximity and country mismatch.
3. ClientHello TLS fingerprint (JA4) vs. HTTP User-Agent cross-consistency.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class FraudRiskAuditor:
    """Evaluates synthetic transaction telemetry against standard fraud scoring heuristics."""

    @staticmethod
    def audit_avs(identity: dict[str, Any], card_meta: dict[str, Any]) -> dict[str, Any]:
        """Evaluate Address Verification System (AVS) alignment."""
        card_country = card_meta.get("country", "US")
        id_country = identity.get("country", "US")

        country_match = (card_country == id_country)
        has_street = bool(identity.get("address"))
        has_zip = bool(identity.get("zip"))

        score = 0
        reasons = []

        if not country_match:
            score += 45
            reasons.append(f"Country mismatch: Card issued in {card_country}, billing in {id_country}")
        if not has_street:
            score += 25
            reasons.append("Missing billing street address")
        if not has_zip:
            score += 20
            reasons.append("Missing billing postal code")

        # Standard AVS outcome mapping
        if country_match and has_street and has_zip:
            avs_code = "Y"  # Street address and 5-digit postal code match
        elif country_match and has_zip:
            avs_code = "Z"  # 5-digit postal code matches only
        elif country_match and has_street:
            avs_code = "A"  # Street address matches only
        else:
            avs_code = "N"  # No address or postal code match

        return {
            "avs_code": avs_code,
            "risk_penalty": score,
            "reasons": reasons,
            "passed": score < 30,
        }

    @staticmethod
    def audit_geo_egress(identity: dict[str, Any], exit_meta: dict[str, Any]) -> dict[str, Any]:
        """Evaluate Geo-IP network egress vs Billing identity coherence."""
        id_country = identity.get("country", "US").upper()
        exit_country = exit_meta.get("country", "").upper()

        score = 0
        reasons = []

        if not exit_country:
            score += 15
            reasons.append("Egress country undetermined or private network")
        elif id_country != exit_country:
            score += 40
            reasons.append(f"Geo-IP mismatch: IP originates in {exit_country}, billing in {id_country}")

        return {
            "identity_country": id_country,
            "egress_country": exit_country,
            "risk_penalty": score,
            "reasons": reasons,
            "coherent": score == 0,
        }

    @staticmethod
    def audit_fingerprint(profile: dict[str, Any]) -> dict[str, Any]:
        """Audit User-Agent vs ClientHello TLS impersonation consistency."""
        ua = profile.get("ua", "")
        impersonate = profile.get("impersonate", "")
        sec_ch_ua = profile.get("sec_ch_ua")

        anomalies = []
        score = 0

        # Check browser engine consistency
        if "Firefox" in ua and "firefox" not in impersonate:
            score += 60
            anomalies.append(f"Engine mismatch: UA indicates Firefox but TLS profile is {impersonate}")
        if "Chrome" in ua and "chrome" not in impersonate and "safari" not in impersonate:
            score += 60
            anomalies.append(f"Engine mismatch: UA indicates Chrome but TLS profile is {impersonate}")

        # Client Hints audit (Firefox and Safari should not send sec-ch-ua)
        if ("firefox" in impersonate or "safari" in impersonate) and sec_ch_ua is not None:
            score += 30
            anomalies.append("Header anomaly: Non-Chromium profile transmitting Chromium Client Hints (sec-ch-ua)")

        return {
            "tls_profile": impersonate,
            "risk_penalty": score,
            "anomalies": anomalies,
            "consistent": score == 0,
        }

    @classmethod
    def full_audit(
        cls,
        identity: dict[str, Any],
        card_meta: dict[str, Any],
        exit_meta: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Perform comprehensive fraud risk analysis for a complete transaction fixture."""
        avs = cls.audit_avs(identity, card_meta)
        geo = cls.audit_geo_egress(identity, exit_meta)
        fp = cls.audit_fingerprint(profile)

        total_risk_score = avs["risk_penalty"] + geo["risk_penalty"] + fp["risk_penalty"]
        total_risk_score = min(100, total_risk_score)

        if total_risk_score < 25:
            decision = "ALLOW"
            frictionless_eligible = True
        elif total_risk_score < 60:
            decision = "CHALLENGE_3DS"
            frictionless_eligible = False
        else:
            decision = "BLOCK"
            frictionless_eligible = False

        return {
            "total_risk_score": total_risk_score,
            "radar_decision": decision,
            "frictionless_eligible": frictionless_eligible,
            "components": {
                "avs": avs,
                "geo_egress": geo,
                "fingerprint": fp,
            },
        }
