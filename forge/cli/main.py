"""forge.cli.main - Command-line interface for forge toolkit."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from forge.cards.bins import (
    BIN_DB,
    bins_by,
    get_default_bin_for_country,
    issuer_lookup,
    supported_countries,
)
from forge.cards.luhn import format_card, generate_random, is_luhn_valid
from forge.cards.storage import CardStorage, storage
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
from forge.config import DATA_DIR
COUNTRY_CURRENCY = {
    "US": "USD",
    "GB": "GBP",
    "JP": "JPY",
    "ID": "IDR",
    "DE": "EUR",
    "BR": "BRL",
    "CA": "CAD",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "AU": "AUD",
    "SG": "SGD",
    "NL": "EUR",
    "SE": "SEK",
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
from forge.payments.idempotency import IdempotencyManager
from forge.payments.state_machine import PaymentStateMachine

def is_local_or_private_target(url: str) -> bool:
    """Return True if target is a loopback, local development, or private network address."""
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False
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


def _parse_latencies(raw: str) -> list[float]:
    """Turn '15.2,22.4,45.1' into floats, rejecting anything unparseable."""
    try:
        values = [float(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(f"latencies must be comma-separated numbers, got {raw!r}")
    if not values:
        raise argparse.ArgumentTypeError("at least one latency sample is required")
    return values


def _egress_meta(a: argparse.Namespace) -> dict[str, str]:
    """Build the egress description from what the caller stated.

    `audit` and `funnel` used to call matching_proxy(), which reached a
    third-party VPN API with a 12s timeout and then defaulted to "residential
    in your own billing country". Both halves were invention: the score passed
    a geo check nobody had performed. Unknown stays unknown.
    """
    return {
        "country": (getattr(a, "egress_country", None) or "").upper(),
        "asn_type": getattr(a, "asn_type", None) or "unknown",
    }


def _resolve_bin_or_fail(a: argparse.Namespace, country: Optional[str]) -> Optional[str]:
    """Pick the BIN for this run, or None after printing why it cannot.

    One implementation for `bin`, `audit` and `funnel`, because a hardcoded
    parser default of 414720 made "not supplied" indistinguishable from
    "supplied as Chase US", and a sentinel comparison on that value silently
    overrode an explicit --bin.
    """
    explicit = getattr(a, "bin", None)
    if explicit:
        meta = issuer_lookup(explicit)
        if not meta["bin_known"] and not getattr(a, "allow_unknown_bin", False):
            print(bad(f"BIN {explicit} is not in the issuer database; country and currency are unknown."))
            print(dim("A card that cannot be tied to an issuer breaks geo-coherence silently."))
            print(dim("Use `forge issuer list` to pick a known prefix, or pass --allow-unknown-bin "
                      "to continue with issuer metadata marked unavailable."))
            return None
        return explicit

    cc = (country or "US").upper()
    default_bin = get_default_bin_for_country(cc)
    if default_bin is None:
        db_has = {m["country"].upper() for m in BIN_DB.values()}
        if cc.upper() in db_has:
            print(bad(f"No default BIN for {cc} — the identity pipeline does not cover it yet."))
            print(dim("Use `forge issuer list --country " + cc + "` and pass --bin explicitly."))
        else:
            print(bad(f"No BIN on file for {cc}; refusing to substitute another country's card."))
            print(dim(f"Countries with a coherent BIN: {', '.join(supported_countries())}"))
        return None
    return default_bin


def cmd_id(a: argparse.Namespace) -> int:
    country = a.country.upper() if a.country else "US"
    fz = make_fullz(country, seed=a.seed)
    if a.card:
        default_bin = get_default_bin_for_country(country)
        if default_bin is None:
            print(bad(f"No BIN on file for {country}; refusing to attach another country's card."))
            print(dim(f"Countries with a coherent BIN: {', '.join(supported_countries())}"))
            return 1
        meta = issuer_lookup(default_bin)
        fz["card_bin"] = default_bin
        fz["card_network"] = meta["network"]
        fz["card_issuer"] = meta["issuer"]
        fz["card_currency"] = meta["currency"]
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
    """Generate card fixtures. Refuses to guess when the prefix or country is
    unknown, because a fixture carrying another country's issuer is not a
    fixture, it is a wrong answer that looks right."""
    bin_ = _resolve_bin_or_fail(a, a.country)
    if bin_ is None:
        return 1

    cards = generate_random(bin_, a.month, a.year, a.count, card_storage=storage, seed=a.seed)
    if a.json:
        print(json.dumps(cards, indent=2))
        return 0
    print(bold(f"\n forge cards — BIN {bin_} ({len(cards)} items)\n" + "─" * 48))
    for c in cards:
        print(f"  {format_card(c, a.format)}")
    print("─" * 48)
    return 0


def cmd_issuer(a: argparse.Namespace) -> int:
    if a.subcommand == "list":
        rows = bins_by(network=getattr(a, "network", None), country=getattr(a, "country", None))
        if getattr(a, "issuer", None):
            rows = {b: m for b, m in rows.items() if a.issuer.lower() in m["issuer"].lower()}
        if a.json:
            print(json.dumps([{"bin": b, **m} for b, m in sorted(rows.items(), key=lambda kv: (kv[1]["country"], kv[0]))], indent=2))
            return 0
        if not rows:
            print("No issuers match")
            return 1
        width_bin = max(len(b) for b in rows)
        print(f"\n forge issuer — {len(rows)} result(s)\n" + "─" * 56)
        for b, m in sorted(rows.items(), key=lambda kv: (kv[1]["country"], kv[0])):
            flags = []
            if m.get("is_prepaid"):
                flags.append("prepaid")
            print(f"  {b:<{width_bin}}  {m['network']:<13} {m['issuer']:<24} {m['country']} {m['currency']} {m['funding']}"
                  + (" " + " ".join(flags) if flags else ""))
        print("─" * 56)
        return 0
    if a.subcommand == "lookup":
        meta = issuer_lookup(a.query)
        if not meta["bin_known"] and meta["network"] == "Unknown":
            print(f"Unknown BIN/pan prefix: {a.query}")
            return 1
        if a.json:
            print(json.dumps(meta, indent=2))
            return 0
        print(f"\n forge issuer lookup — {a.query}\n" + "─" * 56)
        for key in ("bin", "network", "issuer", "country", "currency", "funding"):
            print(f"  {key:<12}: {meta[key]}")
        print(f"  pan_length   : {meta['pan_length']}")
        print(f"  bin_length   : {meta['bin_length']}")
        print(f"  bin_known    : {meta['bin_known']}")
        print(f"  is_prepaid   : {meta.get('is_prepaid', False)}")
        print("─" * 56)
        return 0
    if a.subcommand == "default":
        bin_ = get_default_bin_for_country(a.country.upper())
        if a.json:
            print(json.dumps({"country": a.country, "bin": bin_, **issuer_lookup(bin_)}, indent=2))
            return 0
        meta = issuer_lookup(bin_)
        print(f"forge issuer default — {a.country.upper()}\n" + "─" * 56)
        for key in ("bin", "network", "issuer", "country", "currency", "funding"):
            print(f"  {key:<12}: {meta[key]}")
        print(f"  pan_length   : {meta['pan_length']}")
        print(f"  bin_length   : {meta['bin_length']}")
        print("─" * 56)
        return 0
    return 1


def cmd_run(a: argparse.Namespace) -> int:
    print(bold(BANNER))
    print(bold(" 🛠️  FORGE UNIFIED DEFENSIVE EMULATION PIPELINE\n"))

    tty = sys.stdin.isatty()

    # 1. Inputs: Region, Target URL, Card Count
    country = getattr(a, "country", None) or (_ask("1. Target Region (US/GB/JP/ID/DE/BR/CA/FR/IT/ES/AU/SG/NL/SE)", "US").upper() if tty else "US")
    if country not in COUNTRIES:
        country = "US"

    target = getattr(a, "target", None)
    if target is None:
        target = _ask("2. Target Endpoint URL (Enter = offline staging audit)", "").strip() if tty else ""

    auth_token = getattr(a, "auth", None) or os.environ.get("FORGE_AUTH_TOKEN", "")
    if target and not auth_token and tty:
        auth_token = _ask("3. Authorization Bearer / Token (Enter = none)", "").strip()

    count_val = getattr(a, "count", None)
    count = int(count_val) if count_val else int(_ask("4. Number of test card fixtures", "5") if tty else "5")
    count = min(count, 50)

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
    # Egress is unknown until a proxy actually verifies. Claiming the billing
    # country here made every no-proxy run look geo-coherent by construction.
    exit_meta = {"country": "", "asn_type": getattr(a, "asn_type", None) or "unknown"}
    if px and px.get("proxy"):
        vv = verify_proxy(px["proxy"], expect_country=country)
        exit_ip = vv.get("exit_ip") or px.get("host", "?")
        exit_country = vv.get("country") or ""
        exit_meta = {"country": exit_country, "asn_type": getattr(a, "asn_type", None) or "unknown"}
        if vv["ok"]:
            print(f"      Exit IP  : {exit_ip} ({exit_country or 'country undetermined'}) — {ok('TLS 1.3 Verified')}")
            proxy_url = px["proxy"]
        else:
            print(bad(f"      Exit IP  : {exit_ip} — FAILED ({vv.get('error')})"))
            print(bad("      Security : Direct IP egress forbidden. Halting live probe."))
    else:
        print(warn("      Proxy    : No proxy available. Evaluating offline diagnostics."))

    prof = get_impersonate_profile()
    hdrs = build_headers(prof)
    idemp_key = IdempotencyManager().generate_key(target or "offline")
    hdrs["Idempotency-Key"] = idemp_key
    if auth_token:
        hdrs["Authorization"] = f"Bearer {auth_token}" if not auth_token.startswith("Bearer ") else auth_token

    curr = COUNTRY_CURRENCY.get(country, "USD")
    method = getattr(a, "method", None)
    if not method and target:
        # Detect whether endpoint expects mutation POST vs informational GET
        method = "POST" if any(p in target.lower() for p in ("/checkout", "/pay", "/charge", "/confirm", "/intent", "/v1/")) else "GET"
    method = (method or "GET").upper()

    # Live target probe if specified
    print(bold("\n  [3/5] TARGET ENDPOINT PROBE & TIMING"))
    if target:
        is_private = is_local_or_private_target(target)
        if not is_private and not proxy_url:
            print(warn("      Target probe skipped: strict fail-closed requires verified proxy for public targets."))
        else:
            active_proxy = None if is_private else proxy_url
            strict = not is_private
            route_label = "direct internal target" if is_private else "via verified proxy"
            probe_result = None
            try:
                start_t = time.monotonic()
                with TLSSession(active_proxy, strict_proxy=strict) as s:
                    if method == "POST":
                        probe_payload = {"session_id": idemp_key, "amount": 100, "currency": curr.lower()}
                        r = s.post(target, json=probe_payload, timeout=10.0, headers=hdrs)
                    else:
                        r = s.get(target, timeout=10.0, headers=hdrs)
                dur = (time.monotonic() - start_t) * 1000.0
                st_code = r.status_code
                probe_result = {"status_code": st_code, "latency_ms": dur, "headers": dict(r.headers)}
                status_badge = ok(f"HTTP {st_code}") if st_code < 400 else bad(f"HTTP {st_code}")
                print(f"      Target   : {target} [{method}] ({route_label})")
                print(f"      Response : {status_badge} ({len(r.content)} bytes in {dur:.1f}ms)")
            except Exception as e:
                print(bad(f"      Target   : {target} [{method}] — Unreachable ({e})"))
    else:
        print(dim("      Target   : Offline mode (evaluating staging defense layers)"))
    # 4-Layer Funnel Simulation
    print(bold("\n  [4/5] 4-LAYER TRANSACTION FUNNEL SIMULATION"))
    bin_ = _resolve_bin_or_fail(a, country)
    if bin_ is None:
        return 1
    card_meta = issuer_lookup(bin_)
    funnel = TransactionFunnelSimulator.evaluate(
        hdrs, fz, card_meta, exit_meta, prof,
        probe=probe_result if target else None,
    )

    for l in funnel.layers:
        v_icon = ok("✔") if l.verdict == "PASS" else (warn("!") if l.verdict == "FLAG" else bad("✘"))
        lat_txt = f"{l.latency_ms}ms" if l.latency_ms is not None else "not measured"
        print(f"      {v_icon} {l.layer_name:<22} [{l.verdict:<5}] (+{l.score_penalty} pts, {lat_txt})")
        for d in l.details:
            print(dim(f"          • {d}"))

    disp_badge = warn(funnel.final_disposition) if funnel.final_disposition in ("AUTHORIZED", "CHALLENGE_3DS") else bad(funnel.final_disposition)
    print(f"\n      Funnel Result : {disp_badge} (Total Risk: {funnel.total_risk_score}/100)")
    if funnel.vulnerabilities_detected:
        for v in funnel.vulnerabilities_detected:
            print(bad(f"      ! VULNERABILITY: {v}"))

    # Currency & Luhn Test Cards
    curr = COUNTRY_CURRENCY.get(country, "USD")
    curr_chk = CurrencyPrecisionAuditor.audit_amount_to_units(curr, 100.0)
    print(bold(f"\n  [5/5] REGIONAL CURRENCY & CARD FIXTURES ({curr})"))
    print(f"      Currency : {curr} (Zero-Decimal: {curr_chk.is_zero_decimal})")
    cards = generate_random(bin_, exp_m="auto", exp_y="auto", count=count, card_storage=storage)
    for c in cards:
        print(f"          • {format_card(c, 'pipe')}")

    # Save audit trail report artifact
    audit_data = {
        "timestamp": time.time(),
        "country": country,
        "target": target or None,
        "method": method if target else None,
        "identity": fz,
        "egress": exit_meta,
        "funnel": {
            "final_disposition": funnel.final_disposition,
            "total_risk_score": funnel.total_risk_score,
            "layers": [l.__dict__ for l in funnel.layers],
            "vulnerabilities": funnel.vulnerabilities_detected,
            "recommendations": funnel.recommendations,
            "money_lifecycle": [l.__dict__ for l in funnel.money_lifecycle],
            "rails_state": funnel.rails_state,
        },
        "currency": curr,
        "cards": cards,
    }
    out_file = Path(getattr(a, "output", None) or (DATA_DIR / "last_audit.json"))
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(audit_data, indent=2))
        print(f"\n      Audit Log: Saved report artifact to {out_file}")
    except Exception:
        pass

    print(f"\n{dim('━' * 60)}")
    print(ok("  ✔ Unified Forge evaluation completed successfully.\n"))
    return 0

def cmd_audit_risk(a: argparse.Namespace) -> int:
    country = a.country.upper() if a.country else "US"
    bin_ = _resolve_bin_or_fail(a, country)
    if bin_ is None:
        return 1
    fz = make_fullz(country)
    card_meta = issuer_lookup(bin_)
    exit_meta = _egress_meta(a)
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
    bin_ = _resolve_bin_or_fail(a, country)
    if bin_ is None:
        return 1
    fz = make_fullz(country)
    card_meta = issuer_lookup(bin_)
    exit_meta = _egress_meta(a)
    prof = get_impersonate_profile()
    hdrs = build_headers(prof)
    if a.idempotency:
        hdrs["Idempotency-Key"] = IdempotencyManager().generate_key("funnel-sim")

    res = TransactionFunnelSimulator.evaluate(hdrs, fz, card_meta, exit_meta, prof)
    if a.json:
        data = {
            "final_disposition": res.final_disposition,
            "total_latency_ms": res.total_latency_ms,
            "total_risk_score": res.total_risk_score,
            "layers": [l.__dict__ for l in res.layers],
            "vulnerabilities": res.vulnerabilities_detected,
            "recommendations": res.recommendations,
            "money_lifecycle": [s.__dict__ for s in res.money_lifecycle],
            "rails_state": res.rails_state,
        }
        print(json.dumps(data, indent=2))
        return 0

    print(bold(f"\n forge transaction funnel simulator — {country}\n" + "─" * 56))
    print(f"  Final Disposition : {bold(res.final_disposition)}")
    print(f"  Total Latency     : {res.total_latency_ms:.1f} ms" if res.total_latency_ms is not None
          else "  Total Latency     : not measured (no live probe)")
    print(f"  Total Risk Score  : {res.total_risk_score}/100")
    print(dim("─" * 56))
    for l in res.layers:
        v_icon = ok("✔") if l.verdict == "PASS" else (warn("!") if l.verdict == "FLAG" else bad("✘"))
        lat_txt = f"{l.latency_ms}ms" if l.latency_ms is not None else "not measured"
        print(f"  {v_icon} {l.layer_name:<20} [{l.verdict}] (+{l.score_penalty} pts, {lat_txt})")
        for d in l.details:
            print(dim(f"      • {d}"))

    print(dim("─" * 56))
    print(f"  Rail State       : {dim(res.rails_state)}")
    print(dim("  Money Lifecycle:"))
    for s in res.money_lifecycle:
        print(dim(f"  {s.stage} : {s.verdict} — {s.detail}"))

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
    """Score a real defence run. Every number is parsed from input or read from a
    file; the command refuses to print a scorecard it invented."""
    matrix = DefenseMaturityEvaluator.calculate_confusion_matrix(
        tp=a.tp, tn=a.tn, fp=a.fp, fn=a.fn
    )
    lat = DefenseMaturityEvaluator.benchmark_latency(a.latencies)

    audit = None
    if a.audit_log:
        try:
            with open(a.audit_log) as fh:
                audit = DefenseMaturityEvaluator.audit_trail_completeness(json.load(fh))
        except (OSError, json.JSONDecodeError) as e:
            print(bad(f"Cannot read audit log {a.audit_log}: {e}"))
            return 1

    if a.json:
        data = {
            "confusion_matrix": matrix.__dict__,
            "latency_percentiles": lat.__dict__,
            "audit_trail_completeness": audit.__dict__ if audit else None,
        }
        print(json.dumps(data, indent=2))
        return 0

    print(bold("\n forge defense maturity scorecard\n" + "─" * 56))
    print(bold("  [1] Precision & Tradeoff Metrics"))
    print(dim(f"      counts              : tp={a.tp} tn={a.tn} fp={a.fp} fn={a.fn}"))
    print(f"      False Positive Rate : {matrix.false_positive_rate:.2%} (Conversion Loss Risk)")
    print(f"      False Negative Rate : {matrix.false_negative_rate:.2%} (Fraud Exposure Risk)")
    print(f"      F1-Score / Accuracy : {matrix.f1_score:.4f}")
    print(dim(f"      Assessment          : {matrix.business_impact_summary}"))

    print(bold("\n  [2] Detection Latency Percentiles"))
    print(dim(f"      samples             : {lat.sample_count}"))
    print(f"      p50 (Median)        : {lat.p50_ms} ms")
    print(f"      p95 Percentile      : {lat.p95_ms} ms")
    print(f"      p99 Percentile      : {lat.p99_ms} ms")
    print(f"      Status              : {warn('Degraded (>500ms)') if lat.is_checkout_degraded else ok('Optimal')}")

    print(bold("\n  [3] Forensic Audit Trail Index"))
    if audit:
        print(f"      Completeness        : {audit.completeness_percentage}% ({audit.fields_present}/{audit.total_fields_required} fields)")
        print(f"      Compliance Grade    : {ok(audit.compliance_grade)}")
        if audit.missing_critical_fields:
            print(dim(f"      Missing             : {', '.join(audit.missing_critical_fields)}"))
    else:
        print(dim("      skipped — no --audit-log supplied"))
    print("─" * 56)
    return 0

def cmd_selftest(a: argparse.Namespace) -> int:
    for c in COUNTRIES:
        fz = make_fullz(c)
        assert fz["country"] == c
        assert fz["name"] and fz["city"]
    print(f"selftest ok: identities ({', '.join(COUNTRIES)})")

    # Throwaway DB: a self-test must not consume PANs in the user's dedupe store,
    # or running it repeatedly would shrink the space real generation can use.
    with tempfile.TemporaryDirectory() as td:
        scratch = CardStorage(Path(td) / "selftest.db", migrate_legacy=False)
        sample = generate_random("414720", "12", "29", 20, card_storage=scratch)
    assert len(sample) == 20
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
    p_id.add_argument("--card", action="store_true", help="Include a geo-coherent card BIN in output")

    # fp
    p_fp = sub.add_parser("fp", help="Generate browser fingerprint profile")
    p_fp.add_argument("--json", action="store_true")

    # bin
    p_bin = sub.add_parser("bin", help="Generate Luhn test cards")
    p_bin.add_argument("--country", default=None, help="Auto-pick a geo-coherent BIN for this country")
    p_bin.add_argument("--bin", default=None, help="Explicit BIN/PAN prefix (default: geo-coherent for country, or 414720)")
    p_bin.add_argument("--allow-unknown-bin", action="store_true",
                       help="Generate for a prefix absent from the issuer DB (issuer metadata will be unknown)")
    p_bin.add_argument("-n", "--count", type=int, default=5)
    p_bin.add_argument("-m", "--month", default="12")
    p_bin.add_argument("-y", "--year", default="30")
    p_bin.add_argument("-f", "--format", choices=["pipe", "csv", "json"], default="pipe")
    p_bin.add_argument("--seed", type=int, default=None)
    p_bin.add_argument("--json", action="store_true")

    # issuer
    p_issuer = sub.add_parser("issuer", help="List and look up BIN/issuer metadata")
    issuer_sub = p_issuer.add_subparsers(dest="subcommand", required=True)
    p_il = issuer_sub.add_parser("list", help="List BINs/issuers, filtered")
    p_il.add_argument("--network", help="Filter by card network (substring)")
    p_il.add_argument("--country", help="Filter by issuing country (ISO code)")
    p_il.add_argument("--issuer", help="Filter by issuer name (substring)")
    p_il.add_argument("--json", action="store_true")
    p_iu = issuer_sub.add_parser("lookup", help="Look up a BIN or PAN prefix")
    p_iu.add_argument("query", help="BIN or PAN to resolve (e.g. 414720)")
    p_iu.add_argument("--json", action="store_true")
    p_id = issuer_sub.add_parser("default", help="Show the default BIN for a country")
    p_id.add_argument("country", help="ISO country code (e.g. US)")
    p_id.add_argument("--json", action="store_true")

    # doctor
    p_doc = sub.add_parser("doctor", help="Run system diagnostics")
    p_doc.add_argument("--json", action="store_true")

    # selftest
    sub.add_parser("selftest", help="Run offline unit checks")

    # run
    p_run = sub.add_parser("run", help="Interactive workflow wizard")
    p_run.add_argument("-c", "--country", choices=COUNTRIES, default=None)
    p_run.add_argument("-t", "--target", default=None)
    p_run.add_argument("--auth", default=None, help="Authorization / Bearer token")
    p_run.add_argument("--method", choices=["GET", "POST"], default=None, help="HTTP method for target probe")
    p_run.add_argument("-o", "--output", default=None, help="Path to save audit report JSON")
    p_run.add_argument("--asn-type", choices=["residential", "datacenter", "hosting", "vpn", "unknown"],
                       default="unknown", help="Classification of the exit ASN (default: unknown)")

    # audit
    p_audit = sub.add_parser("audit", help="Audit transaction telemetry against fraud scoring heuristics")
    p_audit.add_argument("-c", "--country", choices=COUNTRIES, default="US")
    p_audit.add_argument("--bin", default=None,
                         help="Explicit BIN/PAN prefix (default: geo-coherent for country)")
    p_audit.add_argument("--allow-unknown-bin", action="store_true",
                         help="Proceed with a prefix absent from the issuer DB")
    p_audit.add_argument("--egress-country", default=None,
                         help="Country your traffic actually exits from (omitted = undetermined)")
    p_audit.add_argument("--asn-type", choices=["residential", "datacenter", "hosting", "vpn", "unknown"],
                         default="unknown", help="Classification of the exit ASN (default: unknown)")
    p_audit.add_argument("--json", action="store_true")

    # decline
    p_dec = sub.add_parser("decline", help="Analyze gateway/issuer decline code and ISO 8583 mapping")
    p_dec.add_argument("code", help="Decline code (e.g. authentication_required, insufficient_funds, stolen_card)")
    p_dec.add_argument("--json", action="store_true")
    # funnel
    p_funnel = sub.add_parser("funnel", help="Simulate transaction traversal across 4 defensive layers")
    p_funnel.add_argument("-c", "--country", choices=COUNTRIES, default="US")
    p_funnel.add_argument("--bin", default=None,
                          help="Explicit BIN/PAN prefix (default: geo-coherent for country)")
    p_funnel.add_argument("--allow-unknown-bin", action="store_true",
                          help="Proceed with a prefix absent from the issuer DB")
    p_funnel.add_argument("--egress-country", default=None,
                          help="Country your traffic actually exits from (omitted = undetermined)")
    p_funnel.add_argument("--asn-type", choices=["residential", "datacenter", "hosting", "vpn", "unknown"],
                          default="unknown", help="Classification of the exit ASN (default: unknown)")
    p_funnel.add_argument("--idempotency", action="store_true", help="Include Idempotency-Key header")
    p_funnel.add_argument("--json", action="store_true")

    # currency
    p_curr = sub.add_parser("currency", help="Audit currency conversion, zero-decimal, and fractional precision")
    p_curr.add_argument("--currency", default="USD")
    p_curr.add_argument("--amount", type=float, default=10.00)
    p_curr.add_argument("--edge-cases", action="store_true", help="Run common rounding edge cases")
    p_curr.add_argument("--json", action="store_true")

    # maturity
    p_mat = sub.add_parser(
        "maturity",
        help="Score a defence run from measured counts and latencies",
        description="Computes FPR/FNR, latency percentiles and audit-trail completeness "
                    "from data you supply. It has no built-in numbers.",
    )
    p_mat.add_argument("--tp", type=int, required=True, help="True positives (malicious challenged)")
    p_mat.add_argument("--tn", type=int, required=True, help="True negatives (legitimate allowed)")
    p_mat.add_argument("--fp", type=int, required=True, help="False positives (legitimate challenged)")
    p_mat.add_argument("--fn", type=int, required=True, help="False negatives (malicious allowed)")
    p_mat.add_argument("--latencies", required=True, type=_parse_latencies,
                       help="Comma-separated decision latencies in ms, e.g. 15.2,22.4,45.1")
    p_mat.add_argument("--audit-log", default=None,
                       help="Path to a JSON event log to grade for forensic completeness")
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
        elif args.cmd == "issuer":
            return cmd_issuer(args)
        elif args.cmd == "doctor":
            return run_doctor(json_output=args.json)
        elif args.cmd == "selftest":
            return cmd_selftest(args)
        elif args.cmd == "run":
            return cmd_run(args)
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
