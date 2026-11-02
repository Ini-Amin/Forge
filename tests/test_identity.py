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

    def test_nik_ddmmyy_matches_dob(self):
        """NIK digits 7-12 are DDMMYY from the identity's DOB, not a constant."""
        seen = set()
        for seed in range(40):
            fz = make_fullz("ID", seed=seed)
            nik, dob = fz["nik"], fz["dob"]
            self.assertEqual(len(nik), 16)
            mm, dd, yy = dob.split("/")
            dd_i = int(dd)
            # Female NIK adds 40 to the day.
            for day in (dd_i, dd_i + 40):
                if f"{day:02d}{mm}{yy[2:]}" == nik[6:12]:
                    break
            else:
                self.fail(f"NIK DDMMYY {nik[6:12]} does not match dob {dob}")
            seen.add(nik[8:12])
        self.assertGreater(len(seen), 10, "MM+YY should vary across seeds")

    def test_nik_without_dob_is_adult(self):
        """Fallback NIK path must not mint future birth years."""
        from forge.identity.geo import id_nik
        import random as _random
        rnd = _random.Random(7)
        for _ in range(50):
            yy = int(id_nik("40111", rnd=rnd)[10:12])
            year = 2000 + yy if yy <= 8 else 1900 + yy
            self.assertGreaterEqual(year, 1961)
            self.assertLessEqual(year, 2026)


if __name__ == "__main__":
    unittest.main()
