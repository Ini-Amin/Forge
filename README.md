# 🛠️ Forge

**Forge** is a cross-platform toolkit engineered for **Backend Developers**, **Security Defenders / Fraud Analysts**, and **QA Engineers** working on identity systems, checkout flows, and payment gateway integrations.

It generates geo-coherent synthetic identities, validates ISO/IEC 7812 Luhn fixtures, orchestrates browser-grade TLS ClientHello profiles, and provides strict fail-closed transport for integration testing.

---

## 🎯 The Triad: Who Uses Forge?

```
                      ┌───────────────────────────┐
                      │           FORGE           │
                      └─────────────┬─────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
  💻 BACKEND DEVS             🛡️ DEFENDERS                🧪 QA TESTERS
  • Database Seeding         • Fraud Rule Tuning        • CI/CD Pipelines
  • AVS/Address Parsing      • Geo-Mismatch Audits      • Zero-PII Test Data
  • Idempotency Testing      • Rate-Limiter Stress      • Gateway Validation
```

### 1. 💻 For Backend Engineers
* **Zero-PII Database Seeding:** Populate development and staging databases with culturally coherent names, localized addresses, valid postal codes, and format-accurate national IDs (SSN, NIK, My Number, CPF, Steuer-ID) without risking real user PII or GDPR/compliance violations.
* **Format & Checksum Parsing:** Validate input sanitization, ISO/IEC 7812 Luhn algorithms, and Address Verification Service (AVS) logic using deterministic seeded fixtures (`--seed`).
* **Contract & Load Testing:** Generate thousands of unique test payloads in JSON/NDJSON format to benchmark microservices and checkout APIs.

### 2. 🛡️ For Defenders & Fraud Analysts
* **Fraud Scoring & Rule Benchmarking:** Test how your fraud detection engine (e.g., Stripe Radar, Sift, custom rulesets) handles intentional geographic discrepancies (e.g., US billing address submitted from an Asian residential exit).
* **Fingerprint Consistency Testing:** Audit your telemetry collectors against realistic Chrome, Firefox, and Safari TLS handshakes and matching `User-Agent` / `sec-ch-ua` headers.

### 3. 🧪 For QA & Test Engineers
* **Staging & Production Gateway Integration:** Test payment endpoints end-to-end without hardcoded third-party targets.
* **Deterministic Test Automation:** Reproducible data generation using seeds ensures tests are repeatable in CI/CD environments.
* **Composability:** Every command supports `--json` for native piping with Unix tools like `jq`, `curl`, and test runners.

---

## 📦 Architecture & Key Features

* **Cross-Platform by Design:** Runs natively on **Linux**, **macOS**, and **Windows** with platform-standard config paths (XDG on Linux, `%APPDATA%` on Windows, `Application Support` on macOS).
* **Strict Fail-Closed Egress:** Built-in safeguards prevent accidental direct IP leaks. If a configured proxy is unreachable or untrusted, network probes abort immediately (`EgressSecurityError`).
* **SQLite WAL Persistence:** Replaces fragile flat files with an ACID-compliant, thread-safe SQLite database running in WAL (Write-Ahead Logging) mode for instant $O(1)$ deduplication.
* **Modern Packaging:** Standard PEP 621 (`pyproject.toml`) for clean editable installation via `pip install -e .`.

---

## ⚡ Installation

Forge requires Python 3.10+ and `curl_cffi`:

```bash
git clone https://github.com/Ini-Amin/Forge.git
cd Forge

# Install as editable package
pip install -e .
```

Verify your environment with the built-in diagnostic tool:

```bash
forge doctor
```

---

## 💻 CLI Quickstart

### 1. Synthetic Identity Generation (`forge id`)
Generate realistic, geo-coherent synthetic identities matching real regional formats.
Add `--card` to attach a matching card BIN (issuer + currency) so identity and card are
geo-coherent out of the box.

```bash
# Formatted terminal display
forge id --country US
forge id --country JP
forge id --country ID
forge id --country CA   # SIN (Luhn)
forge id --country FR   # INSEE/NIR (mod-97)
forge id --country SE   # personnummer (Luhn)

# JSON output for automated scripting
forge id --country US --json

# Identity + geo-coherent card BIN/issuer/currency
forge id --country BR --card
forge id --country BR --card --json

# Deterministic generation using a seed
forge id --country US --seed 42 --json
```

Every national ID is generated to its real format and carries a verifiable
checksum: US SSN, ID NIK, JP My Number, BR CPF, DE steuer-ID, UK NINO plus CA
SIN, FR NIR, IT Codice Fiscale, ES NIE, AU TFN, SG NRIC, NL BSN, and SE
personnummer. `tests/test_identity.py` re-implements each national check
independently, so a generator that drifts from the algorithm fails the suite.

### 2. Browser Fingerprint Profiles (`forge fp`)
Inspect browser TLS ClientHello configurations and matched HTTP headers:

```bash
forge fp
forge fp --json
```

### 3. BIN / Issuer Lookups (`forge issuer`)
Query the BIN database: list issuers, filter by country/network/issuer, and resolve a BIN
or PAN prefix to its issuer, currency, and card length.

The database ships 30+ source-verified issuer prefixes across 14 countries.
Every record carries a `source` field naming the reference it was checked
against — `binlist` (binlist.net data repo, CC-BY 4.0) or `test-panel`
(publicly documented test-card ranges). `forge doctor` runs an integrity
validator over the whole table: it rejects placeholder issuers, countries that
aren't ISO alpha-2, network labels that contradict the IIN range, and prefixes
that cannot form a Luhn-valid PAN. A prefix with no verified issuer is not
shipped at all.

```bash
# List all issuers
forge issuer list

# Filter by country
forge issuer list --country ID
forge issuer list --country US --json

# Filter by network and issuer name (substring)
forge issuer list --network Mastercard --issuer central

# Resolve a BIN or full PAN to issuer metadata
forge issuer lookup 455632
forge issuer lookup 4147201111111111
forge issuer lookup 378282 --json

# Show the default BIN for a country
forge issuer default BR
```

`forge issuer lookup` reports `bin_known`. When a prefix is absent from the
database it still resolves the network from IIN ranges (`4` is Visa whoever
issues it) but leaves issuer, country and currency empty — it does not guess.

### 4. Luhn ISO/IEC 7812 Card Fixtures (`forge bin`)
Generate Luhn-compliant test card fixtures for QA and validator testing. `--country`
auto-picks a geo-coherent BIN for that country (Mandiri for ID, Itau Unibanco for BR,
NatWest for GB, RBC for CA, BNP Paribas for FR, ...) so identities and cards match
without manual BIN lookup. A default BIN exists only where the identity pipeline can
generate a coherent buyer for that country — all 14 shipped countries have one; BIN
data for CH and MX is queryable via `forge issuer list --country CH` but there is no
identity profile, so `--country CH` refuses rather than attach a European card to a
Swiss identity.

Generation is fail-closed. A country with no BIN on file and a prefix absent from the
issuer database are both errors rather than silent fallbacks, because a fixture
carrying another country's issuer is a wrong answer that looks correct.

```bash
# Generate 5 test fixtures for JPMorgan Chase Visa BIN (414720) in pipe format (PAN|MM|YY|CVV)
forge bin --bin 414720 --count 5 --format pipe

# Generate structured JSON fixtures
forge bin --bin 517805 --count 10 --json

# Auto-pick geo-coherent BIN by country
forge bin --country ID --count 5
forge bin --country BR --count 5 --json

# Override the auto-picked BIN explicitly
forge bin --country ID --bin 455632 --count 3  # BCA Visa instead of Mandiri

# Unlisted prefix: refused, because country and currency would be fiction.
# Pass --allow-unknown-bin to generate anyway; network is still inferred from IIN ranges.
forge bin --bin 412290 --count 1 --allow-unknown-bin --json
```

### 5. System Diagnostics & Self-Test (`forge doctor` & `forge selftest`)
```bash
# Run environment health checks
forge doctor

# Run offline cryptographic & identity self-tests
forge selftest
```

---

## 🛡️ Defensive Simulation & Staging Audit Suite

Forge equips defenders, fraud engineers, and backend architects to audit their transaction funnel and stress-test defenses **before** going live to production.

### 1. 4-Layer Transaction Funnel Simulator (`forge funnel`)
Simulate and trace a transaction through the entire defensive pipeline:
```
[Client / Bot]
   ├── 1. Edge / WAF        (IP reputation, ASN type, TLS ClientHello consistency)
   ├── 2. Merchant Backend  (Schema completeness, Idempotency-Key enforcement)
   ├── 3. Gateway / Radar   (AVS match, Geo-IP to billing country alignment)
   └── 4. Card Issuer / 3DS (EMVCo 3DS decision: Frictionless vs Challenge SCA)
```

```bash
# Simulate funnel traversal for US transaction fixture
forge funnel --country US

# State where your traffic actually exits; omitted = undetermined, scored as such
forge funnel --country BR --egress-country BR
forge funnel --country JP --egress-country US --asn-type datacenter

# Include Idempotency-Key header to test backend validation
forge funnel --country US --idempotency

# JSON export for CI/CD staging verification
forge funnel --country JP --json
```

`audit` and `funnel` never fetch a proxy on their own, and they never claim an
egress you did not supply. No `--egress-country` means the geo check is scored
`Egress country undetermined`, and an omitted `--asn-type` reads `unknown`
rather than a clean residential line. Supply the values you actually measured.

Latency is reported only when it was measured: `forge funnel` and the offline
legs of `forge run` print `not measured`, because there is no live request to
time. Only a live probe (`forge run --target ...`) produces a latency figure,
and it can time just the edge request — backend, gateway and issuer stay
`not measured`.

A passing funnel reports `AUTHORIZED`, not `SETTLED`: approval is an
authorization-time decision, not fund movement. `AUTHORIZED` transactions
carry a three-stage `money_lifecycle` — authorization → clearing → settlement
— with verdicts derived only from card funding type, never from invented
rates, amounts, or dates: credit settles `DEFERRED` (funds move after the
capture window), debit and prepaid `PASS` (same-day batch / balance deducted
at capture). `forge funnel --json` adds `money_lifecycle` (per-stage
verdicts) and `rails_state` (`authorized`, `action_required`, `failed`,
`unknown`).

### 2. Forge Lifecycle Simulator (`forge lifecycle`)
Event-driven per-track simulator for what happens *after* the authorization
decision: capture, clearing, settlement. Mock-only, offline, and never inferred
— success on one track never advances another; every state change comes from an
explicit event in your file, applied in file order. Unlike `forge funnel` (a
snapshot at auth time), this simulates the post-auth pipeline.

```bash
# Simulate a run from an explicit event file ({"events": [...]})
forge lifecycle --events events.json --json

# Diff two event files by event_id (input fields only; never mutates state)
forge reconcile --internal internal.json --external external.json --json
```

The $1 mock rule: the base amount is always `$1.00` USD (`amount_units: 100`).
Any other base amount is rejected with the reason in the audit trail. With
`--country` (default `US`; `US/JP/DE/GB/ID`), the $1 converts through an
explicit fixture rate table in `forge/lifecycle/rates.py` — never a runtime-
invented FX rate, and the converted values below are fixture units, not live
quotes: USD $1.00 → 100 minor units; JPY ¥150 → 150 units (zero-decimal);
EUR €0.92 → 92; GBP £0.79 → 79; IDR Rp15,500.00 → 1,550,000 (two-decimal per
ISO 4217). A file must not mix currencies; all events in a run share the run's
target currency.

Active tracks (Phase 1), each advancing independently:
Authorization (`PENDING → AUTHORIZED | DECLINED`),
Capture (`CAPTURED`),
Clearing (`CLEARING_PENDING → CLEARED | CLEARING_FAILED`),
Settlement (`SETTLEMENT_PENDING → SETTLED | SETTLEMENT_FAILED`).
Guards cross-check tracks (e.g. `settlement.accepted` requires Clearing
`CLEARED`); an invalid transition is recorded `rejected` with an auditable
reason and other tracks are untouched. Absent optional-track events mean no
events for that track — never a fabricated transition.

`SETTLED` is terminal only within the Settlement track — it is not a global
"transaction finished" flag. `CLEARING_FAILED` / `SETTLEMENT_FAILED` mean
handling is needed, not that "the transaction failed".

Phase 2 tracks (Reversal, Dispute, Refund) are vocabulary-only in Phase 1:
their state names are declared, but their events are rejected as
`track <name> inactive in phase 1` — not `unknown`. Nothing about a dispute,
refund, or reversal is simulated yet.

`forge reconcile` (Phase 1) compares two event files by `event_id` and diffs
input fields only (`type`, `occurred_at`, `amount_units`, `currency`), reporting
`match` / `mismatch` / `missing_external` / `unexpected_external`. It never
writes to lifecycle event history and is not blocked by absent optional events.

### 3. Currency Truncation & Precision Auditor (`forge currency`)
Audit currency conversions against ISO 4217 zero-decimal (JPY, KRW, VND), three-decimal (KWD, BHD), and fractional cent rounding hazards:

```bash
# Audit zero-decimal conversion (e.g. JPY smallest unit is 1, not 100)
forge currency --currency JPY --amount 1500

# Audit rounding edge cases ($10.555 fractional cent hazards)
forge currency --currency USD --edge-cases
```

### 4. Defense Maturity Scorecard (`forge maturity`)
Scores a defence run from numbers you measured. The command has no built-in
figures — without `--tp/--tn/--fp/--fn` and `--latencies` it does nothing, so the
scorecard can never be mistaken for a demo.
* **Precision Tradeoffs:** False Positive Rate (FPR) vs. False Negative Rate (FNR).
* **Latency Percentiles:** p50, p95, and p99 checkout latency impact.
* **Forensic Audit Trail Index:** Verifies presence of mandatory forensic fields (JA4 hash, AVS, ISO 8583 response code) in a real event log you point it at.

```bash
# Counts from your last evaluation run, latencies in milliseconds
forge maturity --tp 95 --tn 980 --fp 20 --fn 5 \
               --latencies 15.2,22.4,45.1,88,112.5

# Grade an actual event log for forensic completeness
forge maturity --tp 95 --tn 980 --fp 20 --fn 5 \
               --latencies 15.2,22.4,45.1 --audit-log audit/event.json --json
```

---

## 🚀 Integration Testing (Staging & Production)

`forge` is completely **target-agnostic**. It contains **zero hardcoded endpoints**. You supply your own application or gateway endpoint at runtime.

### How to Set or Change Your Target URL (Beginner & Vibe Coder Friendly)

You do **not** need to modify the Python code to test your own app or checkout endpoint. Here are the 3 easiest ways:

#### Option 1: Just Run `forge` and Paste It (Interactive / Zero-Setup)
Simply run `forge` in your terminal. The interactive wizard will ask you directly:
```text
  1. Target Region (US/GB/JP/ID/DE/BR/CA/FR/IT/ES/AU/SG/NL/SE) [US]: US
  2. Target Endpoint URL (Enter = offline staging audit): https://your-website.com/api/checkout
```
👉 Just paste your local dev server (e.g., `http://localhost:3000/api/checkout`) or staging link and press Enter.

#### Option 2: Pass It as a Flag (One-Liner)
If you want to run it instantly in one command:
```bash
# For local apps (Next.js, FastAPI, Express, Laravel):
forge --target "http://localhost:3000/api/checkout"

# For live staging / cloud servers:
forge --target "https://staging.yourstore.com/checkout"
```

#### Option 3: Set an Environment Variable (For Projects & .env)
If you are running automated test scripts or using a `.env` file:
```bash
# On Linux / macOS:
export FORGE_TARGET_URL="http://localhost:3000/api/checkout"
forge

# On Windows (PowerShell):
$env:FORGE_TARGET_URL="http://localhost:3000/api/checkout"
forge
```

> 💡 **Where is it located in the code?**  
> If you want to customize the internal code directly, the target resolver lives in **`forge/cli/main.py`** inside the `cmd_run` function. It automatically checks `a.target` first, then `os.environ.get("FORGE_TARGET_URL")`, and falls back to prompting you interactively.
---

## 🔒 Security & Privacy Notice

All identities, card numbers, addresses, and national ID formats produced by **Forge** are purely **synthetic algorithmic fixtures**. They are intended solely for authorized development, QA testing, database seeding, and defensive security auditing.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
