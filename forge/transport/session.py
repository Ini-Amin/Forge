"""forge.transport.session - TLS impersonation sessions with fail-closed safety."""
from __future__ import annotations

import random
from typing import Any, Dict, Optional

try:
    from curl_cffi import requests as cffi_requests
    from curl_cffi.requests import AsyncSession as AsyncCffiSession
    from curl_cffi.requests.exceptions import ProxyError, RequestException, Timeout
    HAS_CURL_CFFI = True
except ImportError as err:
    HAS_CURL_CFFI = False
    cffi_requests = None
    AsyncCffiSession = None

from forge.transport.profiles import (
    PROFILES,
    REFERERS,
    build_headers,
    get_impersonate_profile,
)


class EgressSecurityError(RuntimeError):
    """Raised when an egress security policy is violated (e.g. direct IP leak attempt)."""


def _check_engine() -> None:
    if not HAS_CURL_CFFI:
        raise ImportError(
            "forge requires 'curl_cffi' for TLS impersonation and leak prevention.\n"
            "Install it via: pip install curl_cffi"
        )


class TLSSession:
    """Synchronous TLS session with locked browser fingerprint and proxy enforcement."""

    def __init__(self, proxy: Optional[str] = None, *, strict_proxy: bool = False):
        _check_engine()
        if strict_proxy and not proxy:
            raise EgressSecurityError(
                "Direct IP egress forbidden: strict_proxy=True requires a verified proxy URL."
            )

        self.proxy = proxy
        self.profile = get_impersonate_profile()
        self._s = cffi_requests.Session()
        self._s.impersonate = self.profile["impersonate"]
        if proxy:
            self._s.proxies = {"http": proxy, "https": proxy}

    def get(self, url: str, timeout: float = 12.0, **kwargs):
        return self._s.get(url, timeout=timeout, allow_redirects=True, **kwargs)

    def post(self, url: str, data: Any = None, json: Any = None, timeout: float = 12.0, **kwargs):
        return self._s.post(url, data=data, json=json, timeout=timeout, allow_redirects=True, **kwargs)

    def close(self) -> None:
        try:
            self._s.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class BrowserSession:
    """Session with a locked-in browser identity, headers, and TLS fingerprint."""

    def __init__(self, proxy_url: Optional[str] = None, *, strict_proxy: bool = False):
        _check_engine()
        if strict_proxy and not proxy_url:
            raise EgressSecurityError(
                "Direct IP egress forbidden: strict_proxy=True requires a verified proxy URL."
            )

        self.profile = random.choice(PROFILES)
        self.session = cffi_requests.Session()
        self.session.impersonate = self.profile["impersonate"]
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        self.headers = build_headers(self.profile, referer=random.choice(REFERERS))

    def get(self, url: str, timeout: float = 10.0, **kwargs):
        return self.session.get(url, headers=self.headers, timeout=timeout, **kwargs)

    def post(self, url: str, json: Any = None, timeout: float = 10.0, **kwargs):
        return self.session.post(url, json=json, headers=self.headers, timeout=timeout, **kwargs)

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AsyncTLSSession:
    """Asynchronous TLS session wrapping curl_cffi.AsyncSession."""

    def __init__(self, proxy: Optional[str] = None, *, strict_proxy: bool = False, impersonate: str = "chrome136"):
        _check_engine()
        if strict_proxy and not proxy:
            raise EgressSecurityError(
                "Direct IP egress forbidden: strict_proxy=True requires a verified proxy URL."
            )
        self.proxy = proxy
        self.impersonate = impersonate
        self._proxies = {"http": proxy, "https": proxy} if proxy else None
        self._session: Optional[Any] = None

    async def __aenter__(self):
        self._session = AsyncCffiSession(impersonate=self.impersonate, proxies=self._proxies)
        return self._session

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
