"""forge.identity.generator - Synthetic identity and persona generator.

Generates realistic, geo-coherent synthetic identities with:
- Culture-appropriate names
- Consistent address, city, state, postal code, and phone area code
- Valid national ID shape
- Deterministic seeding support for reproducible testing
"""
from __future__ import annotations

import random
import string
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

from forge.identity.geo import (
    COUNTRIES,
    GEO,
    NAMES,
    au_tfn,
    br_cpf,
    ca_sin,
    de_steuer,
    es_nie,
    format_phone,
    fr_nir,
    id_nik,
    it_cf,
    jp_my_number,
    nl_bsn,
    se_personnummer,
    sg_nric,
    uk_nino,
    us_ssn,
)


@dataclass
class SyntheticIdentity:
    country: str
    name: str
    address: str
    city: str
    state: str
    zip: str
    phone: str
    email: str
    national_id_name: str
    national_id: str
    dob: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to legacy fullz dictionary structure."""
        d = asdict(self)
        # Map dynamic national ID field name (e.g. 'ssn', 'nik', 'my_number')
        id_key = d.pop("national_id_name")
        id_val = d.pop("national_id")
        d[id_key] = id_val
        return d


def generate_dob(seed: Optional[int] = None) -> str:
    """Generate birthdate for an adult between 18 and 65 years old."""
    rnd = random.Random(seed) if seed is not None else random
    today = date.today()
    start = today - timedelta(days=int(65 * 365.25))
    end = today - timedelta(days=int(18 * 365.25))
    d = start + timedelta(days=rnd.randint(0, (end - start).days))
    return d.strftime("%m/%d/%Y")


def _get_parts(country: str, second: bool = True, rnd: Any = random) -> tuple[str, str]:
    pool = NAMES[country]
    first = rnd.choice(pool["first"])
    last = rnd.choice(pool["last"])
    return first, last


def full_name(country: str = "US", *, number: bool = True, seed: Optional[int] = None) -> str:
    rnd = random.Random(seed) if seed is not None else random
    first, last = _get_parts(country, rnd=rnd)
    name = f"{first} {last}"
    if number and rnd.random() < 0.25:
        name += str(rnd.randint(10, 99))
    return name


def display_name(country: str = "US", *, number: bool = True, seed: Optional[int] = None) -> str:
    rnd = random.Random(seed) if seed is not None else random
    first, last = _get_parts(country, rnd=rnd)
    name = "_".join((first, last)).lower()
    if number and rnd.random() < 0.25:
        name += str(rnd.randint(10, 99))
    return name


def username(country: str = "US", *, digits: int = 4,
             min_len: int = 0, max_len: int = 0, seed: Optional[int] = None) -> str:
    rnd = random.Random(seed) if seed is not None else random
    first, last = _get_parts(country, second=False, rnd=rnd)
    handle = f"{first}_{last}".lower()
    if digits:
        handle += "".join(rnd.choices(string.digits, k=digits))
    handle = "".join(c for c in handle if c.isalnum() or c == "_")
    if min_len and len(handle) < min_len:
        handle += "".join(rnd.choices(string.ascii_lowercase + string.digits,
                                      k=min_len - len(handle)))
    return handle[:max_len] if max_len else handle


def password(n: int = 14, *, require_special: bool = True, seed: Optional[int] = None) -> str:
    rnd = random.Random(seed) if seed is not None else random
    core = "".join(rnd.choices(string.ascii_letters + string.digits, k=max(6, n - 2)))
    out = list(core)
    rnd.shuffle(out)
    out.append(rnd.choice(string.digits))
    if require_special:
        out.append(rnd.choice("!@#$%^&*-_"))
    return "".join(out)[:max(n, 8)]


def make_fullz(country: str = "US", seed: Optional[int] = None) -> dict[str, Any]:
    """Generate a coherent synthetic identity dictionary for `country`."""
    country = country.upper()
    if country not in GEO:
        raise KeyError(f"Country {country} not supported. Available: {sorted(GEO)}")

    rnd = random.Random(seed) if seed is not None else random
    g = GEO[country]
    zip_code = rnd.choice(list(g["cities"].keys()))
    geo_data = g["cities"][zip_code]
    first, last = _get_parts(country, rnd=rnd)

    street = f"{rnd.randint(100, 9999)} {rnd.choice(geo_data['streets'])}"
    if rnd.random() < 0.3:
        street += f" Apt {rnd.randint(1, 99)}{rnd.choice('ABCDEF')}"

    email_domain = rnd.choice(["gmail.com", "yahoo.com", "outlook.com"])
    email = f"{first.lower()}.{last.lower()}{rnd.randint(10, 99)}@{email_domain}"
    phone = format_phone(g["phone_fmt"], geo_data["area"], rnd=rnd)

    # DOB first so date-encoding IDs (NIK, NIR, Codice Fiscale, personnummer)
    # derive their digits from it (single draw, no dead retry).
    dob = generate_dob(seed=seed)
    female = rnd.random() < 0.5
    id_name = g.get("id_name", "national_id")
    if id_name == "ssn":
        nat_id = us_ssn(geo_data["state"], rnd=rnd)
    elif id_name == "nik":
        nat_id = id_nik(zip_code, rnd=rnd, dob=dob, female=female)
    elif id_name == "my_number":
        nat_id = jp_my_number(rnd=rnd)
    elif id_name == "cpf":
        nat_id = br_cpf(rnd=rnd)
    elif id_name == "nino":
        nat_id = uk_nino(rnd=rnd)
    elif id_name == "sin":
        nat_id = ca_sin(rnd=rnd)
    elif id_name == "nir":
        nat_id = fr_nir(zip_code, dob=dob, female=female, rnd=rnd)
    elif id_name == "codice_fiscale":
        nat_id = it_cf(last, first, dob=dob, female=female,
                       cf_code=geo_data.get("cf_code") or "H501", rnd=rnd)
    elif id_name == "nie":
        nat_id = es_nie(rnd=rnd)
    elif id_name == "tfn":
        nat_id = au_tfn(rnd=rnd)
    elif id_name == "nric":
        nat_id = sg_nric(rnd=rnd)
    elif id_name == "bsn":
        nat_id = nl_bsn(rnd=rnd)
    elif id_name == "personnummer":
        nat_id = se_personnummer(dob=dob, rnd=rnd)
    else:
        nat_id = de_steuer(rnd=rnd)

    identity = SyntheticIdentity(
        country=country,
        name=f"{first} {last}",
        address=street,
        city=geo_data["city"],
        state=geo_data["state"],
        zip=zip_code,
        phone=phone,
        email=email,
        national_id_name=id_name,
        national_id=nat_id,
        dob=dob,
    )
    return identity.to_dict()
