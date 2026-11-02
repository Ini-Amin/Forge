"""forge.tests.test_issuer - CLI issuer commands and geo-coherent card pairing."""
import io
import json
import subprocess
import sys

import argparse
import pytest

from forge.cards.bins import BIN_DB, COUNTRY_DEFAULT_BIN, get_default_bin_for_country, issuer_lookup
from forge.identity import make_fullz


def test_get_default_bin_for_country():
    """Each supported country maps to its default BIN."""
    for c in COUNTRY_DEFAULT_BIN:
        assert get_default_bin_for_country(c) == COUNTRY_DEFAULT_BIN[c]
    assert get_default_bin_for_country("XX") == "414720"  # fallback


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
    assert any(r["bin"] == "521114" for r in rows)  # BCA


def test_cmd_issuer_lookup():
    """forge issuer lookup resolves by longest prefix."""
    from forge.cli.main import cmd_issuer
    a = argparse.Namespace(subcommand="lookup", query="521114", json=True)
    out = io.StringIO()
    sys.stdout = out
    try:
        assert cmd_issuer(a) == 0
        meta = json.loads(out.getvalue())
    finally:
        sys.stdout = sys.__stdout__
    assert meta["issuer"] == "Bank Central Asia"
    assert meta["network"] == "Mastercard"


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
    assert "Banco do Brasil" in text
    assert "400403" in text


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
    assert meta["bin"] == "400403"
    assert meta["issuer"] == "Banco do Brasil"


def test_cmd_bin_geo_coherent_default():
    """forge bin --country picks the country's default BIN, not the first DB row."""
    from forge.cli.main import cmd_bin
    from forge.cards.storage import storage
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


def test_cmd_bin_no_country_still_defaults_to_us():
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
    assert "HSBC UK" in r.stdout


def test_subprocess_issuer_lookup():
    r = subprocess.run([sys.executable, "forge.py", "issuer", "lookup", "521114"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "Bank Central Asia" in r.stdout


def test_subprocess_bin_country():
    r = subprocess.run([sys.executable, "forge.py", "bin", "--country", "BR",
                        "--count", "3"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "400403" in r.stdout


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
    assert meta["bin"] == "400403"
    assert meta["issuer"] == "Banco do Brasil"


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

