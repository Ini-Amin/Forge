import unittest

from forge.lifecycle.engine import LifecycleEngine

HAPPY = [
    {"event_id": "e1", "type": "auth.accepted", "occurred_at": "2026-11-03T10:00:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e2", "type": "capture.accepted", "occurred_at": "2026-11-03T10:01:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e3", "type": "clearing.submitted", "occurred_at": "2026-11-03T10:02:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e4", "type": "clearing.accepted", "occurred_at": "2026-11-03T10:03:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e5", "type": "settlement.submitted", "occurred_at": "2026-11-03T10:04:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e6", "type": "settlement.accepted", "occurred_at": "2026-11-03T10:05:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
]


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


class TestEngine(unittest.TestCase):
    def test_happy_path_settles(self):
        res = LifecycleEngine(HAPPY).run()
        self.assertEqual(res.tracks["settlement"], "SETTLED")
        self.assertEqual([r.result for r in res.history], ["applied"] * 6)
        self.assertEqual(len(res.history), 6)

    def test_out_of_order_rejected(self):
        # capture before auth
        events = [HAPPY[1]] + [HAPPY[0]] + HAPPY[2:]
        res = LifecycleEngine(events).run()
        self.assertEqual(res.history[0].result, "rejected")
        self.assertIn("eligible authorization", res.history[0].reason)

    def test_wrong_amount_rejected(self):
        events = [dict(HAPPY[0]), dict(HAPPY[1], amount_units=200)]
        res = LifecycleEngine(events).run()
        self.assertEqual(res.history[1].result, "rejected")
        self.assertIn("$1", res.history[1].reason)

    def test_phase2_event_inactive(self):
        events = [dict(HAPPY[0]), {"event_id": "x", "type": "refund.accepted", "occurred_at": "t", "source": "mock-file", "amount_units": 100, "currency": "USD"}]
        res = LifecycleEngine(events).run()
        self.assertEqual(res.history[1].result, "rejected")
        self.assertIn("inactive", res.history[1].reason)

    def test_duplicate_event_id(self):
        events = [dict(HAPPY[0])] + [dict(HAPPY[0])]
        res = LifecycleEngine(events).run()
        self.assertEqual([r.result for r in res.history], ["applied", "duplicate"])
        self.assertEqual(res.tracks["authorization"], "AUTHORIZED")  # unchanged by replay

    def test_replayable_and_hermetic(self):
        r1 = LifecycleEngine(HAPPY).run()
        r2 = LifecycleEngine(HAPPY).run()
        self.assertEqual([r.result for r in r1.history], [r.result for r in r2.history])
        self.assertEqual(r1.tracks, r2.tracks)

    def test_unknown_event_type(self):
        events = [dict(HAPPY[0]), {"event_id": "u", "type": "bogus.event", "occurred_at": "t", "source": "mock-file", "amount_units": 100, "currency": "USD"}]
        res = LifecycleEngine(events).run()
        self.assertEqual(res.history[1].result, "rejected")
        self.assertIn("unknown", res.history[1].reason)


class TestAggregate(unittest.TestCase):
    def test_settled_aggregate(self):
        from forge.lifecycle.aggregate import build_aggregate
        tracks = {"authorization": "AUTHORIZED", "capture": "CAPTURED", "clearing": "CLEARED", "settlement": "SETTLED"}
        a = build_aggregate(tracks)
        self.assertTrue(a.is_settled)
        self.assertFalse(a.failed)
        self.assertFalse(a.needs_handling)
        self.assertEqual(a.summary, "settled")

    def test_settlement_failed_is_needs_handling_not_failed(self):
        from forge.lifecycle.aggregate import build_aggregate
        tracks = {"authorization": "AUTHORIZED", "capture": "CAPTURED", "clearing": "CLEARED", "settlement": "SETTLEMENT_FAILED"}
        a = build_aggregate(tracks)
        self.assertTrue(a.needs_handling)
        self.assertFalse(a.failed)
        self.assertEqual(a.summary, "needs_handling")

    def test_declined_is_failed(self):
        from forge.lifecycle.aggregate import build_aggregate
        tracks = {"authorization": "DECLINED", "capture": None, "clearing": None, "settlement": None}
        a = build_aggregate(tracks)
        self.assertTrue(a.failed)
        self.assertEqual(a.summary, "declined")

    def test_furthest_reached_when_not_terminal(self):
        from forge.lifecycle.aggregate import build_aggregate
        tracks = {"authorization": "AUTHORIZED", "capture": "CAPTURED", "clearing": "CLEARING_PENDING", "settlement": None}
        a = build_aggregate(tracks)
        self.assertEqual(a.summary, "clearing_pending")
