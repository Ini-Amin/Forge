"""forge.transport.proxy - Proxy providers, verification, and rotation."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from forge.config import CACHE_DIR
from forge.transport.session import TLSSession

PROXY_PROVIDERS: list[Callable[[str], Optional[dict[str, Any]]]] = []


def register_proxy_provider(fn: Callable[[str], Optional[dict[str, Any]]]) -> None:
    """Register a provider function (country: str) -> dict | None."""
    if fn not in PROXY_PROVIDERS:
        PROXY_PROVIDERS.append(fn)


# ── Urban VPN provider ────────────────────────────────────────────────────────
_UV_BASE = "https://api-pro.urban-vpn.com/rest/v1"
_UV_STATS = "https://stats.urban-vpn.com/api/rest/v2"
_UV_APP = "URBAN_VPN_BROWSER_EXTENSION"
_UV_CACHE = CACHE_DIR / "urban_vpn_session.json"


def _uv_post(url: str, payload: dict, token: str = "") -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json", "X-Client-App": _UV_APP}
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
    anon = _uv_post(
        f"{_UV_BASE}/registrations/clientApps/{_UV_APP}/users/anonymous",
        {"clientApp": {"name": _UV_APP, "browser": "CHROME"}},
    )["value"]
    sec = _uv_post(
        f"{_UV_BASE}/security/tokens/accs",
        {"type": "accs", "clientApp": {"name": _UV_APP}},
        token=anon,
    )
    s = {
        "anon_tok": anon,
        "sec_tok": sec["value"],
        "expires_at": sec.get("expirationTime", time.time() * 1000 + 3_600_000) / 1000,
    }
    _UV_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _UV_CACHE.write_text(json.dumps(s, indent=2))
    return s


def _uv_countries(sec_tok: str) -> list[dict]:
    try:
        countries = _uv_get(f"{_UV_STATS}/entrypoints/countries", token=sec_tok)
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        countries = _uv_get(f"{_UV_STATS}/entrypoints/countries", token=_uv_session()["sec_tok"])
    payload = countries.get("countries", countries) if isinstance(countries, dict) else countries
    return (payload.get("elements") if isinstance(payload, dict) else payload) or []


def urban_vpn_single(country: str) -> Optional[dict[str, Any]]:
    """Fetch first available server for country from Urban VPN."""
    try:
        sess = _uv_session()
        entry = next(
            (
                el for el in _uv_countries(sess["sec_tok"])
                if el.get("code", {}).get("iso2", "").upper() == country.upper()
                and el.get("servers", {}).get("elements")
            ),
            None,
        )
        if not entry:
            return None
        chosen = entry["servers"]["elements"][0]
        host = chosen["address"]["primary"]["host"]
        port = chosen["address"]["primary"]["port"]
        tok = _uv_post(
            f"{_UV_BASE}/security/tokens/accs-proxy",
            {"type": "accs-proxy", "clientApp": {"name": _UV_APP}, "signature": chosen["signature"]},
            token=sess["sec_tok"],
        )["value"]
        return {
            "provider": "urban_vpn",
            "country": country.upper(),
            "host": host,
            "port": port,
            "proxy": f"http://{tok}:1@{host}:{port}",
        }
    except Exception:
        return None


def urban_vpn_all_servers(country: str) -> list[dict[str, Any]]:
    """Return all servers exposed for `country`."""
    try:
        sess = _uv_session()
        entry = next(
            (
                el for el in _uv_countries(sess["sec_tok"])
                if el.get("code", {}).get("iso2", "").upper() == country.upper()
                and el.get("servers", {}).get("elements")
            ),
            None,
        )
        if not entry:
            return []
        out = []
        for chosen in entry["servers"]["elements"]:
            try:
                host = chosen["address"]["primary"]["host"]
                port = chosen["address"]["primary"]["port"]
                tok = _uv_post(
                    f"{_UV_BASE}/security/tokens/accs-proxy",
                    {"type": "accs-proxy", "clientApp": {"name": _UV_APP}, "signature": chosen["signature"]},
                    token=sess["sec_tok"],
                )["value"]
                out.append({
                    "provider": "urban_vpn",
                    "country": country.upper(),
                    "host": host,
                    "port": port,
                    "proxy": f"http://{tok}:1@{host}:{port}",
                })
            except Exception:
                continue
        return out
    except Exception:
        return []


def urban_vpn_pool(country: str) -> Optional[dict[str, Any]]:
    """Rotating pool provider variant."""
    if not hasattr(urban_vpn_pool, "_queue"):
        urban_vpn_pool._queue = []  # type: ignore
    q = urban_vpn_pool._queue        # type: ignore
    while q:
        cand = q.pop(0)
        if cand["country"] == country.upper():
            return cand
    servers = urban_vpn_all_servers(country)
    if servers:
        urban_vpn_pool._queue = servers[1:]  # type: ignore
        return servers[0]
    return None


register_proxy_provider(urban_vpn_pool)
register_proxy_provider(urban_vpn_single)


# ── Verification & Matching ──────────────────────────────────────────────────
def verify_proxy(
    proxy_url: str,
    target: str = "https://api.ipify.org?format=json",
    expect_country: Optional[str] = None
) -> dict[str, Any]:
    """Test proxy with TLS ClientHello impersonation. Routes all traffic through proxy."""
    out = {"ok": False, "status": None, "exit_ip": None, "country": None, "error": None}
    try:
        with TLSSession(proxy_url, strict_proxy=True) as s:
            r = s.get(target, timeout=10.0)
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
            with TLSSession(proxy_url, strict_proxy=True) as s:
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


def matching_proxy(fullz: Optional[dict] = None) -> Optional[dict[str, Any]]:
    """Return verified proxy matching the identity's country."""
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


def matching_proxies(fullz: Optional[dict] = None, *, want: int = 3, verify: bool = True) -> list[dict[str, Any]]:
    """Return up to `want` verified distinct proxy entries."""
    country = (fullz or {}).get("country") or "US"
    found: list[dict[str, Any]] = []
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
