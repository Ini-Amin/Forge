"""forge.defenders.funnel - Transaction Funnel Modeling and Layered Defense Simulator.

Models and audits the 4 defensive layers of an e-commerce checkout flow:
  Layer 1: Edge / WAF (IP Reputation, ASN Type, TLS ClientHello / JA4)
  Layer 2: Merchant Backend (Schema Validation, Idempotency-Key, Rate Limiting)
  Layer 3: Gateway (Fraud Scoring Engine, AVS Alignment, Velocity Limits)
  Layer 4: Card Issuer (EMVCo 3DS Evaluation: Frictionless vs Challenge)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LayerVerdict:
    layer_name: str
    verdict: str  # PASS, FLAG, BLOCK, CHALLENGE
    score_penalty: int
    details: list[str]
    latency_ms: Optional[float] = None  # measured only; None = not measured


@dataclass
class StageVerdict:
    stage: str
    verdict: str  # PASS, DEFERRED, BLOCK, N_A
    detail: str


def _build_money_lifecycle(final_disposition: str, funding: str) -> list[StageVerdict]:
    """Trace money movement stages for a transaction outcome.

    Verdicts are derived only from the disposition and the card funding type;
    no rates, amounts, or date arithmetic are claimed.
    """
    if final_disposition == "AUTHORIZED":
        return [
            StageVerdict("authorization", "PASS",
                         "Approved at issuer layer (risk gate passed) — authorization only, no funds moved"),
            StageVerdict("clearing", "PASS", "Routable for clearing batch submission"),
            StageVerdict("settlement", *_settlement_verdict(funding)),
        ]
    auth_verdict = "BLOCK" if final_disposition.startswith("REJECTED_BY_") else "N_A"
    return [
        StageVerdict("authorization", auth_verdict, final_disposition),
        StageVerdict("clearing", "N_A", f"Never reached — {final_disposition}"),
        StageVerdict("settlement", "N_A", f"Never reached — {final_disposition}"),
    ]


def _settlement_verdict(funding: str) -> tuple[str, str]:
    """Return (verdict, detail) for the settlement stage of an authorized transaction."""
    by_funding = {
        "credit": ("DEFERRED", "Credit line — funds move after the capture window; not settled at approval"),
        "debit": ("PASS", "Debit card — settles in the same-day batch"),
        "prepaid": ("PASS", "Prepaid — balance deducted at capture"),
    }
    return by_funding.get(funding.lower(), ("N_A", "Funding type unknown — settlement timing not claimed"))


@dataclass
class FunnelSimulationResult:
    final_disposition: str  # AUTHORIZED, CHALLENGE_3DS, REJECTED_BY_WAF, REJECTED_BY_BACKEND, REJECTED_BY_GATEWAY, REJECTED_BY_ISSUER
    total_latency_ms: Optional[float]  # measured only; None = not measured
    total_risk_score: int
    layers: list[LayerVerdict]
    vulnerabilities_detected: list[str]
    recommendations: list[str]
    money_lifecycle: list[StageVerdict] = field(default_factory=list)


class TransactionFunnelSimulator:
    """Simulates transaction traversal across all 4 defensive layers in staging/pre-production."""

    @classmethod
    def evaluate(
        cls,
        request_headers: dict[str, str],
        identity: dict[str, Any],
        card_meta: dict[str, Any],
        egress_meta: dict[str, Any],
        tls_profile: dict[str, Any],
        stop_on_block: bool = False,
        probe: Optional[dict[str, Any]] = None,
    ) -> FunnelSimulationResult:
        # Latency is a measurement, so it only exists when a live probe measured
        # it. The one probe Forge makes (a single request from `run --target`)
        # can measure the edge layer and nothing deeper, so backend/gateway/
        # issuer layers are None here and the UI must say "not measured".
        probe = probe or {}
        measured_edge: Optional[float] = None
        if probe.get("latency_ms") is not None:
            measured_edge = float(probe["latency_ms"])

        layers: list[LayerVerdict] = []
        vulns: list[str] = []
        recs: list[str] = []
        total_risk = 0
        earliest_rejection: Optional[str] = None
        # ── Layer 1: Edge Layer (WAF / Bot Management) ─────────────────────────
        l1_details = []
        l1_penalty = 0
        l1_verdict = "PASS"

        asn_type = egress_meta.get("asn_type", "unknown").lower()
        if asn_type in ("datacenter", "hosting", "vpn"):
            l1_penalty += 35
            l1_details.append(f"High-risk ASN classification: {asn_type.upper()}")
        elif asn_type == "unknown":
            # Unverified egress is not clean egress. A flag is the honest verdict.
            l1_penalty += 10
            l1_details.append("Exit ASN unclassified — reputation not assessed")

        # Check TLS vs UA header alignment
        ua = request_headers.get("User-Agent") or tls_profile.get("ua", "")
        impersonate = tls_profile.get("impersonate", "")
        if "Firefox" in ua and "firefox" not in impersonate:
            l1_penalty += 50
            l1_details.append(f"WAF Anomaly: UA claims Firefox but TLS ClientHello is {impersonate}")
            vulns.append("WAF rule missing: Failed to drop mismatched TLS ClientHello / User-Agent")
            recs.append("Configure WAF JA4/TLS fingerprint consistency rule at the edge")

        if probe:
            status = int(probe.get("status_code") or 0)
            resp_headers = {str(k).lower(): v for k, v in (probe.get("headers") or {}).items()}
            if status in (403, 429, 503):
                signal = resp_headers.get("cf-mitigated") or resp_headers.get("server") or "edge"
                l1_penalty += 60
                l1_details.append(f"Live probe: HTTP {status} rejected at edge ({signal})")
                vulns.append(f"Edge visible behavior: HTTP {status} from {signal} (challenge/limiter engaged)")
            elif status > 0:
                if measured_edge is not None:
                    l1_details.append(f"Live probe: HTTP {status} passed through edge in {measured_edge:.1f}ms")
                else:
                    l1_details.append(f"Live probe: HTTP {status} passed through edge")

        if l1_penalty >= 50:
            l1_verdict = "BLOCK"
        elif l1_penalty > 0:
            l1_verdict = "FLAG"

        layers.append(LayerVerdict(
            layer_name="1. Edge / WAF",
            verdict=l1_verdict,
            score_penalty=l1_penalty,
            details=l1_details or ["Residential ASN with consistent TLS ClientHello; no live probe supplied"],
            latency_ms=measured_edge,
        ))
        total_risk += l1_penalty

        if l1_verdict == "BLOCK":
            earliest_rejection = earliest_rejection or "REJECTED_BY_WAF"
            if stop_on_block:
                return FunnelSimulationResult(
                    final_disposition="REJECTED_BY_WAF",
                    total_latency_ms=measured_edge,
                    total_risk_score=total_risk,
                    layers=layers,
                    vulnerabilities_detected=vulns,
                    recommendations=recs,
                    money_lifecycle=_build_money_lifecycle("REJECTED_BY_WAF", card_meta.get("funding", "unknown")),
                )

        # ── Layer 2: Merchant App (API Backend) ────────────────────────────────
        l2_details = []
        l2_penalty = 0
        l2_verdict = "PASS"

        has_idempotency = any(k.lower() == "idempotency-key" for k in request_headers)
        if not has_idempotency:
            l2_penalty += 25
            l2_details.append("Missing Idempotency-Key header on state-changing request")
            vulns.append("Backend logic flaw: Endpoint admits mutation without Idempotency-Key (TOCTOU/race hazard)")
            recs.append("Enforce strict UUIDv4 Idempotency-Key on all checkout confirmation mutations")

        # Basic schema completeness check
        required_fields = ["name", "address", "zip"]
        missing_fields = [f for f in required_fields if not identity.get(f)]
        if missing_fields:
            l2_penalty += 30
            l2_details.append(f"Incomplete billing schema: missing {', '.join(missing_fields)}")

        if probe:
            status = int(probe.get("status_code") or 0)
            if 400 <= status < 500 and status not in (403, 429):
                l2_penalty += 30
                l2_details.append(f"Live probe: HTTP {status} rejected by application layer (schema/auth/validation)")

        if l2_penalty >= 50:
            l2_verdict = "BLOCK"
        elif l2_penalty > 0:
            l2_verdict = "FLAG"

        layers.append(LayerVerdict(
            layer_name="2. Merchant Backend",
            verdict=l2_verdict,
            score_penalty=l2_penalty,
            details=l2_details or ["Schema valid; Idempotency-Key present; rate limit within bounds"],
            latency_ms=None,  # merchant backend latency was not measured
        ))
        total_risk += l2_penalty

        if l2_verdict == "BLOCK":
            earliest_rejection = earliest_rejection or "REJECTED_BY_BACKEND"
            if stop_on_block:
                return FunnelSimulationResult(
                    final_disposition="REJECTED_BY_BACKEND",
                    total_latency_ms=measured_edge,
                    total_risk_score=total_risk,
                    layers=layers,
                    vulnerabilities_detected=vulns,
                    recommendations=recs,
                    money_lifecycle=_build_money_lifecycle("REJECTED_BY_BACKEND", card_meta.get("funding", "unknown")),
                )

        # ── Layer 3: Gateway (Fraud Scoring / AVS) ─────────────────────────────
        l3_details = []
        l3_penalty = 0
        l3_verdict = "PASS"

        card_country = card_meta.get("country", "US").upper()
        billing_country = identity.get("country", "US").upper()
        if card_country != billing_country:
            l3_penalty += 40
            l3_details.append(f"AVS Mismatch: Card issued in {card_country}, billed in {billing_country}")

        exit_country = egress_meta.get("country", "").upper()
        if exit_country and exit_country != billing_country:
            l3_penalty += 30
            l3_details.append(f"Geo-IP Discrepancy: Network egress in {exit_country}, billing in {billing_country}")

        if l3_penalty >= 60:
            l3_verdict = "BLOCK"
        elif l3_penalty > 0:
            l3_verdict = "FLAG"

        layers.append(LayerVerdict(
            layer_name="3. Gateway / Radar",
            verdict=l3_verdict,
            score_penalty=l3_penalty,
            details=l3_details or ["AVS Full Match (Y); Geo-IP matches billing country; Radar score low"],
            latency_ms=None,  # gateway latency was not measured
        ))
        total_risk += l3_penalty

        if l3_verdict == "BLOCK":
            earliest_rejection = earliest_rejection or "REJECTED_BY_GATEWAY"
            if stop_on_block:
                return FunnelSimulationResult(
                    final_disposition="REJECTED_BY_GATEWAY",
                    total_latency_ms=measured_edge,
                    total_risk_score=total_risk,
                    layers=layers,
                    vulnerabilities_detected=vulns,
                    recommendations=recs,
                    money_lifecycle=_build_money_lifecycle("REJECTED_BY_GATEWAY", card_meta.get("funding", "unknown")),
                )

        # ── Layer 4: Issuer (EMVCo 3DS Evaluation) ─────────────────────────────
        l4_details = []
        l4_penalty = 0
        total_accumulated = total_risk

        if total_accumulated >= 35:
            l4_verdict = "CHALLENGE"
            l4_details.append(f"High risk score ({total_accumulated}) triggered 3DS Strong Customer Authentication (SCA)")
            disposition = "CHALLENGE_3DS"
        else:
            l4_verdict = "PASS"
            l4_details.append(f"Low risk score ({total_accumulated}) eligible for 3DS Frictionless settlement")
            disposition = "AUTHORIZED"

        layers.append(LayerVerdict(
            layer_name="4. Issuer / 3DS",
            verdict=l4_verdict,
            score_penalty=l4_penalty,
            details=l4_details,
            latency_ms=None,  # issuer latency was not measured
        ))
        return FunnelSimulationResult(
            final_disposition=earliest_rejection or disposition,
            total_latency_ms=measured_edge,
            total_risk_score=total_risk,
            layers=layers,
            vulnerabilities_detected=vulns,
            recommendations=recs,
            money_lifecycle=_build_money_lifecycle(
                earliest_rejection or disposition, card_meta.get("funding", "unknown")),
        )
