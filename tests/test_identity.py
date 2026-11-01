"""Unit tests for synthetic identity and geo coherence."""
import unittest

from forge.identity.generator import (
    SyntheticIdentity,
    display_name,
    full_name,
    generate_dob,
    make_fullz,
    password,
    username,
)
from forge.identity.geo import COUNTRIES, GEO


class TestIdentityGenerator(unittest.TestCase):
    def test_all_supported_countries(self):
        for c in COUNTRIES:
            fz = make_fullz(c)
            self.assertEqual(fz["country"], c)
            self.assertTrue(fz["name"])
            self.assertTrue(fz["city"])
            self.assertTrue(fz["phone"])
            self.assertTrue(fz["email"])
            self.assertTrue("@" in fz["email"])

            # Verify national ID field presence
            expected_id_name = GEO[c]["id_name"]
            self.assertIn(expected_id_name, fz)
            self.assertTrue(fz[expected_id_name])

    def test_unsupported_country_raises(self):
        with self.assertRaises(KeyError):
            make_fullz("XX")

    def test_deterministic_seed(self):
        fz1 = make_fullz("US", seed=1337)
        fz2 = make_fullz("US", seed=1337)
        self.assertEqual(fz1, fz2)

    def test_username_and_password(self):
        u = username("US", digits=4)
        self.assertTrue(any(ch.isdigit() for ch in u))

        p = password(16, require_special=True)
        self.assertGreaterEqual(len(p), 16)
        self.assertTrue(any(ch in "!@#$%^&*-_" for ch in p))


if __name__ == "__main__":
    unittest.main()
