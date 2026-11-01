"""Unit tests for PaymentStateMachine, DeclineCodeTaxonomy, and FraudRiskAuditor."""
import unittest

from forge.defenders.fraud_audit import FraudRiskAuditor
from forge.payments.decline_codes import DeclineCodeTaxonomy
from forge.payments.idempotency import IdempotencyManager
from forge.payments.state_machine import PaymentStateMachine


class TestPaymentsAndDefenders(unittest.TestCase):
    def test_decline_taxonomy(self):
        # 3DS / SCA required
        res_sca = DeclineCodeTaxonomy.analyze("authentication_required")
        self.assertEqual(res_sca.category, DeclineCodeTaxonomy.CAT_SCA)
        self.assertFalse(res_sca.is_retryable)
        self.assertEqual(res_sca.iso_8583_equivalent, "65")

        # Soft decline
        res_soft = DeclineCodeTaxonomy.analyze("insufficient_funds")
        self.assertEqual(res_soft.category, DeclineCodeTaxonomy.CAT_SOFT)
        self.assertTrue(res_soft.is_retryable)
        self.assertEqual(res_soft.iso_8583_equivalent, "51")

        # Hard decline
        res_hard = DeclineCodeTaxonomy.analyze("stolen_card")
        self.assertEqual(res_hard.category, DeclineCodeTaxonomy.CAT_HARD)
        self.assertFalse(res_hard.is_retryable)
        self.assertEqual(res_hard.iso_8583_equivalent, "43")

    def test_state_machine_next_action_eval(self):
        # 3DS2 SDK action
        next_action_sdk = {
            "type": "use_stripe_sdk",
            "use_stripe_sdk": {
                "three_ds_method_url": "https://acs.bank.com/method",
                "three_ds_server_trans_id": "trans_123",
            },
        }
        res_sdk = PaymentStateMachine.parse_next_action(next_action_sdk)
        self.assertTrue(res_sdk.is_3ds)
        self.assertEqual(res_sdk.three_ds_method_url, "https://acs.bank.com/method")
        self.assertEqual(res_sdk.server_trans_id, "trans_123")

        # Redirect 3DS1 action
        next_action_redirect = {
            "type": "redirect_to_url",
            "redirect_to_url": {"url": "https://hooks.stripe.com/redirect/123"},
        }
        res_redir = PaymentStateMachine.parse_next_action(next_action_redirect)
        self.assertTrue(res_redir.is_3ds)
        self.assertTrue(res_redir.requires_user_interaction)
        self.assertEqual(res_redir.redirect_url, "https://hooks.stripe.com/redirect/123")

    def test_payment_intent_lifecycle_evaluation(self):
        raw_resp = {
            "id": "pi_test_123",
            "status": "requires_action",
            "client_secret": "pi_test_123_secret_abc",
            "next_action": {
                "type": "redirect_to_url",
                "redirect_to_url": {"url": "https://acs.example.com/auth"},
            },
        }
        eval_res = PaymentStateMachine.evaluate_response(raw_resp)
        self.assertEqual(eval_res["intent_id"], "pi_test_123")
        self.assertEqual(eval_res["status"], "requires_action")
        self.assertTrue(eval_res["action_required"])
        self.assertFalse(eval_res["is_terminal"])
        self.assertTrue(eval_res["next_action"]["is_3ds"])

    def test_idempotency_headers(self):
        mgr = IdempotencyManager()
        h1 = mgr.get_headers(endpoint="/v1/payment_intents")
        h2 = mgr.get_headers(endpoint="/v1/payment_intents")
        self.assertIn("Idempotency-Key", h1)
        self.assertNotEqual(h1["Idempotency-Key"], h2["Idempotency-Key"])

    def test_fraud_risk_auditor(self):
        # Coherent US identity + US card + US egress
        id_us = {"country": "US", "address": "123 Main St", "zip": "10001"}
        card_us = {"country": "US"}
        exit_us = {"country": "US"}
        fp_chrome = {
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
            "impersonate": "chrome136",
            "sec_ch_ua": '"Chromium";v="136"',
        }

        audit = FraudRiskAuditor.full_audit(id_us, card_us, exit_us, fp_chrome)
        self.assertEqual(audit["total_risk_score"], 0)
        self.assertEqual(audit["radar_decision"], "ALLOW")
        self.assertTrue(audit["frictionless_eligible"])

        # Mismatched identity (US card + JP egress)
        exit_jp = {"country": "JP"}
        audit_mismatch = FraudRiskAuditor.full_audit(id_us, card_us, exit_jp, fp_chrome)
        self.assertGreater(audit_mismatch["total_risk_score"], 25)
        self.assertEqual(audit_mismatch["radar_decision"], "CHALLENGE_3DS")
        self.assertFalse(audit_mismatch["frictionless_eligible"])


if __name__ == "__main__":
    unittest.main()
