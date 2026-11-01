"""forge.defenders.metrics - Defense Maturity Metrics & Audit Trail Evaluator.

Provides empirical benchmarking for fraud and security engineering teams:
1. False Positive Rate (FPR) vs. False Negative Rate (FNR) matrix.
2. Latency percentiles (p50, p95, p99) across defense layers.
3. Audit Trail Completeness index for forensic compliance.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ConfusionMatrixReport:
    true_positives: int    # Malicious correctly challenged/blocked
    true_negatives: int    # Legitimate correctly allowed
    false_positives: int   # Legitimate mistakenly challenged/blocked (conversion loss)
    false_negatives: int   # Malicious mistakenly allowed (fraud loss)
    false_positive_rate: float
    false_negative_rate: float
    precision: float
    recall: float
    f1_score: float
    business_impact_summary: str


@dataclass
class LatencyPercentileReport:
    sample_count: int
    min_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    is_checkout_degraded: bool  # True if p95 > 500ms


@dataclass
class AuditTrailCompletenessReport:
    total_fields_required: int
    fields_present: int
    completeness_percentage: float
    missing_critical_fields: list[str]
    compliance_grade: str  # A, B, C, F


class DefenseMaturityEvaluator:
    """Calculates quantitative security and operational maturity metrics."""

    @staticmethod
    def calculate_confusion_matrix(
        tp: int, tn: int, fp: int, fn: int
    ) -> ConfusionMatrixReport:
        """Compute error rates and conversion vs. fraud impact tradeoffs."""
        total_legit = tn + fp
        total_malicious = tp + fn

        fpr = (fp / total_legit) if total_legit > 0 else 0.0
        fnr = (fn / total_malicious) if total_malicious > 0 else 0.0

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        if fpr > 0.05:
            impact = f"CRITICAL CONVERSION RISK: FPR is {fpr:.1%}. Legitimate customers are being falsely declined."
        elif fnr > 0.10:
            impact = f"HIGH FRAUD EXPOSURE: FNR is {fnr:.1%}. More than 10% of malicious attempts are slipping through."
        else:
            impact = "BALANCED: Low FPR and acceptable fraud capture rate."

        return ConfusionMatrixReport(
            true_positives=tp,
            true_negatives=tn,
            false_positives=fp,
            false_negatives=fn,
            false_positive_rate=round(fpr, 4),
            false_negative_rate=round(fnr, 4),
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1, 4),
            business_impact_summary=impact,
        )

    @staticmethod
    def benchmark_latency(latencies_ms: list[float]) -> LatencyPercentileReport:
        """Compute p50, p95, p99 latency percentiles for the defense evaluation pipeline."""
        if not latencies_ms:
            return LatencyPercentileReport(0, 0, 0, 0, 0, 0, 0, False)

        sorted_lat = sorted(latencies_ms)
        n = len(sorted_lat)

        def _percentile(p: float) -> float:
            idx = int(math.ceil(p * n)) - 1
            return sorted_lat[max(0, min(n - 1, idx))]

        p50 = _percentile(0.50)
        p95 = _percentile(0.95)
        p99 = _percentile(0.99)
        mean_val = statistics.mean(sorted_lat)

        return LatencyPercentileReport(
            sample_count=n,
            min_ms=round(sorted_lat[0], 2),
            p50_ms=round(p50, 2),
            p95_ms=round(p95, 2),
            p99_ms=round(p99, 2),
            max_ms=round(sorted_lat[-1], 2),
            mean_ms=round(mean_val, 2),
            is_checkout_degraded=(p95 > 500.0),
        )

    @staticmethod
    def audit_trail_completeness(log_entry: dict[str, Any]) -> AuditTrailCompletenessReport:
        """Verify whether an event log captures mandatory forensic and regulatory parameters."""
        mandatory_fields = [
            "transaction_id",
            "timestamp_utc",
            "client_ip",
            "egress_asn",
            "tls_ja4_fingerprint",
            "avs_code",
            "cvv_result",
            "iso_8583_response_code",
            "decision",
            "rule_id",
        ]

        missing = [f for f in mandatory_fields if not log_entry.get(f)]
        present = len(mandatory_fields) - len(missing)
        pct = (present / len(mandatory_fields)) * 100.0

        if pct >= 95.0:
            grade = "A (Forensically Sound)"
        elif pct >= 80.0:
            grade = "B (Acceptable)"
        elif pct >= 60.0:
            grade = "C (Significant Forensic Blindspots)"
        else:
            grade = "F (Non-Compliant / Audit Failure)"

        return AuditTrailCompletenessReport(
            total_fields_required=len(mandatory_fields),
            fields_present=present,
            completeness_percentage=round(pct, 1),
            missing_critical_fields=missing,
            compliance_grade=grade,
        )
