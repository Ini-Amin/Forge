import unittest


class TestRates(unittest.TestCase):
    def test_converted_units_known_currencies(self):
        from forge.lifecycle.rates import converted_units
        self.assertEqual(converted_units("USD"), 100)
        self.assertEqual(converted_units("JPY"), 150)   # zero-decimal: 150 yen, not 15000
        self.assertEqual(converted_units("EUR"), 92)
        self.assertEqual(converted_units("GBP"), 79)
        self.assertEqual(converted_units("IDR"), 1550000)  # two-decimal per ISO 4217 — see ruling Q1

    def test_converted_units_unknown_currency_raises(self):
        from forge.lifecycle.rates import converted_units
        with self.assertRaises(ValueError):
            converted_units("XXX")


class TestTransitions(unittest.TestCase):
    def test_find_transition_known_and_unknown(self):
        from forge.lifecycle.state import find_transition
        t = find_transition("capture.accepted")
        self.assertEqual(t.track, "capture")
        self.assertEqual(t.to_state, "CAPTURED")
        self.assertIsNone(find_transition("refund.accepted"))  # phase-2 vocab has no transition

    def test_guard_eligible_auth(self):
        from forge.lifecycle.state import evaluate_guard
        ok, reason = evaluate_guard("eligible_auth", {"authorization": "AUTHORIZED"}, 100)
        self.assertTrue(ok)
        ok, reason = evaluate_guard("eligible_auth", {"authorization": "AUTHORIZED"}, 0)
        self.assertFalse(ok)
        self.assertIn("remaining", reason)
