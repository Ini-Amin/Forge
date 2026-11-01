"""Unit tests for SQLite WAL storage and transport security."""
import tempfile
import unittest
from pathlib import Path

from forge.cards.storage import CardStorage
from forge.transport.session import EgressSecurityError, TLSSession


class TestStorageAndTransport(unittest.TestCase):
    def test_sqlite_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_file = Path(tmp) / "test_forge.db"
            store = CardStorage(db_file, migrate_legacy=False)

            # Insert unique hash
            self.assertTrue(store.record_card("hash_001", "4147201234567890", "414720"))
            self.assertTrue(store.has_seen("hash_001"))
            self.assertFalse(store.has_seen("hash_999"))

            # Duplicate hash rejected
            self.assertFalse(store.record_card("hash_001", "4147201234567890", "414720"))
            self.assertEqual(store.total_count(), 1)

    def test_strict_proxy_fails_closed(self):
        # When strict_proxy=True is set, omitting a proxy MUST raise EgressSecurityError
        with self.assertRaises(EgressSecurityError):
            TLSSession(proxy=None, strict_proxy=True)


if __name__ == "__main__":
    unittest.main()
