"""forge.identity.geo - Geographic database and regional national ID shapes.

Provides coherent locale datasets:
- Cities, ZIP/postal codes, area codes, streets
- Culture-matched first & last name pools
- Algorithmic national ID generators (US SSN, ID NIK, JP My Number, BR CPF, DE Personalausweis)
"""
from __future__ import annotations

import random
from typing import Dict, Tuple

COUNTRIES = ["US", "JP", "ID", "DE", "BR"]

COUNTRY_LABEL = {
    "US": "United States",
    "JP": "Japan",
    "ID": "Indonesia",
    "DE": "Germany",
    "BR": "Brazil",
}

GEO: dict[str, dict] = {
    "US": {
        "phone_fmt": "(aaa) nnn-nnnn",
        "id_name": "ssn",
        "cities": {
            "10001": {"city": "New York", "state": "NY", "area": "212",
                      "streets": ["W 23rd St", "Broadway", "8th Ave", "7th Ave"]},
            "90210": {"city": "Beverly Hills", "state": "CA", "area": "310",
                      "streets": ["Rodeo Dr", "Wilshire Blvd", "Canon Dr", "Crescent Dr"]},
            "60601": {"city": "Chicago", "state": "IL", "area": "312",
                      "streets": ["N Michigan Ave", "E Wacker Dr", "N State St"]},
            "33101": {"city": "Miami", "state": "FL", "area": "305",
                      "streets": ["Biscayne Blvd", "Ocean Dr", "Collins Ave", "Washington Ave"]},
            "98101": {"city": "Seattle", "state": "WA", "area": "206",
                      "streets": ["Pine St", "Pike St", "4th Ave", "Union St"]},
            "78701": {"city": "Austin", "state": "TX", "area": "512",
                      "streets": ["Congress Ave", "E 6th St", "W 5th St", "Lavaca St"]},
        },
        "ssn_state_block": {"NY": 50, "CA": 550, "IL": 320, "FL": 260, "WA": 530, "TX": 460},
    },
    "JP": {
        "phone_fmt": "090-nnnn-nnnn",
        "id_name": "my_number",
        "cities": {
            "160-0022": {"city": "Shinjuku, Tokyo", "state": "Tokyo", "area": "03",
                         "streets": ["Shinjuku", "Nishi-Shinjuku", "Yotsuya"]},
            "530-0001": {"city": "Kita, Osaka", "state": "Osaka", "area": "06",
                         "streets": ["Umeda", "Dojima", "Tenma"]},
            "460-0008": {"city": "Naka, Nagoya", "state": "Aichi", "area": "052",
                         "streets": ["Nishiki", "Sakae", "Marunouchi"]},
        },
    },
    "ID": {
        "phone_fmt": "0812-nnnn-nnn",
        "id_name": "nik",
        "cities": {
            "10110": {"city": "Jakarta Pusat", "state": "DKI Jakarta", "area": "021",
                      "streets": ["Jl. Thamrin", "Jl. Sudirman", "Jl. Kebon Sirih"]},
            "40111": {"city": "Bandung", "state": "Jawa Barat", "area": "022",
                      "streets": ["Jl. Asia Afrika", "Jl. Braga", "Jl. Merdeka"]},
            "80111": {"city": "Denpasar", "state": "Bali", "area": "0361",
                      "streets": ["Jl. Sunset Road", "Jl. Teuku Umar", "Jl. Raya Kuta"]},
        },
    },
    "DE": {
        "phone_fmt": "+49 a nnnnnnn",
        "id_name": "personalausweis",
        "cities": {
            "10115": {"city": "Berlin", "state": "Berlin", "area": "30",
                      "streets": ["Torstrasse", "Invalidenstrasse", "Chausseestrasse"]},
            "80331": {"city": "Munchen", "state": "Bayern", "area": "89",
                      "streets": ["Kaufingerstrasse", "Sendlinger Strasse", "Prannerstrasse"]},
            "60311": {"city": "Frankfurt", "state": "Hessen", "area": "69",
                      "streets": ["Kaiserstrasse", "Zeil", "Rossmarkt"]},
        },
    },
    "BR": {
        "phone_fmt": "+55 a nnnnn-nnnn",
        "id_name": "cpf",
        "cities": {
            "01310-100": {"city": "Sao Paulo", "state": "SP", "area": "11",
                          "streets": ["Av. Paulista", "Rua Augusta", "Rua Bela Cintra"]},
            "20040-020": {"city": "Rio de Janeiro", "state": "RJ", "area": "21",
                          "streets": ["Av. Rio Branco", "Rua Primeiro de Marco", "Rua Uruguaiana"]},
        },
    },
}

NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "US": {
        "first": ("James", "Mary", "Robert", "Patricia", "John", "Jennifer",
                  "Michael", "Linda", "David", "Elizabeth", "William", "Jessica"),
        "last": ("Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
                 "Miller", "Davis", "Rodriguez", "Wilson", "Anderson", "Taylor"),
    },
    "JP": {
        "first": ("Hiroshi", "Yuki", "Takashi", "Sakura", "Kenji", "Aoi",
                  "Daiki", "Hana", "Ryo", "Mei", "Sora", "Yui"),
        "last": ("Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito",
                 "Yamamoto", "Nakamura", "Kobayashi", "Kato", "Yoshida", "Sasaki"),
    },
    "ID": {
        "first": ("Rizky", "Dimas", "Bayu", "Arif", "Fajar", "Putra", "Siti",
                  "Dewi", "Ayu", "Putri", "Wulan", "Budi"),
        "last": ("Pratama", "Saputra", "Wijaya", "Hidayat", "Nugroho", "Setiawan",
                 "Kusuma", "Permana", "Gunawan", "Santoso", "Wibowo", "Lestari"),
    },
    "DE": {
        "first": ("Lukas", "Felix", "Jonas", "Leon", "Anna", "Lena", "Julia",
                  "Sophie", "Maximilian", "Niklas", "Elena", "Laura"),
        "last": ("Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer",
                 "Wagner", "Becker", "Hoffmann", "Schulz", "Koch", "Bauer"),
    },
    "BR": {
        "first": ("Miguel", "Arthur", "Gabriel", "Rafael", "Sofia", "Helena",
                  "Alice", "Laura", "Thiago", "Bruno", "Lucas", "Pedro"),
        "last": ("Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira",
                 "Costa", "Almeida", "Nascimento", "Araujo", "Ribeiro", "Carvalho"),
    },
}


def us_ssn(state: str, rnd: Any = random) -> str:
    """SSN-shaped ID. Respects SSA allocation blocks."""
    block = (GEO["US"].get("ssn_state_block") or {}).get(state)
    if block:
        area = block * 10 + rnd.randint(1, 9)
        area = min(area, 899)
    else:
        area = rnd.randint(1, 899)
    if area == 666:
        area = 665
    return f"{area:03d}-{rnd.randint(1, 99):02d}-{rnd.randint(1, 9999):04d}"


def id_nik(zip_code: str, rnd: Any = random) -> str:
    """Indonesian NIK: 16 digits, starts with province/regency codes + birthdate."""
    prov = rnd.choice({"10110": "31", "40111": "32", "80111": "51"}.get(zip_code, "31"))
    reg = f"{rnd.randint(1, 75):02d}"
    d = rnd.randint(1, 28) + (40 if rnd.random() < 0.5 else 0)
    mm = rnd.randint(1, 12)
    yy = rnd.randint(0, 99)
    serial = f"{rnd.randint(1, 9999):04d}"
    return f"{prov}{reg}{d:02d}{mm:02d}{yy:02d}{serial}"


def jp_my_number(rnd: Any = random) -> str:
    """Japanese My Number (12 digits with weighted check digit)."""
    digits = [rnd.randint(0, 9) for _ in range(11)]
    weights = list(range(6, 1, -1)) + list(range(9, 0, -1)) + list(range(8, 0, -1))
    s = sum(d * w for d, w in zip(digits, weights))
    check = (s % 11)
    check = 0 if check <= 1 else 11 - check
    digits.append(check)
    return "".join(map(str, digits))


def br_cpf(rnd: Any = random) -> str:
    """Brazilian CPF (11 digits with dual modulo-11 check digits)."""
    def calc(nums: list[int], weights: list[int]) -> int:
        s = sum(n * w for n, w in zip(nums, weights))
        r = (s * 10) % 11
        return 0 if r == 10 else r

    nums = [rnd.randint(0, 9) for _ in range(9)]
    d1 = calc(nums, list(range(10, 1, -1)))
    d2 = calc(nums + [d1], list(range(11, 1, -1)))
    return "".join(map(str, nums)) + f"{d1}{d2}"


def de_steuer(rnd: Any = random) -> str:
    """German Tax ID / Personalausweis shape."""
    return f"{rnd.randint(10, 99)}{rnd.randint(100000, 999999)}"[:11]


def format_phone(fmt: str, area: str, rnd: Any = random) -> str:
    """Render the country phone template: 'a' -> area code, 'n' -> random digit."""
    out = []
    area_used = False
    for ch in fmt:
        if ch == "a":
            if not area_used:
                out.append(area)
                area_used = True
        elif ch == "n":
            out.append(str(rnd.randint(0, 9)))
        else:
            out.append(ch)
    return "".join(out)
