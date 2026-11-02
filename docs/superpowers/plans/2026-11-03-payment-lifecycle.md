# Payment Lifecycle (A: money trace, C: rail states) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop presenting approval as settlement (`SETTLED` → `AUTHORIZED`), trace the money lifecycle after a funnel decision, and extend the payment state machine with card-rails states wired to the decline taxonomy.

**Architecture:** Phase A adds a deterministic `money_lifecycle` trace (authorization → clearing → settlement) to `FunnelSimulationResult`, derived only from card `funding` (credit/debit/prepaid). Phase C adds `rails_state` (rail vocabulary) to the funnel result via `PaymentStateMachine`, mapping funnel dispositions and decline categories into `authorized|captured|cleared|settled|action_required|failed`. CLI (`cmd_funnel`, `cmd_run` audit artifact) prints and emits both.

**Tech Stack:** Python 3.10+, dataclasses, stdlib only. unittest/pytest suite.

**Spec:** `docs/superpowers/specs/2026-11-03-payment-lifecycle-design.md`

## Global Constraints

- No invented rates, no money amounts, no date arithmetic anywhere in the lifecycle logic. Verdicts come only from `funding` and the disposition itself.
- Verdict vocabulary is exactly `PASS` / `DEFERRED` / `BLOCK` / `N_A`.
- Rail-state snapshot of an approved funnel is always `authorized` — capture/clearing/settlement happen after the snapshot and are never claimed as reached.
- Tests are mock-only: no real endpoints, no network, no proxy. Suite stays hermetic.
- `card_meta` may omit `funding` (existing tests do); unknown funding → settlement verdict `N_A`, never a fabricated timing claim.

## Review Focus

1. `card_meta` without `funding`: lifecycle must not crash or invent a timing claim → settlement `N_A`, task 1.
2. `stop_on_block` early returns: each must carry `money_lifecycle` and `rails_state` consistent with its disposition → tasks 1 and 3.
3. `funnel.py` importing `forge.payments.state_machine`: must not create a circular import (`forge/payments/*` does not import `forge.defenders`) → task 3.
4. CLI JSON is additive-only: existing keys keep their meaning; new keys (`money_lifecycle`, `rails_state`) appear in both `cmd_funnel --json` and the `cmd_run` audit artifact → tasks 2 and 4.
5. `FunnelSimulationResult` gains fields with defaults; all four construction sites build with keywords, so appending fields at dataclass end is safe → tasks 1 and 3.

---
### Task 1: Money lifecycle trace in the funnel

**Files:**
- Modify: `forge/defenders/funnel.py` (dataclasses block ~24-31; `evaluate` returns ~116-123, 167-174, 209-216, 239-246)
- Test: `tests/test_defenders_advanced.py`

**Interfaces:**
- Consumes: `card_meta` dict keys `funding` (`card_meta.get("funding", "unknown")`, values credit/debit/prepaid/other).
- Produces:
  - `StageVerdict(stage: str, verdict: str, detail: str)` dataclass.
  - `FunnelSimulationResult.money_lifecycle: list[StageVerdict]` (default `field(default_factory=list)`).
  - Terminal disposition renames `SETTLED` → `AUTHORIZED`.

- [ ] **Step 1: Write the failing tests**

Modify `tests/test_defenders_advanced.py`:

```python
# in test_funnel_simulator_clean (card_meta has NO funding key):
        self.assertEqual(res.final_disposition, "AUTHORIZED")
        self.assertEqual(len(res.money_lifecycle), 3)
        stages = [s["stage"] if isinstance(s, dict) else s.stage for s in res.money_lifecycle]
        self.assertEqual(stages, ["authorization", "clearing", "settlement"])
        # funding unknown -> settlement truthfully unclaimed
        self.assertEqual(res.money_lifecycle[2].verdict, "N_A")

    def test_funnel_lifecycle_credit_settlement_deferred(self):
        card = {"country": "US", "issuer": "Chase", "funding": "credit"}
        res = self._run_clean_funnel(card_meta=card)
        self.assertEqual(res.final_disposition, "AUTHORIZED")
        self.assertEqual(res.money_lifecycle[2].verdict, "DEFERRED")
        self.assertIn("not settled", res.money_lifecycle[2].detail)

    def test_funnel_lifecycle_prepaid_settlement_passes(self):
        card = {"country": "US", "issuer": "Chase", "funding": "prepaid"}
        res = self._run_clean_funnel(card_meta=card)
        self.assertEqual(res.money_lifecycle[2].verdict, "PASS")

    def test_funnel_lifecycle_rejected_never_reaches_clearing(self):
        # datacenter ASN (35 pts) + UA/TLS mismatch (50 pts) forces L1 BLOCK
        headers = {"User-Agent": "Mozilla/5.0 ... Firefox/135.0"}
        tls = {"impersonate": "chrome136", "ua": "Mozilla/5.0 ... Chrome/136.0.0.0 Safari/537.36"}
        res = TransactionFunnelSimulator.evaluate(
            headers, {"country": "US", "name": "John Doe", "address": "a", "zip": "10001"},
            {"country": "US", "funding": "credit"}, {"country": "US", "asn_type": "datacenter"}, tls)
        self.assertEqual(res.final_disposition, "REJECTED_BY_WAF")
        self.assertEqual(res.money_lifecycle[1].verdict, "N_A")
        self.assertIn("Never reached", res.money_lifecycle[1].detail)
```

Add a private helper on the test class that runs a clean funnel (headers/identity/egress identical to `test_funnel_simulator_clean`) with an overridable `card_meta`:

```python
    def _run_clean_funnel(self, card_meta):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
                   "Idempotency-Key": "test_uuid_123"}
        identity = {"country": "US", "name": "John Doe", "address": "123 Main St", "zip": "10001"}
        egress = {"country": "US", "asn_type": "residential"}
        tls = {"impersonate": "firefox135",
               "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"}
        return TransactionFunnelSimulator.evaluate(headers, identity, card_meta, egress, tls)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_defenders_advanced.py -q`
Expected: FAIL — `AttributeError: 'FunnelSimulationResult' object has no attribute 'money_lifecycle'` (and the `SETTLED` assertion fails).

- [ ] **Step 3: Implement `StageVerdict`, rename, and `_build_money_lifecycle` in `forge/defenders/funnel.py`**

Add the dataclass and the field with `field(default_factory=list)`. Add a module-level function:

```python
def _build_money_lifecycle(final_disposition: str, funding: str) -> list[StageVerdict]:
```

Rules (exact):
- If `final_disposition == "AUTHORIZED"`:
  - authorization → `PASS`, detail "Approved at issuer layer (risk gate passed) — authorization only, no funds moved"
  - clearing → `PASS`, detail "Routable for clearing batch submission"
  - settlement → by `funding.lower()`:
    - `"credit"` → `DEFERRED`, "Credit line — funds move after the capture window; not settled at approval"
    - `"debit"` → `PASS`, "Debit card — settles in the same-day batch"
    - `"prepaid"` → `PASS`, "Prepaid — balance deducted at capture"
    - anything else → `N_A`, "Funding type unknown — settlement timing not claimed"
- Else:
  - authorization → `BLOCK` if disposition startswith `REJECTED_BY_`, else `N_A`; detail = the disposition
  - clearing and settlement → `N_A`, `f"Never reached — {final_disposition}"`

Rename the final disposition assignment at the pass-through branch (`line ~230`: `disposition = "SETTLED"` → `disposition = "AUTHORIZED"`). Pass `money_lifecycle=_build_money_lifecycle(<this return's disposition>, card_meta.get("funding", "unknown"))` in all four `FunnelSimulationResult(...)` construction sites.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_defenders_advanced.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest -q`
Expected: 80 passed, 1 new XFAIL none — only `test_funnel_simulator_clean`'s renamed expectation and the 4 new lifecycle tests change; every other file green.

```bash
git add forge/defenders/funnel.py tests/test_defenders_advanced.py
git commit -m "feat(funnel): trace money lifecycle after approval; SETTLED -> AUTHORIZED
```

---
### Task 2: CLI surface for the money trace

**Files:**
- Modify: `forge/cli/main.py` (badge ~379-381; `cmd_funnel` text block ~499-511 and JSON ~487-497; `cmd_run` audit artifact ~396-413)
- Test: `tests/test_issuer.py`

**Interfaces:**
- Consumes: `funnel.money_lifecycle` (list of `StageVerdict`) from Task 1.
- Produces: `--json` payloads for `cmd_funnel` and the `cmd_run` audit artifact each contain `"money_lifecycle": [stage.__dict__ ...]`; terminal badge renders `AUTHORIZED` amber, not green.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_issuer.py`:

```python
def test_funnel_cli_lifecycle_json():
    """cmd_funnel JSON exposes the money trace; a US credit card must not
    claim settlement at approval (offline, no proxy: hermetic)."""
    r = subprocess.run([sys.executable, "forge.py", "funnel", "--country", "US", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["final_disposition"] == "AUTHORIZED"
    assert "money_lifecycle" in data
    assert len(data["money_lifecycle"]) == 3
    assert [s["stage"] for s in data["money_lifecycle"]] == ["authorization", "clearing", "settlement"]
    assert data["money_lifecycle"][2]["verdict"] == "DEFERRED"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_issuer.py::test_funnel_cli_lifecycle_json -q`
Expected: FAIL — `"money_lifecycle"` not in the JSON payload.

- [ ] **Step 3: Wire `money_lifecycle` into `forge/cli/main.py`**

- Badge (~379): `ok(...)` applies only when the disposition used to be green; `AUTHORIZED` now renders `warn(...)` (amber), `CHALLENGE_3DS` stays `warn`, `REJECTED_*` stays `bad`.
- `cmd_funnel` JSON: add `"money_lifecycle": [s.__dict__ for s in res.money_lifecycle]`.
- `cmd_funnel` text: after the per-layer loop, print a `Money Lifecycle:` block, one dim line per stage: `  authorization : PASS — <detail>`.
- `cmd_run` audit artifact: under the `"funnel"` dict add `"money_lifecycle": [l.__dict__ for l in funnel.money_lifecycle]`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_issuer.py::test_funnel_cli_lifecycle_json -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest -q`
Expected: 81 passed.

```bash
git add forge/cli/main.py tests/test_issuer.py
git commit -m "feat(funnel): surface money lifecycle in funnel CLI output and audit JSON"
```

---
### Task 3: Card-rails states in the state machine + funnel

**Files:**
- Modify: `forge/payments/state_machine.py`; `forge/defenders/funnel.py`
- Test: `tests/test_payments.py`, `tests/test_defenders_advanced.py`

**Interfaces:**
- Consumes: `DeclineAnalysis` (from `forge.payments.decline_codes`) category constants `CAT_HARD`, `CAT_SOFT`, `CAT_SCA`, `CAT_CONFIG`.
- Produces:
  - `PaymentStateMachine.RAIL_STATES: tuple = ("authorized", "captured", "cleared", "settled", "action_required", "failed")`
  - `PaymentStateMachine.rails_state(final_disposition: str, funding: str = "") -> str`
  - `PaymentStateMachine.state_for_decline(analysis: DeclineAnalysis) -> str`
  - `FunnelSimulationResult.rails_state: str` (default `"unknown"`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_payments.py`:

```python
    def test_rails_state_mapping(self):
        sm = PaymentStateMachine
        self.assertEqual(sm.rails_state("AUTHORIZED", "credit"), "authorized")
        self.assertEqual(sm.rails_state("AUTHORIZED", "prepaid"), "authorized")  # snapshot, never beyond
        self.assertEqual(sm.rails_state("CHALLENGE_3DS"), "action_required")
        self.assertEqual(sm.rails_state("REJECTED_BY_GATEWAY"), "failed")

    def test_rails_state_from_decline(self):
        sm = PaymentStateMachine
        from forge.payments.decline_codes import DeclineCodeTaxonomy as DCT
        self.assertEqual(sm.state_for_decline(DCT.analyze("stolen_card")), "failed")
        self.assertEqual(sm.state_for_decline(DCT.analyze("authentication_required")), "action_required")
        self.assertEqual(sm.state_for_decline(DCT.analyze("insufficient_funds")), "failed")
```

Add to `tests/test_defenders_advanced.py`, inside the new lifecycle tests' helper area:

```python
    def test_funnel_clean_rails_state(self):
        res = self._run_clean_funnel({"country": "US", "issuer": "Chase", "funding": "credit"})
        self.assertEqual(res.rails_state, "authorized")

    def test_funnel_blocked_rails_state(self):
        # Same fixture as test_funnel_lifecycle_rejected_never_reaches_clearing:
        # datacenter ASN + UA/TLS mismatch force an L1 BLOCK.
        headers = {"User-Agent": "Mozilla/5.0 ... Firefox/135.0"}
        tls = {"impersonate": "chrome136", "ua": "Mozilla/5.0 ... Chrome/136.0.0.0 Safari/537.36"}
        res = TransactionFunnelSimulator.evaluate(
            headers, {"country": "US", "name": "John Doe", "address": "a", "zip": "10001"},
            {"country": "US", "funding": "credit"}, {"country": "US", "asn_type": "datacenter"}, tls)
        self.assertEqual(res.rails_state, "failed")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_payments.py tests/test_defenders_advanced.py -q`
Expected: FAIL — `AttributeError: ... rails_state` and `'PaymentStateMachine' object has no attribute 'rails_state'`.

- [ ] **Step 3: Implement the rail-state mapping in `forge/payments/state_machine.py`**

```python
    RAIL_STATES = ("authorized", "captured", "cleared", "settled", "action_required", "failed")

    @classmethod
    def rails_state(cls, final_disposition: str, funding: str = "") -> str:
        # Exact precedence:
        #   "AUTHORIZED"              -> "authorized"  (snapshot; funding is NOT consulted)
        #   "CHALLENGE_3DS"           -> "action_required"
        #   startswith("REJECTED_BY_")-> "failed"
        #   anything else             -> "unknown"
        ...
```

The `rails_state` body follows that precedence table exactly. `funding` is part of the signature because the funnel will call with it, but it must not change the result — an approved card is `authorized` regardless of funding, since capture/clearing/settlement happen after the snapshot and are never claimed as reached.

`state_for_decline` reads the category off the `DeclineAnalysis`:

| `analysis.category` | return |
|---|---|
| `CAT_HARD` | `"failed"` |
| `CAT_SOFT` | `"failed"` |
| `CAT_SCA` | `"action_required"` |
| `CAT_CONFIG` or any other | `"failed"` |

Use the constants `DeclineCodeTaxonomy.CAT_HARD`, `CAT_SOFT`, `CAT_SCA`, `CAT_CONFIG`; import `DeclineCodeTaxonomy` from `forge.payments.decline_codes` at the top of `state_machine.py`. No other rail states exist — the snapshot never propagates a card past `authorized`.

- [ ] **Step 4: Add `rails_state` to the funnel**

In `forge/defenders/funnel.py` add `rails_state: str = "unknown"` after `money_lifecycle`. Import `PaymentStateMachine` at top (`from forge.payments.state_machine import PaymentStateMachine`; verify no circular import — `forge/payments` imports no `forge.defenders`). In each of the four `FunnelSimulationResult(...)` sites add `rails_state=PaymentStateMachine.rails_state(<that disposition>, card_meta.get("funding", "unknown"))`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_payments.py tests/test_defenders_advanced.py -q`
Expected: PASS.

- [ ] **Step 6: Full suite + commit**

Run: `python3 -m pytest -q`
Expected: 86 passed.

```bash
git add forge/payments/state_machine.py forge/defenders/funnel.py tests/test_payments.py tests/test_defenders_advanced.py
git commit -m "feat(payments): card-rails rail states wired to funnel disposition and decline taxonomy"
```

---
### Task 4: CLI surface for rail state

**Files:**
- Modify: `forge/cli/main.py` (`cmd_funnel` text ~499-511 and JSON ~487-497; `cmd_run` audit artifact ~396-413)
- Test: `tests/test_issuer.py`

**Interfaces:**
- Consumes: `res.rails_state` from Task 3.
- Produces: `"rails_state"` key in `cmd_funnel --json` and the `cmd_run` audit `"funnel"` dict; `Rail State:` line in `cmd_funnel` text.

- [ ] **Step 1: Extend the CLI test (make it fail)**

Edit `test_funnel_cli_lifecycle_json` in `tests/test_issuer.py` to add:

```python
    assert data["rails_state"] == "authorized"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_issuer.py::test_funnel_cli_lifecycle_json -q`
Expected: FAIL — `KeyError: 'rails_state'`.

- [ ] **Step 3: Wire `rails_state` into `forge/cli/main.py`**

- `cmd_funnel` JSON: add `"rails_state": res.rails_state`.
- `cmd_funnel` text: print `  Rail State       : authorized` (dim value) above the Money Lifecycle block.
- `cmd_run` audit artifact: add `"rails_state": funnel.rails_state` to the `"funnel"` dict.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_issuer.py::test_funnel_cli_lifecycle_json -q`
Expected: PASS.

- [ ] **Step 5: Full suite twice + commit**

Run: `python3 -m pytest -q` twice; both runs the same count (87). Confirms hermeticity — the CLI tests never touch the network.

```bash
git add forge/cli/main.py tests/test_issuer.py
git commit -m "feat(funnel): report card-rails rail state in CLI and audit output"
```

---
### Task 5: Docs + final gate

**Files:**
- Modify: `README.md`; `docs/superpowers/specs/2026-11-03-payment-lifecycle-design.md` (strike through completed-phase framing if needed)

- [ ] **Step 1: Update README**

- Under the funnel section (~~`Final Disposition`~~): state explicitly that a passing funnel reports `AUTHORIZED`, that approval is not settlement, and reference the money lifecycle (auth → clear → settle; credit DEFERRED, debit/prepaid PASS).
- One line on `forge funnel --json` now including `money_lifecycle` and `rails_state`.

- [ ] **Step 2: Final verification**

Run: `python3 forge.py selftest` (offline) and `python3 -m pytest -q` once more. No `forge doctor`, no `run --target`, no binlist/proxy calls — mocks only, per constraint.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-11-03-payment-lifecycle-design.md
git commit -m "docs: document authorization vs settlement and the money lifecycle"
```