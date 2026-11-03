import json
import os
import tempfile
import unittest

from forge.lifecycle.reconciliation import events_from_file, reconcile

INT = [
    {"event_id": "e1", "type": "auth.accepted", "occurred_at": "t1", "amount_units": 100, "currency": "USD"},
    {"event_id": "e2", "type": "capture.accepted", "occurred_at": "t2", "amount_units": 100, "currency": "USD"},
    {"event_id": "e3", "type": "clearing.accepted", "occurred_at": "t3", "amount_units": 100, "currency": "USD"},
]


class TestReconciliation(unittest.TestCase):
    def test_exact_match(self):
        ext = [dict(e) for e in INT]
        rep = reconcile(INT, ext)
        self.assertEqual(rep.matches, 3)
        self.assertEqual(rep.counts["mismatch"], 0)

    def test_mismatch_per_field(self):
        ext = [dict(INT[0], amount_units=999)] + [dict(e) for e in INT[1:]]
        rep = reconcile(INT, ext)
        self.assertEqual(rep.mismatches, 1)
        self.assertEqual(rep.rows[0].diffs, ("amount_units",))

    def test_missing_and_unexpected(self):
        # internal keeps e3, external drops it and gains a fabricated e9
        ext = [dict(e) for e in INT[:-1]] + [{"event_id": "e9", "type": "auth.declined", "occurred_at": "t9", "amount_units": 100, "currency": "USD"}]
        rep = reconcile(INT, ext)
        self.assertEqual(rep.missing_external, 1)  # e3 absent from external
        self.assertEqual(rep.unexpected_external, 1)  # e9 present externally only

    def test_metadata_never_diffed(self):
        internal = [dict(INT[0])]
        external = [dict(INT[0], result="applied", reason="x", source="reconciliation")]
        rep = reconcile(internal, external)
        self.assertEqual(rep.matches, 1)
        self.assertEqual(rep.rows[0].diffs, ())


class TestEventsFromFile(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump({"events": INT}, fh)
            path = fh.name
        try:
            events = events_from_file(path)
        finally:
            os.unlink(path)
        self.assertEqual(events, INT)

    def test_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            events_from_file("/nonexistent/path/events.json")

    def test_malformed_json_raises_value_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{not json")
            path = fh.name
        try:
            with self.assertRaises(ValueError):
                events_from_file(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
