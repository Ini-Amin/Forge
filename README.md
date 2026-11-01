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
* **WAF & Rate Limiting Verification:** Verify whether your bot management (Cloudflare, DataDome, Akamai) and API rate-limiters (Token Bucket / Leaky Bucket) trigger correctly under realistic browser TLS ClientHello signatures.
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
Generate realistic, geo-coherent synthetic identities matching real regional formats:

```bash
# Formatted terminal display
forge id --country US
forge id --country JP
forge id --country ID

# JSON output for automated scripting
forge id --country US --json

# Deterministic generation using a seed
forge id --country US --seed 42 --json
```

### 2. Browser Fingerprint Profiles (`forge fp`)
Inspect browser TLS ClientHello configurations and matched HTTP headers:

```bash
forge fp
forge fp --json
```

### 3. Luhn ISO/IEC 7812 Card Fixtures (`forge bin`)
Generate Luhn-compliant test card fixtures for QA and validator testing:

```bash
# Generate 5 test fixtures for Chase Visa BIN (414720) in pipe format (PAN|MM|YY|CVV)
forge bin --bin 414720 --count 5 --format pipe

# Generate structured JSON fixtures
forge bin --bin 517805 --count 10 --json
```

### 4. System Diagnostics & Self-Test (`forge doctor` & `forge selftest`)
```bash
# Run environment health checks
forge doctor

# Run offline cryptographic & identity self-tests
forge selftest
```

---

## 🚀 Integration Testing (Staging & Production)

`forge` is completely **target-agnostic**. It contains **zero hardcoded endpoints**. You supply your own application or gateway endpoint at runtime.

### Dynamic Endpoint Supply

```bash
# Option 1: Supply target via CLI flag
forge run --target "https://staging.yourdomain.com/api/v1/checkout"

# Option 2: Set target via environment variable
export FORGE_TARGET_URL="https://staging.yourdomain.com/api/v1/checkout"
forge run
```

### Testing Local Mock Services (e.g., `stripe-mock`)

For offline local development against mock containers:

```bash
# Default targets http://127.0.0.1:12111
forge test-mock

# Or specify your custom local server port
forge test-mock --url "http://127.0.0.1:8000/api/health"
```

---

## 🔒 Security & Privacy Notice

All identities, card numbers, addresses, and national ID formats produced by **Forge** are purely **synthetic algorithmic fixtures**. They are intended solely for authorized development, QA testing, database seeding, and defensive security auditing.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
