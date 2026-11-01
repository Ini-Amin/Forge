"""forge.cli.main - Command-line interface for forge toolkit."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from typing import Any, Optional

from forge.cards.bins import BIN_DB, get_default_bin_for_country, issuer_lookup
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
COUNTRY_CURRENCY = {
    "US": "USD",
    "JP": "JPY",
    "ID": "IDR",
    "DE": "EUR",
    "BR": "BRL",
}
from forge.transport.proxy import matching_proxy, verify_proxy
from forge.transport.session import EgressSecurityError, TLSSession
from forge.defenders import (
    BotTelemetryAuditor,
    CurrencyPrecisionAuditor,
    DefenseMaturityEvaluator,
    FraudRiskAuditor,
    RaceConditionAuditor,
    TransactionFunnelSimulator,
)
from forge.payments.decline_codes import DeclineCodeTaxonomy
from forge.payments.state_machine import PaymentStateMachine
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
    print(bold(" 🛠️  FORGE UNIFIED DEFENSIVE EMULATION PIPELINE\n"))

    # 1. Inputs: Region, Target URL, Card Count
    country = getattr(a, "country", None) or _ask("1. Target Region (US/JP/ID/DE/BR)", "US").upper()
    if country not in COUNTRIES:
        country = "US"

    target = getattr(a, "target", None)
    if target is None:
        target = _ask("2. Target Endpoint URL (Enter = offline staging audit)", "").strip()

    count_val = getattr(a, "count", None)
    count = int(count_val) if count_val else int(_ask("3. Number of test card fixtures", "5"))

    print(f"\n{dim('━' * 60)}")
    print(bold(f"  [1/5] SYNTHETIC IDENTITY & REGIONAL PROFILE ({country})"))
    fz = make_fullz(country)
    id_name = GEO[country].get("id_name", "national_id")
    print(f"      Name     : {bold(fz['name'])}")
    print(f"      Address  : {fz['address']}, {fz['city']}, {fz['state']} {fz['zip']}")
    print(f"      Phone    : {fz['phone']}")
    print(f"      {id_name.upper():<9}: {fz[id_name]}")

    print(bold("\n  [2/5] GEO-MATCHED EGRESS & TLS HANDSHAKE"))
    px = matching_proxy(fz)
    proxy_url = ""
    exit_meta = {"country": country, "asn_type": "residential"}
    if px and px.get("proxy"):
        vv = verify_proxy(px["proxy"], expect_country=country)
        exit_ip = vv.get("exit_ip") or px.get("host", "?")
        exit_country = vv.get("country") or country
        exit_meta = {"country": exit_country, "asn_type": "residential"}
        if vv["ok"]:
            print(f"      Exit IP  : {exit_ip} ({exit_country}) — {ok('TLS 1.3 Verified')}")
            proxy_url = px["proxy"]
        else:
            print(bad(f"      Exit IP  : {exit_ip} — FAILED ({vv.get('error')})"))
            print(bad("      Security : Direct IP egress forbidden. Halting live probe."))
    else:
        print(warn("      Proxy    : No proxy available. Evaluating offline diagnostics."))

    prof = get_impersonate_profile()
    hdrs = build_headers(prof)
    idemp_key = f"forge_{int(time.time())}_{random.randint(1000, 9999)}"
    hdrs["Idempotency-Key"] = idemp_key

    # Live target probe if specified
    print(bold("\n  [3/5] TARGET ENDPOINT PROBE & TIMING"))
    if target:
        if not proxy_url:
            print(warn("      Target probe skipped: strict fail-closed requires verified proxy."))
        else:
            try:
                start_t = time.monotonic()
                with TLSSession(proxy_url, strict_proxy=True) as s:
                    r = s.get(target, timeout=10.0, headers=hdrs)
                dur = (time.monotonic() - start_t) * 1000.0
                st_code = r.status_code
                status_badge = ok(f"HTTP {st_code}") if st_code < 400 else bad(f"HTTP {st_code}")
                print(f"      Target   : {target}")
                print(f"      Response : {status_badge} ({len(r.content)} bytes in {dur:.1f}ms)")
            except Exception as e:
                print(bad(f"      Target   : {target} — Unreachable ({e})"))
    else:
        print(dim("      Target   : Offline mode (evaluating staging defense layers)"))

    # 4-Layer Funnel Simulation
    print(bold("\n  [4/5] 4-LAYER TRANSACTION FUNNEL SIMULATION"))
    bin_ = getattr(a, "bin", None) or get_default_bin_for_country(country)
    card_meta = issuer_lookup(bin_)
    funnel = TransactionFunnelSimulator.evaluate(hdrs, fz, card_meta, exit_meta, prof)

    for l in funnel.layers:
        v_icon = ok("✔") if l.verdict == "PASS" else (warn("!") if l.verdict == "FLAG" else bad("✘"))
        print(f"      {v_icon} {l.layer_name:<22} [{l.verdict:<5}] (+{l.score_penalty} pts, {l.latency_ms}ms)")
        for d in l.details:
            print(dim(f"          • {d}"))

    disp_badge = ok(funnel.final_disposition) if funnel.final_disposition == "SETTLED" else (
        warn(funnel.final_disposition) if "3DS" in funnel.final_disposition else bad(funnel.final_disposition)
    )
    print(f"\n      Funnel Result : {disp_badge} (Total Risk: {funnel.total_risk_score}/100)")
    if funnel.vulnerabilities_detected:
        for v in funnel.vulnerabilities_detected:
            print(bad(f"      ! VULNERABILITY: {v}"))

    # Currency & Luhn Test Cards
    curr = COUNTRY_CURRENCY.get(country, "USD")
    curr_chk = CurrencyPrecisionAuditor.audit_amount_to_units(curr, 100.0)
    print(bold(f"\n  [5/5] REGIONAL CURRENCY & CARD FIXTURES ({curr})"))
    print(f"      Currency : {curr} (Zero-Decimal: {curr_chk.is_zero_decimal})")
    print(f"      Fixtures : {count} Luhn ISO/IEC 7812 test cards generated ({card_meta['network']} - {card_meta['issuer']}):")
    cards = generate_random(bin_, "12", "30", count, card_storage=storage)
    for c in cards:
        print(f"          • {format_card(c, 'pipe')}")

    print(f"\n{dim('━' * 60)}")
    print(ok("  ✔ Unified Forge evaluation completed successfully.\n"))
    return 0

def cmd_audit_risk(a: argparse.Namespace) -> int:
    country = a.country.upper() if a.country else "US"
    fz = make_fullz(country)
    bin_ = a.bin if (getattr(a, "bin", None) and a.bin != "414720") else get_default_bin_for_country(country)
    card_meta = issuer_lookup(bin_)
    exit_meta = {"country": px.get("country", country) if px else ""}
    prof = get_impersonate_profile()

    audit = FraudRiskAuditor.full_audit(fz, card_meta, exit_meta, prof)
    if a.json:
        print(json.dumps(audit, indent=2))
        return 0

    print(bold(f"\n forge fraud risk audit — {country}\n" + "─" * 52))
    print(f"  Risk Score        : {audit['total_risk_score']}/100")
    print(f"  Radar Decision    : {audit['radar_decision']}")
    print(f"  3DS Frictionless  : {'YES' if audit['frictionless_eligible'] else 'NO (Challenge Required)'}")
    print(dim("─" * 52))
    print(f"  AVS Code          : {audit['components']['avs']['avs_code']} (Penalty: {audit['components']['avs']['risk_penalty']})")
    print(f"  Geo-IP Egress     : {audit['components']['geo_egress']['egress_country']} (Penalty: {audit['components']['geo_egress']['risk_penalty']})")
    print(f"  TLS Profile       : {audit['components']['fingerprint']['tls_profile']} (Penalty: {audit['components']['fingerprint']['risk_penalty']})")
    if audit['components']['avs']['reasons']:
        for r in audit['components']['avs']['reasons']:
            print(warn(f"    ! AVS: {r}"))
    if audit['components']['geo_egress']['reasons']:
        for r in audit['components']['geo_egress']['reasons']:
            print(warn(f"    ! Geo: {r}"))
    print("─" * 52)
    return 0


def cmd_decline(a: argparse.Namespace) -> int:
    analysis = DeclineCodeTaxonomy.analyze(a.code)
    if a.json:
        print(json.dumps(analysis.__dict__, indent=2))
        return 0

    print(bold(f"\n forge decline analyzer — {a.code}\n" + "─" * 52))
    print(f"  Category          : {analysis.category}")
    print(f"  Retryable         : {'YES' if analysis.is_retryable else 'NO (Hard Decline)'}")
    print(f"  ISO 8583 Code     : {analysis.iso_8583_equivalent}")
    print(f"  Description       : {analysis.description}")
    print(f"  Remediation       : {analysis.recommended_action}")
    print("─" * 52)
    return 0
def cmd_funnel(a: argparse.Namespace) -> int:
    country = a.country.upper() if a.country else "US"
    bin_ = a.bin if (getattr(a, "bin", None) and a.bin != "414720") else get_default_bin_for_country(country)
    card_meta = issuer_lookup(bin_)
    exit_meta = {"country": px.get("country", country) if px else "", "asn_type": "residential"}
    prof = get_impersonate_profile()
    hdrs = build_headers(prof)
    if a.idempotency:
        hdrs["Idempotency-Key"] = "test_key_123"

    res = TransactionFunnelSimulator.evaluate(hdrs, fz, card_meta, exit_meta, prof)
    if a.json:
        data = {
            "final_disposition": res.final_disposition,
            "total_latency_ms": res.total_latency_ms,
            "total_risk_score": res.total_risk_score,
            "layers": [l.__dict__ for l in res.layers],
            "vulnerabilities": res.vulnerabilities_detected,
            "recommendations": res.recommendations,
        }
        print(json.dumps(data, indent=2))
        return 0

    print(bold(f"\n forge transaction funnel simulator — {country}\n" + "─" * 56))
    print(f"  Final Disposition : {bold(res.final_disposition)}")
    print(f"  Total Latency     : {res.total_latency_ms:.1f} ms")
    print(f"  Total Risk Score  : {res.total_risk_score}/100")
    print(dim("─" * 56))
    for l in res.layers:
        v_icon = ok("✔") if l.verdict == "PASS" else (warn("!") if l.verdict == "FLAG" else bad("✘"))
        print(f"  {v_icon} {l.layer_name:<20} [{l.verdict}] (+{l.score_penalty} pts, {l.latency_ms}ms)")
        for d in l.details:
            print(dim(f"      • {d}"))

    if res.vulnerabilities_detected:
        print(dim("─" * 56))
        print(bad("  Vulnerabilities Identified:"))
        for v in res.vulnerabilities_detected:
            print(bad(f"    ✘ {v}"))
    if res.recommendations:
        print(dim("─" * 56))
        print(ok("  Defense Recommendations:"))
        for r in res.recommendations:
            print(ok(f"    ✔ {r}"))
    print("─" * 56)
    return 0


def cmd_currency(a: argparse.Namespace) -> int:
    if a.edge_cases:
        checks = CurrencyPrecisionAuditor.test_rounding_edge_cases(a.currency)
        if a.json:
            print(json.dumps([c.__dict__ for c in checks], indent=2))
            return 0
        print(bold(f"\n forge currency rounding edge cases — {a.currency}\n" + "─" * 56))
        for c in checks:
            h_icon = warn("!") if c.has_rounding_hazard else ok("✔")
            print(f"  {h_icon} Input: {c.input_amount:<10} -> Smallest Units: {c.expected_integer_units:<8} (Hazard: {c.has_rounding_hazard})")
        print("─" * 56)
        return 0

    chk = CurrencyPrecisionAuditor.audit_amount_to_units(a.currency, a.amount)
    if a.json:
        print(json.dumps(chk.__dict__, indent=2))
        return 0

    print(bold(f"\n forge currency precision audit — {chk.currency}\n" + "─" * 56))
    print(f"  Input Amount      : {chk.input_amount}")
    print(f"  Integer Units     : {chk.expected_integer_units}")
    print(f"  Zero-Decimal      : {chk.is_zero_decimal}")
    print(f"  Rounding Hazard   : {warn('YES') if chk.has_rounding_hazard else ok('NO')}")
    print(f"  Recommendation    : {chk.recommendation}")
    print("─" * 56)
    return 0


def cmd_maturity(a: argparse.Namespace) -> int:
    matrix = DefenseMaturityEvaluator.calculate_confusion_matrix(tp=95, tn=980, fp=20, fn=5)
    latencies = [15.2, 22.4, 45.1, 88.0, 112.5, 140.2, 210.0, 310.5, 450.0, 620.0]
    lat = DefenseMaturityEvaluator.benchmark_latency(latencies)
    sample_log = {
        "transaction_id": "tx_staging_123",
        "timestamp_utc": "2026-11-01T08:00:00Z",
        "client_ip": "146.70.228.82",
        "egress_asn": "AS9009",
        "tls_ja4_fingerprint": "t13d1516h2_8daaf6152771_b0da82dd1658",
        "avs_code": "Y",
        "cvv_result": "match",
        "iso_8583_response_code": "00",
        "decision": "ALLOW",
        "rule_id": "rule_default_allow",
    }
    audit = DefenseMaturityEvaluator.audit_trail_completeness(sample_log)

    if a.json:
        data = {
            "confusion_matrix": matrix.__dict__,
            "latency_percentiles": lat.__dict__,
            "audit_trail_completeness": audit.__dict__,
        }
        print(json.dumps(data, indent=2))
        return 0

    print(bold("\n forge defense maturity scorecard\n" + "─" * 56))
    print(bold("  [1] Precision & Tradeoff Metrics"))
    print(f"      False Positive Rate : {matrix.false_positive_rate:.2%} (Conversion Loss Risk)")
    print(f"      False Negative Rate : {matrix.false_negative_rate:.2%} (Fraud Exposure Risk)")
    print(f"      F1-Score / Accuracy : {matrix.f1_score:.4f}")
    print(dim(f"      Assessment          : {matrix.business_impact_summary}"))

    print(bold("\n  [2] Detection Latency Percentiles"))
    print(f"      p50 (Median)        : {lat.p50_ms} ms")
    print(f"      p95 Percentile      : {lat.p95_ms} ms")
    print(f"      p99 Percentile      : {lat.p99_ms} ms")
    print(f"      Status              : {warn('Degraded (>500ms)') if lat.is_checkout_degraded else ok('Optimal')}")

    print(bold("\n  [3] Forensic Audit Trail Index"))
    print(f"      Completeness        : {audit.completeness_percentage}% ({audit.fields_present}/{audit.total_fields_required} fields)")
    print(f"      Compliance Grade    : {ok(audit.compliance_grade)}")
    print("─" * 56)
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

    # audit
    p_audit = sub.add_parser("audit", help="Audit transaction telemetry against fraud scoring heuristics")
    p_audit.add_argument("-c", "--country", choices=COUNTRIES, default="US")
    p_audit.add_argument("--bin", default="414720")
    p_audit.add_argument("--json", action="store_true")

    # decline
    p_dec = sub.add_parser("decline", help="Analyze gateway/issuer decline code and ISO 8583 mapping")
    p_dec.add_argument("code", help="Decline code (e.g. authentication_required, insufficient_funds, stolen_card)")
    p_dec.add_argument("--json", action="store_true")
    # funnel
    p_funnel = sub.add_parser("funnel", help="Simulate transaction traversal across 4 defensive layers")
    p_funnel.add_argument("-c", "--country", choices=COUNTRIES, default="US")
    p_funnel.add_argument("--bin", default="414720")
    p_funnel.add_argument("--idempotency", action="store_true", help="Include Idempotency-Key header")
    p_funnel.add_argument("--json", action="store_true")

    # currency
    p_curr = sub.add_parser("currency", help="Audit currency conversion, zero-decimal, and fractional precision")
    p_curr.add_argument("--currency", default="USD")
    p_curr.add_argument("--amount", type=float, default=10.00)
    p_curr.add_argument("--edge-cases", action="store_true", help="Run common rounding edge cases")
    p_curr.add_argument("--json", action="store_true")

    # maturity
    p_mat = sub.add_parser("maturity", help="Generate defensive maturity and latency scorecard")
    p_mat.add_argument("--json", action="store_true")
    return p


def main() -> int:
    parser = build_parser()
    if len(sys.argv) == 1:
        # Default zero-friction UX: launch unified wizard immediately
        return cmd_run(argparse.Namespace(country=None, target=None, count=None, json=False, cmd="run"))

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
        elif args.cmd == "audit":
            return cmd_audit_risk(args)
        elif args.cmd == "decline":
            return cmd_decline(args)
        elif args.cmd == "funnel":
            return cmd_funnel(args)
        elif args.cmd == "currency":
            return cmd_currency(args)
        elif args.cmd == "maturity":
            return cmd_maturity(args)
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
