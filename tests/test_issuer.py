"""forge.tests.test_issuer - CLI issuer commands and geo-coherent card pairing."""
import io
import json
import subprocess
import sys

import argparse
import pytest

from forge.cards.bins import BIN_DB, COUNTRY_DEFAULT_BIN, get_default_bin_for_country, issuer_lookup
from forge.identity import make_fullz


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    """Point the CLI at a throwaway DB.

    The suite used to write into the real ~/.local/share/forge database, and
    seeded generation is deterministic, so after enough runs every candidate PAN
    for a seed was already recorded and generation returned nothing. Tests must
    not share state with the user's data, or with each other.
    """
    from forge.cards.storage import CardStorage
    import importlib
    cli = importlib.import_module("forge.cli.main")  # package __init__ shadows the submodule name
    store = CardStorage(tmp_path / "cards.db", migrate_legacy=False)
    monkeypatch.setattr(cli, "storage", store)
    return store


def test_get_default_bin_for_country():
    """Each supported country maps to its default BIN; anything else is None.

    Returning a US BIN for an unknown country was how `forge bin --country FR`
    silently produced a Chase/USD card: coherent-looking, wrong country.
    """
    for c in COUNTRY_DEFAULT_BIN:
        assert get_default_bin_for_country(c) == COUNTRY_DEFAULT_BIN[c]
    assert get_default_bin_for_country("XX") is None


def test_cmd_issuer_list_all(monkeypatch):
    """forge issuer list prints all 23 issuers."""
    from forge.cli.main import cmd_issuer
    a = argparse.Namespace(subcommand="list", network=None, country=None, issuer=None, json=False)
    out = io.StringIO()
    sys.stdout = out
    try:
        assert cmd_issuer(a) == 0
        text = out.getvalue()
    finally:
        sys.stdout = sys.__stdout__
    assert "forge issuer —" in text
    assert "Chase" in text and "Bank Mandiri" in text


def test_cmd_issuer_list_filtered():
    """forge issuer list --country filters correctly."""
    from forge.cli.main import cmd_issuer
    a = argparse.Namespace(subcommand="list", network=None, country="ID", issuer=None, json=True)
    out = io.StringIO()
    sys.stdout = out
    try:
        assert cmd_issuer(a) == 0
        rows = json.loads(out.getvalue())
    finally:
        sys.stdout = sys.__stdout__
    assert len(rows) == 2
    for r in rows:
        assert r["country"] == "ID"
    assert any(r["bin"] == "461700" for r in rows)  # Mandiri
    assert any(r["bin"] == "455632" for r in rows)  # BCA


def test_cmd_issuer_lookup():
    """forge issuer lookup resolves by longest prefix."""
    from forge.cli.main import cmd_issuer
    a = argparse.Namespace(subcommand="lookup", query="455632", json=True)
    out = io.StringIO()
    sys.stdout = out
    try:
        assert cmd_issuer(a) == 0
        meta = json.loads(out.getvalue())
    finally:
        sys.stdout = sys.__stdout__
    assert meta["issuer"] == "Bank Central Asia"
    assert meta["network"] == "Visa"


def test_cmd_issuer_lookup_unknown():
    from forge.cli.main import cmd_issuer
    a = argparse.Namespace(subcommand="lookup", query="999999", json=False)
    out = io.StringIO()
    sys.stdout = out
    try:
        assert cmd_issuer(a) == 1
    finally:
        sys.stdout = sys.__stdout__


def test_cmd_issuer_default():
    from forge.cli.main import cmd_issuer
    a = argparse.Namespace(subcommand="default", country="BR", json=False)
    out = io.StringIO()
    sys.stdout = out
    try:
        assert cmd_issuer(a) == 0
    finally:
        sys.stdout = sys.__stdout__
    text = out.getvalue()
    assert "Itau Unibanco" in text
    assert "544828" in text


def test_cmd_issuer_default_json():
    from forge.cli.main import cmd_issuer
    a = argparse.Namespace(subcommand="default", country="BR", json=True)
    out = io.StringIO()
    sys.stdout = out
    try:
        assert cmd_issuer(a) == 0
        meta = json.loads(out.getvalue())
    finally:
        sys.stdout = sys.__stdout__
    assert meta["bin"] == "544828"
    assert meta["issuer"] == "Itau Unibanco"


def test_cmd_bin_geo_coherent_default(isolated_storage):
    """forge bin --country picks the country's default BIN, not the first DB row."""
    from forge.cli.main import cmd_bin
    for idx, (country, expected_bin) in enumerate(COUNTRY_DEFAULT_BIN.items()):
        seed = 100 + idx
        a = argparse.Namespace(country=country, bin=None, count=1, month="12",
                               year="30", format="pipe", seed=seed, json=True)
        out = io.StringIO()
        sys.stdout = out
        try:
            assert cmd_bin(a) == 0
            cards = json.loads(out.getvalue())
        finally:
            sys.stdout = sys.__stdout__
        assert cards, f"no cards for {country}"
        assert cards[0]["pan"].startswith(expected_bin), (country, cards[0]["pan"], expected_bin)


def test_cmd_bin_no_country_still_defaults_to_us(isolated_storage):
    from forge.cli.main import cmd_bin
    a = argparse.Namespace(country=None, bin=None, count=1, month="12",
                           year="30", format="pipe", seed=200, json=True)
    out = io.StringIO()
    sys.stdout = out
    try:
        assert cmd_bin(a) == 0
        cards = json.loads(out.getvalue())
    finally:
        sys.stdout = sys.__stdout__
    assert cards[0]["pan"].startswith("414720")


def test_id_card_pairing():
    """forge id --card attaches a geo-coherent card BIN to the identity."""
    from forge.cli.main import cmd_id
    for country in ["US", "ID", "JP", "BR", "DE", "GB"]:
        a = argparse.Namespace(country=country, seed=7, json=True, card=True)
        out = io.StringIO()
        sys.stdout = out
        try:
            assert cmd_id(a) == 0
            fz = json.loads(out.getvalue())
        finally:
            sys.stdout = sys.__stdout__
        assert fz["card_bin"] == get_default_bin_for_country(country)
        assert fz["name"]  # identity still generated


def test_subprocess_issuer_list():
    """End-to-end via the CLI entrypoint."""
    r = subprocess.run([sys.executable, "forge.py", "issuer", "list"],
                       capture_output=True, text=True, cwd=".")
    assert r.returncode == 0, r.stderr
    assert "Chase" in r.stdout
    assert "Navy Federal" in r.stdout
    assert "NatWest" in r.stdout


def test_subprocess_issuer_lookup():
    r = subprocess.run([sys.executable, "forge.py", "issuer", "lookup", "455632"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "Bank Central Asia" in r.stdout


def test_subprocess_bin_country():
    r = subprocess.run([sys.executable, "forge.py", "bin", "--country", "BR",
                        "--count", "3"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "544828" in r.stdout


def test_subprocess_issuer_default_plain():
    """Regression: `issuer default` must work through the real parser, not just a
    hand-built Namespace. It previously crashed with AttributeError because the
    subparser never registered --json while cmd_issuer read a.json unconditionally."""
    r = subprocess.run([sys.executable, "forge.py", "issuer", "default", "ID"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Bank Mandiri" in r.stdout


def test_subprocess_issuer_default_json():
    r = subprocess.run([sys.executable, "forge.py", "issuer", "default", "BR", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    meta = json.loads(r.stdout)
    assert meta["bin"] == "544828"
    assert meta["issuer"] == "Itau Unibanco"


def test_public_test_pans_are_not_issuers():
    """424242 / 411111 are publicly documented test PANs (Stripe, generic Visa).

    No issuer owns them, so a lookup table that answers with a country and a
    currency for those prefixes is describing a card that cannot exist. Forge
    only ships prefixes that resolve to a real issuer.
    """
    for pan in ("4242424242424242", "4111111111111111", "424242", "411111"):
        meta = issuer_lookup(pan)
        assert meta["bin"] == "Unknown", pan
        assert meta["issuer"] == "Unknown", pan
    assert "424242" not in BIN_DB
    assert "411111" not in BIN_DB


def test_bin_db_passes_validator():
    """Every BIN must be structurally sound and carry provenance.

    A prefix that cannot (a) form a Luhn-valid PAN, (b) state a real issuer
    rather than a placeholder, or (c) cite where its claim came from is a
    fabrication waiting to happen — the validator refuses it.
    """
    from forge.cards.bins import validate_bin_db
    assert validate_bin_db() == []


def test_bin_db_validator_rejects_fabricated_entry(monkeypatch):
    from forge.cards.bins import BIN_DB, validate_bin_db
    monkeypatch.setitem(BIN_DB, "111111", {
        "network": "Visa", "issuer": "Test Bank", "country": "US",
        "currency": "USD", "pan_length": 16, "bin_length": 6,
        "funding": "credit", "is_prepaid": False, "source": "",
    })
    errs = validate_bin_db()
    assert any("BIN 111111" in e and "placeholder" in e for e in errs)
    assert any("source" in e for e in errs)


def test_bin_db_validator_rejects_network_contradiction(monkeypatch):
    """A 'Visa' label on a Mastercard IIN range is a misattribution, not data."""
    from forge.cards.bins import BIN_DB, validate_bin_db
    monkeypatch.setitem(BIN_DB, "523456", {
        "network": "Visa", "issuer": "Some Bank", "country": "US",
        "currency": "USD", "pan_length": 16, "bin_length": 6,
        "funding": "credit", "is_prepaid": False, "source": "binlist",
    })
    errs = validate_bin_db()
    assert any("BIN 523456" in e and "contradicts IIN" in e for e in errs)


def test_bin_db_grows_beyond_fifteen_issuers():
    """The expansion goal: more real, source-verified issuers than the old 15."""
    assert len(BIN_DB) >= 30
    assert len(COUNTRY_DEFAULT_BIN) >= 10
    assert any(m["country"] == "CA" for m in BIN_DB.values())
    assert any(m["country"] == "SG" for m in BIN_DB.values())


def test_bin_db_failed_attribution_fixed():
    """400022 was shipped as 'HSBC UK prepaid'; binlist says Navy Federal US.
    A card that looks British but is issued in the US is a lie that AVS
    scoring would trust. It must now resolve to the verified issuer."""
    meta = issuer_lookup("400022")
    assert meta["issuer"] == "Navy Federal Credit Union"
    assert meta["country"] == "US"
    assert meta["currency"] == "USD"


def test_no_mock_harness_command():
    """`forge test-mock` was a stub that typed a fixture at a localhost port.

    It was removed: the tool reports on real systems, so it does not carry a
    command whose only job is talking to a fake one.
    """
    from forge.cli.main import build_parser
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert "test-mock" not in sub.choices


def test_maturity_requires_measured_input():
    """`forge maturity` must refuse to invent a scorecard."""
    r = subprocess.run([sys.executable, "forge.py", "maturity"],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "--tp" in r.stderr


def test_maturity_scores_supplied_counts():
    r = subprocess.run([sys.executable, "forge.py", "maturity",
                        "--tp", "95", "--tn", "980", "--fp", "20", "--fn", "5",
                        "--latencies", "15.2,22.4,45.1,88,112.5", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    cm = data["confusion_matrix"]
    assert cm["true_positives"] == 95
    assert cm["false_positives"] == 20
    # FPR = fp / (tn + fp) = 20 / 1000
    assert abs(cm["false_positive_rate"] - 0.02) < 1e-9
    assert data["latency_percentiles"]["sample_count"] == 5
    assert data["audit_trail_completeness"] is None


def test_unknown_country_is_refused():
    """No silent US substitution: a country with no BIN at all is an error, not a guess."""
    r = subprocess.run([sys.executable, "forge.py", "bin", "--country", "VE"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "No BIN on file for VE" in r.stdout
    assert "414720" not in r.stdout


def test_bin_country_with_data_but_no_identity_points_to_explicit_flag():
    """CH/MX have verified BINs but no identity profile; `--country CH` must not
    silently re-point elsewhere — it tells you to use --bin explicitly."""
    r = subprocess.run([sys.executable, "forge.py", "bin", "--country", "CH"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "No default BIN for CH" in r.stdout
    assert "--bin explicitly" in r.stdout


def test_unknown_bin_is_refused_by_default():
    r = subprocess.run([sys.executable, "forge.py", "bin", "--bin", "412290", "--count", "1"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "not in the issuer database" in r.stdout


def test_unknown_bin_generates_only_with_explicit_flag():
    """--allow-unknown-bin is the escape hatch, and it keeps the metadata honest."""
    r = subprocess.run([sys.executable, "forge.py", "bin", "--bin", "412290",
                        "--count", "1", "--allow-unknown-bin", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    card = json.loads(r.stdout)[0]
    assert card["issuer"] == "Unknown"
    assert card["network"] == "Visa"  # IIN range is still real information
    assert card["pan"].startswith("412290")


def test_infer_network_uses_real_iin_ranges():
    from forge.cards.bins import infer_network
    assert infer_network("4122906140104798") == "Visa"
    assert infer_network("378282246310005") == "American Express"
    assert infer_network("6011000990139424") == "Discover"
    assert infer_network("5555555555554444") == "Mastercard"
    assert infer_network("2221000000000009") == "Mastercard"
    assert infer_network("3566002020360505") == "JCB"
    assert infer_network("3056930009020004") == "Diners Club"
    assert infer_network("9999000000000000") is None
    assert infer_network("abcd") is None


def test_unknown_bin_reports_what_it_does_not_know():
    meta = issuer_lookup("4122906140104798")
    assert meta["bin_known"] is False
    assert meta["network"] == "Visa"
    assert meta["issuer"] == "Unknown"
    assert meta["country"] == "??"
    assert meta["currency"] == "?"


def test_lookup_partial_prefix_succeeds_with_unknowns():
    """An unlisted prefix still answers with its IIN range, so it is not a failure.

    Exit 1 is reserved for input that says nothing at all in either direction.
    """
    r = subprocess.run([sys.executable, "forge.py", "issuer", "lookup",
                        "4122906140104798", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    meta = json.loads(r.stdout)
    assert meta["bin_known"] is False
    assert meta["network"] == "Visa"
    assert meta["country"] == "??"


def test_lookup_unparseable_prefix_fails():
    r = subprocess.run([sys.executable, "forge.py", "issuer", "lookup", "999999"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "Unknown" in r.stdout


def test_selftest_does_not_write_to_user_database():
    """`forge selftest` generated 20 real PANs into the shared dedupe store on
    every run, permanently consuming candidates that seeded generation needs."""
    from forge.cards.storage import storage
    before = storage.total_count()
    r = subprocess.run([sys.executable, "forge.py", "selftest"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "20/20 valid" in r.stdout
    assert storage.total_count() == before


def test_audit_and_funnel_refuse_unknown_bin():
    """The fail-closed rule was only in `bin`; audit and funnel took anything."""
    for cmd in ("audit", "funnel"):
        r = subprocess.run([sys.executable, "forge.py", cmd, "--bin", "412290"],
                           capture_output=True, text=True)
        assert r.returncode == 1, cmd
        assert "not in the issuer database" in r.stdout, cmd


def test_audit_uses_country_default_bin():
    r = subprocess.run([sys.executable, "forge.py", "audit", "--country", "BR", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    avs = json.loads(r.stdout)["components"]["avs"]
    assert avs["passed"] is True


def test_audit_honours_explicit_bin_over_country_default():
    """`--bin 414720` with `--country BR` used to be swallowed by a sentinel
    comparison, so the mismatch it should report could never be produced."""
    r = subprocess.run([sys.executable, "forge.py", "audit",
                        "--country", "BR", "--bin", "414720", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    avs = json.loads(r.stdout)["components"]["avs"]
    assert avs["passed"] is False
    assert avs["avs_code"] == "N"
    assert any("Card issued in US" in reason for reason in avs["reasons"])


def test_audit_does_not_invent_egress_country():
    """With no proxy and no --egress-country, egress must read as undetermined.

    It used to default to the billing country, so every offline audit reported
    a coherent geo check that had never been performed.
    """
    r = subprocess.run([sys.executable, "forge.py", "audit", "--country", "BR", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    geo = json.loads(r.stdout)["components"]["geo_egress"]
    assert geo["egress_country"] == ""
    assert geo["coherent"] is False
    assert any("undetermined" in reason for reason in geo["reasons"])


def test_audit_scores_stated_egress():
    r = subprocess.run([sys.executable, "forge.py", "audit", "--country", "BR",
                        "--egress-country", "US", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    geo = json.loads(r.stdout)["components"]["geo_egress"]
    assert geo["egress_country"] == "US"
    assert geo["risk_penalty"] == 40


def test_funnel_flags_unclassified_asn():
    """An unknown exit ASN is not a clean residential line."""
    r = subprocess.run([sys.executable, "forge.py", "funnel", "--country", "BR", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    layer1 = json.loads(r.stdout)["layers"][0]
    assert layer1["verdict"] == "FLAG"
    assert any("unclassified" in d.lower() for d in layer1["details"])


def test_funnel_offline_reports_no_latency():
    """Offline, no layer latency may be printed. The funnel used to fabricate
    per-layer defaults (15/45/120/210ms); a number with no probe behind it is
    a claim, so every layer must read not-measured instead."""
    r = subprocess.run([sys.executable, "forge.py", "funnel", "--country", "US", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["total_latency_ms"] is None
    assert all(l["latency_ms"] is None for l in data["layers"])


def test_funnel_probe_measures_edge_latency_only():
    """The single live probe can time the edge request and nothing deeper, so
    the edge verdict takes the measured value and the rest stay None."""
    from forge.defenders.funnel import TransactionFunnelSimulator
    res = TransactionFunnelSimulator.evaluate(
        {}, {"country": "US", "name": "A", "address": "B", "zip": "1"},
        {"country": "US"}, {"country": "US", "asn_type": "residential"},
        {"impersonate": "chrome", "ua": "Chrome/120"},
        probe={"status_code": 200, "latency_ms": 42.5},
    )
    assert res.layers[0].latency_ms == 42.5
    assert all(l.latency_ms is None for l in res.layers[1:])
    assert res.total_latency_ms == 42.5


def test_funnel_cli_lifecycle_json():
    """cmd_funnel JSON exposes the money trace; a US credit card must not
    claim settlement at approval (offline, no proxy: hermetic).

    `--idempotency` is required to reach the AUTHORIZED branch: offline the
    missing Idempotency-Key adds 25 risk, pushing the total to 35 and into
    3DS SCA (CHALLENGE_3DS), where settlement is N/A and no money trace exists.
    """
    r = subprocess.run([sys.executable, "forge.py", "funnel", "--country", "US",
                        "--idempotency", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["final_disposition"] == "AUTHORIZED"
    assert "money_lifecycle" in data
    assert len(data["money_lifecycle"]) == 3
    assert [s["stage"] for s in data["money_lifecycle"]] == ["authorization", "clearing", "settlement"]
    assert data["money_lifecycle"][2]["verdict"] == "DEFERRED"
    assert data["rails_state"] == "authorized"


def test_running_the_suite_offline_is_fast():
    """audit/funnel used to call a third-party VPN API with a 12s timeout."""
    import time as _time
    start = _time.monotonic()
    subprocess.run([sys.executable, "forge.py", "audit", "--country", "US"],
                   capture_output=True, text=True)
    assert _time.monotonic() - start < 5.0



HAPPY_FILE = {"events": [
    {"event_id": "e1", "type": "auth.accepted", "occurred_at": "2026-11-03T10:00:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e2", "type": "capture.accepted", "occurred_at": "2026-11-03T10:01:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e3", "type": "clearing.submitted", "occurred_at": "2026-11-03T10:02:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e4", "type": "clearing.accepted", "occurred_at": "2026-11-03T10:03:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e5", "type": "settlement.submitted", "occurred_at": "2026-11-03T10:04:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e6", "type": "settlement.accepted", "occurred_at": "2026-11-03T10:05:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
]}


def test_lifecycle_cli_json(tmp_path):
    """forge lifecycle --events happy.json --json is hermetic and machine-readable."""
    f = tmp_path / "happy.json"
    f.write_text(json.dumps(HAPPY_FILE))
    r = subprocess.run([sys.executable, "forge.py", "lifecycle", "--events", str(f), "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["tracks"]["settlement"] == "SETTLED"
    assert data["aggregate"]["summary"] == "settled"
    assert len(data["audit"]) == 6
    assert all(x["result"] == "applied" for x in data["audit"])


def test_lifecycle_cli_jpy_conversion(tmp_path):
    """$1 in US converts to ¥150 when the run targets JP; only $1 accepted."""
    f = tmp_path / "happy_jpy.json"
    evs = [{**e, "currency": "JPY", "amount_units": 150} for e in HAPPY_FILE["events"]]
    f.write_text(json.dumps({"events": evs}))
    r = subprocess.run([sys.executable, "forge.py", "lifecycle", "--events", str(f), "--country", "JP", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["tracks"]["settlement"] == "SETTLED"
    assert data["currency"] == "JPY"
    assert data["expected_units"] == 150


def test_lifecycle_cli_bad_amount_rejected(tmp_path):
    f = tmp_path / "bad.json"
    evs = [dict(HAPPY_FILE["events"][0]), {**HAPPY_FILE["events"][1], "amount_units": 200}]
    f.write_text(json.dumps({"events": evs}))
    r = subprocess.run([sys.executable, "forge.py", "lifecycle", "--events", str(f), "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["audit"][1]["result"] == "rejected"
    assert "only $1.00" in data["audit"][1]["reason"]


def test_lifecycle_json_round_trips_into_reconcile_internal(tmp_path):
    """`forge lifecycle --json` emits an event-list export usable as --internal:
    its `events` key feeds straight into `forge reconcile --internal`."""
    f = tmp_path / "happy.json"
    out_f = tmp_path / "out.json"
    f.write_text(json.dumps(HAPPY_FILE))
    r = subprocess.run([sys.executable, "forge.py", "lifecycle", "--events", str(f), "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out_f.write_text(r.stdout)
    r2 = subprocess.run([sys.executable, "forge.py", "reconcile",
                         "--internal", str(out_f), "--external", str(f), "--json"],
                        capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    data = json.loads(r2.stdout)
    assert data["counts"]["match"] == 6
    assert data["mismatches"] == 0
    assert data["missing_external"] == 0
    assert data["unexpected_external"] == 0
    assert all(row["diffs"] == [] for row in data["rows"])


def test_reconcile_cli(tmp_path):
    int_f = tmp_path / "internal.json"
    ext_f = tmp_path / "external.json"
    int_f.write_text(json.dumps({"events": HAPPY_FILE["events"]}))
    ext_f.write_text(json.dumps({"events": HAPPY_FILE["events"]}))
    r = subprocess.run([sys.executable, "forge.py", "reconcile",
                        "--internal", str(int_f), "--external", str(ext_f), "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["counts"]["match"] == 6
