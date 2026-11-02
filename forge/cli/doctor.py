"""forge.cli.doctor - Environment diagnostic and connectivity verification."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, List, Tuple

from forge.cards.bins import BIN_DB, validate_bin_db
from forge.cards.storage import storage
from forge.config import DEFAULT_PROXIES_FILE
from forge.transport.proxy import matching_proxy, urban_vpn_single, verify_proxy
from forge.transport.session import HAS_CURL_CFFI


def _c(code: str, s: str) -> str:
    if not sys.stdout.isatty():
        return s
    return f"\033[{code}m{s}\033[0m"


def ok(s: str) -> str: return _c("32", s)
def bad(s: str) -> str: return _c("31", s)
def warn(s: str) -> str: return _c("33", s)
def dim(s: str) -> str: return _c("2", s)
def bold(s: str) -> str: return _c("1", s)


def run_doctor(json_output: bool = False) -> int:
    """Execute system doctor checks."""
    checks: list[tuple[str, bool, str]] = []

    # 1. Python version
    v = sys.version_info
    checks.append(("python >= 3.10", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}"))

    # 2. curl_cffi TLS engine
    try:
        import curl_cffi
        cffi_ver = getattr(curl_cffi, "__version__", "unknown")
    except ImportError:
        cffi_ver = "missing"
    checks.append(("curl_cffi (TLS impersonate)", HAS_CURL_CFFI, f"v{cffi_ver} (required)"))

    # 3. SQLite Storage
    try:
        count = storage.total_count()
        checks.append(("sqlite wal storage", True, f"{storage.db_path} ({count} records)"))
    except Exception as e:
        checks.append(("sqlite wal storage", False, f"error: {e}"))

    # 3b. BIN database integrity (offline: fabrications are structural, not live)
    bin_errors = validate_bin_db()
    checks.append((
        "BIN database integrity",
        not bin_errors,
        f"{len(BIN_DB)} prefixes clean" if not bin_errors else f"{len(bin_errors)} violation(s): {bin_errors[0]}",
    ))

    # 4. Urban VPN Provider
    try:
        px = urban_vpn_single("US")
        checks.append((
            "urban_vpn provider",
            bool(px),
            f"exit {(px or {}).get('host', '?')}" if px else "no US server"
        ))
    except Exception as e:
        checks.append(("urban_vpn provider", False, f"{type(e).__name__}: {e}"))

    # 5. TLS probe via proxy (fail-closed, 100% routed through proxy)
    try:
        px = matching_proxy({"country": "US"})
        if px and px.get("proxy"):
            vv = verify_proxy(px["proxy"], expect_country="US")
            checks.append((
                "TLS probe via proxy",
                vv["ok"],
                f"{vv['exit_ip']} = {vv['country']}" if vv["ok"] else (vv["error"] or "?")
            ))
        else:
            checks.append(("TLS probe via proxy", False, "no proxy available"))
    except Exception as e:
        checks.append(("TLS probe via proxy", False, f"{type(e).__name__}: {e}"))

    # 6. Proxies configuration file
    has_proxy = DEFAULT_PROXIES_FILE.exists() or Path("proxies.txt").exists()
    p_path = str(DEFAULT_PROXIES_FILE if DEFAULT_PROXIES_FILE.exists() else "proxies.txt")
    checks.append((
        "proxies file",
        has_proxy,
        p_path if has_proxy else f"optional template: {DEFAULT_PROXIES_FILE}"
    ))

    # 7. Forge binary on PATH
    forge_bin = shutil.which("forge")
    checks.append(("forge on PATH", forge_bin is not None, forge_bin or "run: pip install -e ."))

    if json_output:
        res = [{"check": name, "ok": good, "detail": detail} for name, good, detail in checks]
        print(json.dumps(res, indent=2))
        return 0 if all(c[1] for c in checks if "optional" not in c[2]) else 1

    print(bold("\n forge doctor — modular v3.0\n" + "─" * 54))
    fails = 0
    for name, good, detail in checks:
        icon = ok("✔") if good else (warn("!") if "optional" in detail else bad("✘"))
        print(f"  {icon} {name:<26} {dim(detail)}")
        if not good and "optional" not in detail:
            fails += 1
    print("─" * 54)

    if not fails:
        print(ok("  all required checks passed") + dim("  (production ready)"))
        return 0
    print(bad(f"  {fails} required check(s) failed"))
    return 1
