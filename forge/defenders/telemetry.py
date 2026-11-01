"""forge.defenders.telemetry - Subnet, ASN distribution, and telemetry entropy auditor.

Evaluates bot detection indicators:
1. ASN and Subnet (/24 CIDR) concentration across multiple requests or proxy fleets.
2. Inter-request timing entropy (jitter, cadence variance) to detect metronomic bot signatures.
"""
from __future__ import annotations

import ipaddress
import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class EgressDistributionReport:
    total_samples: int
    unique_asns: int
    unique_subnets_c: int  # /24 CIDR blocks
    is_concentrated_asn: bool
    is_concentrated_subnet: bool
    risk_score: int
    findings: list[str]


@dataclass
class TimingEntropyReport:
    sample_count: int
    mean_interval_sec: float
    stdev_interval_sec: float
    coefficient_of_variation: float
    is_metronomic_bot: bool
    entropy_rating: str  # NATURAL_HUMAN, SUSPICIOUS_JITTER, BOT_METRONOME
    risk_score: int


class BotTelemetryAuditor:
    """Audits network egress clustering and behavioral timing entropy."""

    @staticmethod
    def audit_egress_distribution(
        ip_list: list[str],
        asn_list: Optional[list[str]] = None,
    ) -> EgressDistributionReport:
        """Audit whether IP addresses are clustered in identical /24 subnets or ASNs."""
        clean_ips = [ip.strip() for ip in ip_list if ip and ip.strip()]
        if not clean_ips:
            return EgressDistributionReport(
                total_samples=0, unique_asns=0, unique_subnets_c=0,
                is_concentrated_asn=False, is_concentrated_subnet=False,
                risk_score=0, findings=["No IP samples provided"]
            )

        subnets_c = set()
        for ip_str in clean_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj.version == 4:
                    # /24 network
                    net = ipaddress.ip_network(f"{ip_str}/24", strict=False)
                    subnets_c.add(str(net))
                else:
                    # /48 IPv6
                    net = ipaddress.ip_network(f"{ip_str}/48", strict=False)
                    subnets_c.add(str(net))
            except ValueError:
                pass

        asns = set(asn_list) if asn_list else set()
        findings = []
        score = 0

        # Subnet concentration analysis
        total = len(clean_ips)
        subnet_count = len(subnets_c)
        is_subnet_concentrated = (total >= 4 and subnet_count <= max(1, total // 3))

        if is_subnet_concentrated:
            score += 45
            findings.append(f"Subnet clustering detected: {total} IPs originate from only {subnet_count} CIDR blocks")
        else:
            findings.append(f"Healthy subnet dispersion: {total} IPs across {subnet_count} distinct CIDR blocks")

        # ASN concentration analysis
        is_asn_concentrated = False
        if asns:
            asn_count = len(asns)
            is_asn_concentrated = (total >= 5 and asn_count == 1)
            if is_asn_concentrated:
                score += 35
                findings.append(f"Single ASN bottleneck: All {total} requests originate from ASN {list(asns)[0]}")

        return EgressDistributionReport(
            total_samples=total,
            unique_asns=len(asns),
            unique_subnets_c=subnet_count,
            is_concentrated_asn=is_asn_concentrated,
            is_concentrated_subnet=is_subnet_concentrated,
            risk_score=min(100, score),
            findings=findings,
        )

    @staticmethod
    def audit_timing_entropy(intervals_sec: list[float]) -> TimingEntropyReport:
        """Audit inter-request arrival intervals to detect bot-like metronomic patterns."""
        if len(intervals_sec) < 3:
            return TimingEntropyReport(
                sample_count=len(intervals_sec),
                mean_interval_sec=0.0,
                stdev_interval_sec=0.0,
                coefficient_of_variation=0.0,
                is_metronomic_bot=False,
                entropy_rating="INSUFFICIENT_DATA",
                risk_score=0,
            )

        mean_val = statistics.mean(intervals_sec)
        stdev_val = statistics.stdev(intervals_sec)
        cv = (stdev_val / mean_val) if mean_val > 0 else 0.0

        # Low coefficient of variation (< 0.10) signifies rigid timer / loop without human jitter
        if cv < 0.08:
            rating = "BOT_METRONOME"
            is_bot = True
            score = 60
        elif cv < 0.25:
            rating = "SUSPICIOUS_JITTER"
            is_bot = False
            score = 25
        else:
            rating = "NATURAL_HUMAN"
            is_bot = False
            score = 0

        return TimingEntropyReport(
            sample_count=len(intervals_sec),
            mean_interval_sec=round(mean_val, 3),
            stdev_interval_sec=round(stdev_val, 3),
            coefficient_of_variation=round(cv, 4),
            is_metronomic_bot=is_bot,
            entropy_rating=rating,
            risk_score=score,
        )
