"""forge.transport.profiles - Browser TLS fingerprint & User-Agent profile catalog."""
from __future__ import annotations

import random
from collections import OrderedDict
from typing import Any, Dict, List, Optional

PROFILES: list[dict[str, Any]] = [
    {
        "impersonate": "chrome136",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept_lang": "en-US,en;q=0.9",
        "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "sec_ch_ua_platform": '"Windows"',
        "sec_ch_ua_mobile": "?0",
    },
    {
        "impersonate": "chrome133a",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept_lang": "en-GB,en;q=0.9",
        "sec_ch_ua": '"Not(A:Brand";v="24", "Chromium";v="133", "Google Chrome";v="133"',
        "sec_ch_ua_platform": '"Windows"',
        "sec_ch_ua_mobile": "?0",
    },
    {
        "impersonate": "firefox135",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept_lang": "en-US,en;q=0.5",
        "sec_ch_ua": None,
        "sec_ch_ua_platform": None,
        "sec_ch_ua_mobile": None,
    },
    {
        "impersonate": "safari18_0",
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept_lang": "en-US,en;q=0.9",
        "sec_ch_ua": None,
        "sec_ch_ua_platform": None,
        "sec_ch_ua_mobile": None,
    },
    {
        "impersonate": "chrome131",
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept_lang": "en-US,en;q=0.9",
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec_ch_ua_platform": '"macOS"',
        "sec_ch_ua_mobile": "?0",
    },
]

REFERERS: list[Optional[str]] = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    None,
]


def get_impersonate_profile() -> dict[str, Any]:
    """Return a randomly chosen browser profile with aligned TLS and UA."""
    return random.choice(PROFILES)


def build_headers(profile: dict[str, Any], referer: Optional[str] = None) -> dict[str, str]:
    """Construct authentic browser request headers matching the profile."""
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
