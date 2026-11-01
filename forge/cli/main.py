"""forge.cli.main - Command-line interface for forge toolkit."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Any, Optional

from forge.cards.bins import BIN_DB
from forge.cards.luhn import format_card, generate_random, is_luhn_valid
from forge.cards.storage import storage
from forge.cli.doctor import bad, bold, dim, ok, run_doctor, warn
from forge.identity.generator import (
    display_name,
    full_name,
    generate_dob,
    make_fullz,
    password,
    username,
)
from forge.identity.geo import COUNTRIES, COUNTRY_LABEL, GEO
from forge.transport.profiles import PROFILES, build_headers, get_impersonate_profile
from forge.transport.proxy import matching_proxy, verify_proxy
from forge.transport.session import EgressSecurityError, TLSSession

BANNER = r"""
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
   identity · fingerprint · cards · test harness (modular v3.0)
"""


def _ask(prompt: str, default: str = "") -> str:
    msg = f"  {prompt} [{default}]: " if default else f"  {prompt}: "
    val = input(msg).strip()
    return val if val else default


def cmd_id(a: argparse.Namespace) -> int:
    country = a.country.upper() if a.country else "US"
    fz = make_fullz(country, seed=a.seed)
    if a.json:
        print(json.dumps(fz, indent=2))
        return 0

    print(bold(f"\n forge identity — {COUNTRY_LABEL.get(country, country)}\n" + "─" * 48))
    for k, v in fz.items():
        print(f"  {k:<16}: {v}")
    print("─" * 48)
    return 0


def cmd_fp(a: argparse.Namespace) -> int:
    prof = get_impersonate_profile()
    hdrs = build_headers(prof)
    data = {"profile": prof, "headers": hdrs}
    if a.json:
        print(json.dumps(data, indent=2))
        return 0

    print(bold("\n forge fingerprint — browser profile\n" + "─" * 48))
    print(f"  impersonate     : {prof['impersonate']}")
    print(f"  user-agent      : {prof['ua'][:60]}...")
    print(f"  accept-language : {prof['accept_lang']}")
    print(f"  sec-ch-ua       : {prof.get('sec_ch_ua') or '(none)'}")
    print("─" * 48)
    return 0


def cmd_bin(a: argparse.Namespace) -> int:
    bin_ = a.bin
    cards = generate_random(bin_, a.month, a.year, a.count, card_storage=storage, seed=a.seed)
    if a.json:
        print(json.dumps(cards, indent=2))
        return 0

    print(bold(f"\n forge cards — BIN {bin_} ({len(cards)} items)\n" + "─" * 48))
    for c in cards:
        print(f"  {format_card(c, a.format)}")
    print("─" * 48)
    return 0


def cmd_mock_test(a: argparse.Namespace) -> int:
    """Placeholder harness for testing local endpoints (e.g. stripe-mock, local dev servers)."""
    target = a.url or os.environ.get("FORGE_LOCAL_TEST_URL", "http://127.0.0.1:12111")
    print(bold(f"\n forge local test harness\n" + "─" * 48))
    print(f"  Target Endpoint : {target}")
    print(f"  Mode            : Local Diagnostic & Functional Verification")

    try:
        # Local mock endpoints do not require proxies
        with TLSSession(proxy=None, strict_proxy=False) as s:
            r = s.get(target, timeout=5.0)
            status_text = ok(f"HTTP {r.status_code}") if r.status_code < 400 else bad(f"HTTP {r.status_code}")
            print(f"  Health Check    : {status_text} ({len(r.content)} bytes)")
    except Exception as e:
        print(warn(f"  Health Check    : Failed to reach local test target ({e})"))
        print(dim("  (Ensure local test mock server, e.g. stripe-mock or local app, is running)"))
        return 1

    print(ok("  Local test endpoint responded successfully."))
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    print(bold(BANNER))
    print(bold(" forge run — identity + proxy + test cards, one flow\n"))
    country = a.country or _ask("1. Select Country (US/JP/ID/DE/BR)", "US").upper()
    target = a.target or _ask("2. Target URL (Enter = skip probe)", "")
    count = int(_ask("3. How many test cards", "5"))

    print(f"\n{dim('─' * 52)}\n{bold('  [1/4] identity')}")
    fz = make_fullz(country)
    for k, v in fz.items():
        print(f"      {k:16}: {v}")

    print(bold("\n  [2/4] country-matched proxy"))
    px = matching_proxy(fz)
    proxy_url = ""
    if px and px.get("proxy"):
        vv = verify_proxy(px["proxy"], expect_country=country)
        print(f"      exit     : {vv.get('exit_ip') or px.get('host', '?')}  ({vv.get('country') or '?'})")
        if vv["ok"]:
            print(f"      {ok('verified')}  TLS handshake + geo match ({vv['status']})")
            proxy_url = px["proxy"]
        else:
            print(bad(f"      FAILED: {vv.get('error')} (direct IP egress forbidden)"))
    else:
        print(bad("      no proxy provider available (direct IP forbidden)"))

    print(bold("\n  [3/4] proxy ↔ target probe (TLS-fingerprinted)"))
    if target:
        if not proxy_url:
            print(bad("      probe aborted: valid proxy required (direct IP egress forbidden)"))
        else:
            try:
                with TLSSession(proxy_url, strict_proxy=True) as s:
                    r = s.get(target)
                m = ok(f"HTTP {r.status_code}") if r.status_code < 400 else bad(f"HTTP {r.status_code}")
                print(f"      {m} via proxy ({len(r.content)} bytes)")
            except Exception as e:
                print(bad(f"      unreachable: {type(e).__name__}: {e}"))
    else:
        print(dim("      skipped (no target given)"))

    print(bold("\n  [4/4] test cards"))
    cards = generate_random("414720", "09", "31", count, card_storage=storage)
    for c in cards:
        print(f"      {format_card(c, 'pipe')}")

    print(f"{dim('─' * 52)}\n{ok('✔')} workflow completed.\n")
    return 0


def cmd_selftest(a: argparse.Namespace) -> int:
    for c in COUNTRIES:
        fz = make_fullz(c)
        assert fz["country"] == c
        assert fz["name"] and fz["city"]
    print(f"selftest ok: identities ({', '.join(COUNTRIES)})")

    sample = generate_random("414720", "12", "29", 20, card_storage=storage)
    assert all(is_luhn_valid(c["pan"]) for c in sample)
    print(f"selftest ok: cards luhn {len(sample)}/{len(sample)} valid")
    print(f"selftest ok: profiles {len(PROFILES)} | database: {storage.db_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="forge",
        description="forge — identity · fingerprint · cards · test harness (modular v3.0)",
    )
    sub = p.add_subparsers(dest="cmd")

    # id
    p_id = sub.add_parser("id", help="Generate synthetic identity")
    p_id.add_argument("-c", "--country", choices=COUNTRIES, default="US")
    p_id.add_argument("--seed", type=int, default=None)
    p_id.add_argument("--json", action="store_true")

    # fp
    p_fp = sub.add_parser("fp", help="Generate browser fingerprint profile")
    p_fp.add_argument("--json", action="store_true")

    # bin
    p_bin = sub.add_parser("bin", help="Generate Luhn test cards")
    p_bin.add_argument("--bin", default="414720")
    p_bin.add_argument("-n", "--count", type=int, default=5)
    p_bin.add_argument("-m", "--month", default="12")
    p_bin.add_argument("-y", "--year", default="30")
    p_bin.add_argument("-f", "--format", choices=["pipe", "csv", "json"], default="pipe")
    p_bin.add_argument("--seed", type=int, default=None)
    p_bin.add_argument("--json", action="store_true")

    # doctor
    p_doc = sub.add_parser("doctor", help="Run system diagnostics")
    p_doc.add_argument("--json", action="store_true")

    # selftest
    sub.add_parser("selftest", help="Run offline unit checks")

    # run
    p_run = sub.add_parser("run", help="Interactive workflow wizard")
    p_run.add_argument("-c", "--country", choices=COUNTRIES, default=None)
    p_run.add_argument("-t", "--target", default=None)

    # test-mock
    p_mock = sub.add_parser("test-mock", help="Test local mock server (e.g. stripe-mock)")
    p_mock.add_argument("--url", default=None, help="Local mock endpoint URL")

    return p


def main() -> int:
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()
    try:
        if args.cmd == "id":
            return cmd_id(args)
        elif args.cmd == "fp":
            return cmd_fp(args)
        elif args.cmd == "bin":
            return cmd_bin(args)
        elif args.cmd == "doctor":
            return run_doctor(json_output=args.json)
        elif args.cmd == "selftest":
            return cmd_selftest(args)
        elif args.cmd == "run":
            return cmd_run(args)
        elif args.cmd == "test-mock":
            return cmd_mock_test(args)
        else:
            parser.print_help()
            return 0
    except KeyboardInterrupt:
        print("\n[!] Operation canceled by user (SIGINT). Exiting cleanly.")
        return 130
    except EgressSecurityError as err:
        print(bad(f"\n[CRITICAL SECURITY ERROR] {err}"))
        return 2


if __name__ == "__main__":
    sys.exit(main())
