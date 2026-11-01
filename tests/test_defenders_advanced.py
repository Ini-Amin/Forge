"""Unit tests for advanced defensive simulation, funnel modeling, and maturity metrics."""
import unittest

from forge.defenders.currency import CurrencyPrecisionAuditor
from forge.defenders.funnel import TransactionFunnelSimulator
from forge.defenders.metrics import DefenseMaturityEvaluator
from forge.defenders.telemetry import BotTelemetryAuditor


class TestAdvancedDefenders(unittest.TestCase):
    def test_funnel_simulator_clean(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            "Idempotency-Key": "test_uuid_123",
        }
        identity = {"country": "US", "name": "John Doe", "address": "123 Main St", "zip": "10001"}
        card_meta = {"country": "US", "issuer": "Chase"}
        egress_meta = {"country": "US", "asn_type": "residential"}
        tls_profile = {
            "impersonate": "firefox135",
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
        }

        res = TransactionFunnelSimulator.evaluate(headers, identity, card_meta, egress_meta, tls_profile)
        self.assertEqual(res.final_disposition, "SETTLED")
        self.assertEqual(res.total_risk_score, 0)
        self.assertEqual(len(res.layers), 4)
        for l in res.layers:
            self.assertEqual(l.verdict, "PASS")

    def test_funnel_simulator_vulnerabilities(self):
        # Missing Idempotency-Key + Mismatched UA/TLS
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            # missing Idempotency-Key
        }
        identity = {"country": "US", "name": "John Doe", "address": "123 Main St", "zip": "10001"}
        card_meta = {"country": "JP", "issuer": "JCB"}  # Card mismatch
        egress_meta = {"country": "US", "asn_type": "datacenter"}
        tls_profile = {
            "impersonate": "chrome136",  # Mismatch with Firefox UA
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
        }

        res = TransactionFunnelSimulator.evaluate(headers, identity, card_meta, egress_meta, tls_profile)
        self.assertGreater(res.total_risk_score, 50)
        self.assertTrue(len(res.vulnerabilities_detected) > 0)
        self.assertTrue(any("Idempotency-Key" in v for v in res.vulnerabilities_detected))

    def test_currency_auditor(self):
        # Zero decimal: JPY
        jpy = CurrencyPrecisionAuditor.audit_amount_to_units("JPY", 1500)
        self.assertEqual(jpy.expected_integer_units, 1500)
        self.assertTrue(jpy.is_zero_decimal)
        self.assertFalse(jpy.has_rounding_hazard)

        # Standard two decimal: USD
        usd = CurrencyPrecisionAuditor.audit_amount_to_units("USD", 10.55)
        self.assertEqual(usd.expected_integer_units, 1055)
        self.assertFalse(usd.is_zero_decimal)
        self.assertFalse(usd.has_rounding_hazard)

        # Rounding hazard: USD fractional cents
        usd_frac = CurrencyPrecisionAuditor.audit_amount_to_units("USD", 10.555)
        self.assertEqual(usd_frac.expected_integer_units, 1056)
        self.assertTrue(usd_frac.has_rounding_hazard)

    def test_telemetry_subnet_clustering(self):
        # Clustered /24 IPs
        clustered = ["192.168.1.10", "192.168.1.20", "192.168.1.30", "192.168.1.40", "192.168.1.50"]
        report = BotTelemetryAuditor.audit_egress_distribution(clustered)
        self.assertTrue(report.is_concentrated_subnet)
        self.assertGreater(report.risk_score, 0)

        # Dispersed IPs
        dispersed = ["10.1.1.1", "10.2.2.2", "10.3.3.3", "10.4.4.4", "10.5.5.5"]
        report_ok = BotTelemetryAuditor.audit_egress_distribution(dispersed)
        self.assertFalse(report_ok.is_concentrated_subnet)
        self.assertEqual(report_ok.risk_score, 0)

    def test_telemetry_timing_entropy(self):
        # Metronomic timing (rigid intervals around 1.0s)
        metronome = [1.001, 1.002, 1.000, 1.001, 1.003, 1.000]
        rep_bot = BotTelemetryAuditor.audit_timing_entropy(metronome)
        self.assertTrue(rep_bot.is_metronomic_bot)
        self.assertEqual(rep_bot.entropy_rating, "BOT_METRONOME")

        # Natural human jitter (varying intervals)
        human = [0.8, 2.4, 1.1, 4.5, 0.5, 3.2]
        rep_human = BotTelemetryAuditor.audit_timing_entropy(human)
        self.assertFalse(rep_human.is_metronomic_bot)
        self.assertEqual(rep_human.entropy_rating, "NATURAL_HUMAN")

    def test_defense_maturity_metrics(self):
        matrix = DefenseMaturityEvaluator.calculate_confusion_matrix(tp=90, tn=900, fp=10, fn=10)
        self.assertAlmostEqual(matrix.false_positive_rate, 10 / 910, places=3)
        self.assertAlmostEqual(matrix.false_negative_rate, 10 / 100, places=3)

        lat = DefenseMaturityEvaluator.benchmark_latency([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        self.assertEqual(lat.p50_ms, 50.0)
        self.assertEqual(lat.p95_ms, 100.0)

        log_complete = {
            "transaction_id": "tx_123", "timestamp_utc": "2026-11-01T00:00:00Z",
            "client_ip": "1.2.3.4", "egress_asn": "AS123", "tls_ja4_fingerprint": "ja4_hash",
            "avs_code": "Y", "cvv_result": "match", "iso_8583_response_code": "00",
            "decision": "ALLOW", "rule_id": "rule_1",
        }
        audit_res = DefenseMaturityEvaluator.audit_trail_completeness(log_complete)
        self.assertEqual(audit_res.completeness_percentage, 100.0)
        self.assertEqual(len(audit_res.missing_critical_fields), 0)


if __name__ == "__main__":
    unittest.main()
