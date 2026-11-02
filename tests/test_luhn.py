"""Unit tests for Luhn validation, card generation, and issuer lookup."""
import tempfile
import unittest
from pathlib import Path

from forge.cards.bins import card_length, issuer_lookup
from forge.cards.storage import CardStorage
from forge.cards.luhn import (
    format_card,
    generate_expiry_date,
    generate_random,
    generate_sequential,
    is_luhn_valid,
    luhn_check_digit,
)


class TestLuhnCards(unittest.TestCase):
    def test_luhn_validation(self):
        # Known valid Luhn test PANs
        self.assertTrue(is_luhn_valid("4242424242424242"))
        self.assertTrue(is_luhn_valid("4111111111111111"))
        self.assertFalse(is_luhn_valid("4242424242424243"))
        self.assertFalse(is_luhn_valid("abc"))
        self.assertFalse(is_luhn_valid(""))

    def test_luhn_check_digit(self):
        partial = "424242424242424"
        chk = luhn_check_digit(partial)
        self.assertEqual(chk, "2")
        self.assertTrue(is_luhn_valid(partial + chk))

    def test_card_length(self):
        self.assertEqual(card_length("341234"), 15)  # Amex
        self.assertEqual(card_length("371234"), 15)  # Amex
        self.assertEqual(card_length("361234"), 14)  # Diners
        self.assertEqual(card_length("414720"), 16)  # Visa
        self.assertEqual(card_length("517805"), 16)  # Mastercard

    def test_issuer_lookup(self):
        meta_visa = issuer_lookup("4147201234567890")
        self.assertEqual(meta_visa["network"], "Visa")
        self.assertEqual(meta_visa["issuer"], "Chase")

        meta_mc = issuer_lookup("5178051234567890")
        self.assertEqual(meta_mc["network"], "Mastercard")

        meta_unknown = issuer_lookup("9999991234567890")
        self.assertEqual(meta_unknown["network"], "Unknown")

    def test_generate_random(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = CardStorage(Path(td) / "cards.db", migrate_legacy=False)
            cards = generate_random("414720", "12", "30", 10, seed=42, card_storage=scratch)
        self.assertEqual(len(cards), 10)
        for c in cards:
            self.assertTrue(is_luhn_valid(c["pan"]))
            self.assertTrue(c["pan"].startswith("414720"))
            self.assertEqual(len(c["pan"]), 16)
            self.assertEqual(len(c["cvv"]), 3)

    def test_generate_sequential(self):
        cards = generate_sequential("414720", "12", "30", 5)
        self.assertEqual(len(cards), 5)
        for c in cards:
            self.assertTrue(is_luhn_valid(c["pan"]))

    def test_format_card(self):
        card = {"pan": "4242424242424242", "mm": "12", "yy": "30", "cvv": "123", "issuer": "Test", "network": "Visa"}
        self.assertEqual(format_card(card, "pipe"), "4242424242424242|12|30|123")
        self.assertIn("4242424242424242,12,30,123", format_card(card, "csv"))
    def test_dynamic_rolling_expiry(self):
        mm, yy = generate_expiry_date()
        self.assertTrue(1 <= int(mm) <= 12)
        self.assertTrue(len(yy) == 2 and yy.isdigit())

        with tempfile.TemporaryDirectory() as td:
            scratch = CardStorage(Path(td) / "cards.db", migrate_legacy=False)
            cards = generate_random("414720", exp_m="auto", exp_y="auto", count=3, card_storage=scratch)
        for c in cards:
            self.assertTrue(1 <= int(c["mm"]) <= 12)
            self.assertTrue(len(c["yy"]) == 2)


if __name__ == "__main__":
    unittest.main()
