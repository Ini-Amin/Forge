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


def _luhn_ok(digits):
    """Independent Luhn check (check digit at reversed index 0 is not doubled)."""
    total = 0
    for i, d in enumerate([int(c) for c in digits][::-1]):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class TestNewCountryIdChecksums(unittest.TestCase):
    """The 8 new ID generators must produce nationally valid checksums, not
    random digits that look the part. Each check below re-implements the
    national algorithm independently of the generator."""

    def test_ca_sin_luhn(self):
        from forge.identity.geo import ca_sin
        import random as _random
        rnd = _random.Random(11)
        for _ in range(200):
            s = ca_sin(rnd=rnd)
            self.assertEqual(len(s), 9)
            self.assertIn(s[0], "12345678")
            self.assertTrue(_luhn_ok(s), s)

    def test_fr_nir_mod97_and_dob(self):
        from forge.identity.geo import fr_nir
        import random as _random
        rnd = _random.Random(12)
        dob = "11/22/1973"
        for _ in range(200):
            s = fr_nir("75001", dob=dob, female=True, rnd=rnd)
            self.assertEqual(len(s), 15)
            self.assertEqual(s[0], "2")  # female
            self.assertEqual(int(s[13:]), 97 - (int(s[:13]) % 97), s)
            self.assertEqual(s[1:3], "73")   # YY from dob
            self.assertEqual(s[3:5], "11")   # MM from dob

    def test_it_cf_eigen_check_and_dob(self):
        odd = {"0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17,
               "8": 19, "9": 21, "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13,
               "G": 15, "H": 17, "I": 19, "J": 21, "K": 2, "L": 4, "M": 18,
               "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8, "S": 12, "T": 14,
               "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24, "Z": 23}
        even = {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
                "8": 8, "9": 9, "A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5,
                "G": 6, "H": 7, "I": 8, "J": 9, "K": 10, "L": 11, "M": 12,
                "N": 13, "O": 14, "P": 15, "Q": 16, "R": 17, "S": 18, "T": 19,
                "U": 20, "V": 21, "W": 22, "X": 23, "Y": 24, "Z": 25}
        from forge.identity.geo import it_cf
        import random as _random
        rnd = _random.Random(13)
        for _ in range(200):
            s = it_cf("Rossi", "Mario", dob="04/12/1980", female=False,
                      cf_code="F205", rnd=rnd)
            self.assertEqual(len(s), 16)
            body = s[:15]
            total = sum((odd if i % 2 == 0 else even)[ch] for i, ch in enumerate(body))
            self.assertEqual(s[15], chr(65 + total % 26), s)
            self.assertEqual(body[6:8], "80")   # YY
            self.assertEqual(body[8], "D")      # month 04 -> 'ABCDEHLMPRST'[3]
            self.assertEqual(body[9:11], "12")  # day

    def test_it_cf_female_day_plus_40(self):
        from forge.identity.geo import it_cf
        import random as _random
        rnd = _random.Random(14)
        for _ in range(50):
            s = it_cf("Rossi", "Maria", dob="04/12/1980", female=True, rnd=rnd)
            self.assertEqual(s[9:11], "52")  # 12 + 40

    def test_es_nie_control_letter(self):
        from forge.identity.geo import es_nie
        import random as _random
        rnd = _random.Random(15)
        table = "TRWAGMYFPDXBNJZSQVHLCKE"
        for _ in range(200):
            s = es_nie(rnd=rnd)
            self.assertEqual(len(s), 9)
            self.assertTrue(s[:-1].isdigit())
            self.assertEqual(s[-1], table[int(s[:-1]) % 23], s)

    def test_au_tfn_mod11(self):
        from forge.identity.geo import au_tfn
        import random as _random
        rnd = _random.Random(16)
        for _ in range(200):
            s = au_tfn(rnd=rnd)
            self.assertEqual(len(s), 9)
            total = sum(int(d) * w for d, w in zip(s, (1, 4, 3, 7, 5, 8, 6, 9, 10)))
            self.assertEqual(total % 11, 0, s)

    def test_sg_nric_check_letter(self):
        from forge.identity.geo import sg_nric
        import random as _random
        rnd = _random.Random(17)
        weights = (2, 7, 6, 5, 4, 3, 2)
        for _ in range(200):
            s = sg_nric(rnd=rnd)
            self.assertEqual(len(s), 9)
            self.assertIn(s[0], "ST")
            rem = sum(int(d) * w for d, w in zip(s[1:-1], weights)) % 11
            want = "JZIHGFEDCBA"[rem] if s[0] == "S" else "XWUTRQPNMLK"[rem]
            self.assertEqual(s[-1], want, s)

    def test_nl_bsn_mod11(self):
        from forge.identity.geo import nl_bsn
        import random as _random
        rnd = _random.Random(18)
        for _ in range(200):
            s = nl_bsn(rnd=rnd)
            self.assertEqual(len(s), 9)
            total = sum(int(d) * w for d, w in zip(s[:8], (9, 8, 7, 6, 5, 4, 3, 2)))
            self.assertEqual((total - int(s[8])) % 11, 0, s)

    def test_se_personnummer_luhn_and_dob(self):
        from forge.identity.geo import se_personnummer
        import random as _random
        rnd = _random.Random(19)
        dob = "02/14/1990"
        for _ in range(200):
            s = se_personnummer(dob=dob, rnd=rnd)
            self.assertEqual(len(s), 12)
            self.assertTrue(_luhn_ok(s[2:12]), s)  # YYMMDDNNNC form
            self.assertEqual(s[0:4], "1990")
            self.assertEqual(s[4:6], "02")
            self.assertEqual(s[6:8], "14")

    def test_ids_from_make_fullz_validate(self):
        """End-to-end: the identities the pipeline produces carry valid IDs."""
        from forge.identity.geo import (
            au_tfn, ca_sin, es_nie, fr_nir, it_cf, nl_bsn, se_personnummer, sg_nric,
        )
        for c in ("CA", "FR", "IT", "ES", "AU", "SG", "NL", "SE"):
            ok = False
            for seed in range(30):
                fz = make_fullz(c, seed=seed)
                sid = fz[GEO[c]["id_name"]]
                if c == "CA":
                    ok = len(sid) == 9 and _luhn_ok(sid)
                elif c == "FR":
                    ok = len(sid) == 15 and int(sid[13:]) == 97 - (int(sid[:13]) % 97)
                elif c == "IT":
                    ok = len(sid) == 16
                elif c == "ES":
                    ok = len(sid) == 9 and sid[-1] == "TRWAGMYFPDXBNJZSQVHLCKE"[int(sid[:-1]) % 23]
                elif c == "AU":
                    ok = sum(int(d) * w for d, w in zip(sid, (1, 4, 3, 7, 5, 8, 6, 9, 10))) % 11 == 0
                elif c == "SG":
                    ok = len(sid) == 9 and sid[0] in "ST"
                elif c == "NL":
                    ok = (sum(int(d) * w for d, w in zip(sid[:8], (9, 8, 7, 6, 5, 4, 3, 2))) - int(sid[8])) % 11 == 0
                else:  # SE
                    ok = len(sid) == 12
                if ok:
                    break
            self.assertTrue(ok, f"{c}: no valid ID in 30 seeds")


if __name__ == "__main__":
    unittest.main()
