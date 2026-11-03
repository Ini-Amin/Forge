# Forge Lifecycle (event-driven per-track state machine + reconciliation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `forge lifecycle` (explicit event-driven per-track lifecycle simulator, mock-only) and `forge reconcile` (Phase 1 reconciliation), driven ONLY by supplied mock events, with auditable rejection of invalid transitions.

**Architecture:** A new `forge/lifecycle/` package with three layers — immutable per-track event history (source of truth), per-track current states, and a derived aggregate. Each track owns states/events/edges; cross-track guards validate eligibility. Amounts are `(currency, minor_units)`; the mock validator rejects anything that is not exactly $1.00 in the event's currency per an explicit fixture rate table. Reconciliation compares two event files by `event_id` and never mutates lifecycle state.

**Tech Stack:** Python 3.10+, dataclasses, stdlib only (json, argparse, unittest/pytest). Reuses `forge.defenders.currency.CurrencyPrecisionAuditor` for minor-unit conversion.

**Spec:** `docs/superpowers/specs/2026-11-03-forge-lifecycle-design.md`

## Global Constraints

- Verdict vocabulary for event results is exactly: `applied` / `rejected` / `duplicate`.
- No inference: success of prior states NEVER advances the lifecycle; absence of optional-track events = empty list for that track, never a fabricated transition, never marks the transaction failed/incomplete.
- Track state vocabulary (shared, declared now): Authorization `PENDING, AUTHORIZED, DECLINED`; Capture `CAPTURED, PARTIALLY_CAPTURED`; Clearing `CLEARING_PENDING, CLEARED, CLEARING_FAILED`; Settlement `SETTLEMENT_PENDING, SETTLED, SETTLEMENT_FAILED`; Reversal `REVERSED, VOIDED`; Dispute `DISPUTED, CHARGEBACK_RECEIVED, CHARGEBACK_WON, CHARGEBACK_LOST`; Refund `REFUND_PENDING, PARTIALLY_REFUNDED, REFUNDED`.
- Phase 1 ACTIVE tracks: authorization, capture, clearing, settlement. Reversal/Dispute/Refund are vocabulary-only — every event targeting them is rejected as inactive (NOT "unknown event type").
- `SETTLED` is terminal ONLY within the Settlement track — never a global "transaction finished" flag.
- `CLEARING_FAILED` / `SETTLEMENT_FAILED` are track-terminal but NOT transaction failure — the aggregate reports them as `needs_handling`, never as failed.
- Mock-only: no real endpoints, no network, no proxy. Verification is `pytest`/`selftest` only.
- Deterministic and replayable: processing is in FILE ORDER (`occurred_at` is provenance, never drives ordering); running the same file twice yields identical results.
- Amount rule: base is `$1.00 USD = 100` minor units. Every event's `(currency, amount_units)` must equal exactly $1.00 converted to that currency via the explicit rate table. Unknown currency or wrong amount → `rejected` with reason. A file must not mix currencies.

## Review Focus

1. An event arriving out of logical order (e.g. `capture.accepted` before `auth.accepted`): must be `rejected` with a guard/state reason, never silently applied, and must not corrupt other tracks — task 2.
2. An event with `amount_units != $1.00` in its currency (e.g. `{currency: "JPY", amount_units: 200}`): `rejected` with the mock $1-rule reason — task 2.
3. A Phase-2 track event (e.g. `refund.accepted`, `chargeback.received`): `rejected` as inactive, with a reason that distinguishes it from an unknown event type — task 2.
4. A duplicate `event_id` in one file: `duplicate` result, no state change, no guard re-evaluation, replay-identical — task 2.
5. Reconcile input fields only (`type`, `occurred_at`, `amount_units`, `currency`): engine metadata (`result`, `reason`, `source`) is never diffed, and reconcile never writes lifecycle history — task 4.
6. `SETTLED` does not end the story: after settlement, the aggregate must still report track states and a `needs_handling` state is not reported as `failed` — task 3.

---

### Task 1: Track definitions, transitions, guards, and the rate table

**Files:**
- Create: `forge/lifecycle/__init__.py`, `forge/lifecycle/state.py`, `forge/lifecycle/rates.py`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Consumes: `forge.defenders.currency.CurrencyPrecisionAuditor.audit_amount_to_units(currency, amount) -> CurrencyPrecisionCheck` (field `expected_integer_units`).
- Produces (exact, used by Task 2-5):
  - `forge.lifecycle.state.ACTIVE_TRACKS: tuple = ("authorization", "capture", "clearing", "settlement")`
  - `forge.lifecycle.state.TRANSITIONS: tuple[Transition, ...]` where
    `Transition(event_type: str, track: str, from_state: str | None, to_state: str, guard: str | None)`
    (dataclass, frozen). Exact transitions:
    - `auth.accepted` auth PENDING→AUTHORIZED
    - `auth.declined` auth PENDING→DECLINED
    - `capture.accepted` capture None→CAPTURED, guard `eligible_auth`
    - `clearing.submitted` clearing None→CLEARING_PENDING, guard `clearing_eligible`
    - `clearing.accepted` clearing CLEARING_PENDING→CLEARED
    - `clearing.failed` clearing CLEARING_PENDING→CLEARING_FAILED
    - `settlement.submitted` settlement None→SETTLEMENT_PENDING, guard `settlement_eligible`
    - `settlement.accepted` settlement SETTLEMENT_PENDING→SETTLED
    - `settlement.failed` settlement SETTLEMENT_PENDING→SETTLEMENT_FAILED
  - `forge.lifecycle.state.INITIAL_STATES: dict[str, str | None]` = `{"authorization": "PENDING", "capture": None, "clearing": None, "settlement": None}`
  - `forge.lifecycle.state.INACTIVE_EVENT_TYPES: dict[str, str]` — phase-2 vocabulary events mapped to their track, so the engine can reject them as "inactive" rather than "unknown". Exact: `{"refund.accepted": "refund", "refund.partial": "refund", "refund.full": "refund", "chargeback.received": "dispute", "chargeback.won": "dispute", "chargeback.lost": "dispute", "reversal.submitted": "reversal", "void.submitted": "reversal"}`. These are vocabulary declarations only — no transitions, never applied.
  - `forge.lifecycle.state.find_transition(event_type: str) -> Transition | None`
  - `forge.lifecycle.state.evaluate_guard(guard: str, tracks: dict[str, str | None], remaining_units: int) -> tuple[bool, str]`
    returning `(ok, reason)`, where `remaining_units` = run's expected $1 minor units minus the sum of applied capture amounts (computed by the engine). Guards: `eligible_auth` (auth == AUTHORIZED and `remaining_units > 0`, reason includes "eligible authorization" or "remaining must be positive"); `clearing_eligible` (capture == CAPTURED); `settlement_eligible` (clearing == CLEARED).
  - `forge.lifecycle.rates.COUNTRY_CURRENCY: dict[str, str]` = `{"US": "USD", "JP": "JPY", "DE": "EUR", "GB": "GBP", "ID": "IDR"}`
  - `forge.lifecycle.rates.RATES: dict[str, str]` = `{"USD": "1.00", "JPY": "150.00", "EUR": "0.92", "GBP": "0.79", "IDR": "15500.00"}` (amount of currency per $1.00)
  - `forge.lifecycle.rates.converted_units(currency: str) -> int`: minor units of $1.00 in `currency`, via `RATES` × `CurrencyPrecisionAuditor.audit_amount_to_units`. USD → 100, JPY → 150, EUR → 92, GBP → 79, IDR → 1550000 (IDR is two-decimal per ISO 4217 — the existing auditor's behavior is correct and must not be bent). Unknown currency raises `ValueError`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_lifecycle.py`:

```python
class TestRates(unittest.TestCase):
    def test_converted_units_known_currencies(self):
        from forge.lifecycle.rates import converted_units
        self.assertEqual(converted_units("USD"), 100)
        self.assertEqual(converted_units("JPY"), 150)   # zero-decimal: 150 yen, not 15000
        self.assertEqual(converted_units("EUR"), 92)
        self.assertEqual(converted_units("GBP"), 79)
        self.assertEqual(converted_units("IDR"), 1550000)  # two-decimal per ISO 4217 — see ruling Q1

    def test_converted_units_unknown_currency_raises(self):
        from forge.lifecycle.rates import converted_units
        with self.assertRaises(ValueError):
            converted_units("XXX")


class TestTransitions(unittest.TestCase):
    def test_find_transition_known_and_unknown(self):
        from forge.lifecycle.state import find_transition
        t = find_transition("capture.accepted")
        self.assertEqual(t.track, "capture")
        self.assertEqual(t.to_state, "CAPTURED")
        self.assertIsNone(find_transition("refund.accepted"))  # phase-2 vocab has no transition

    def test_guard_eligible_auth(self):
        from forge.lifecycle.state import evaluate_guard
        ok, reason = evaluate_guard("eligible_auth", {"authorization": "AUTHORIZED"}, 100)
        self.assertTrue(ok)
        ok, reason = evaluate_guard("eligible_auth", {"authorization": "AUTHORIZED"}, 0)
        self.assertFalse(ok)
        self.assertIn("remaining", reason)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: FAIL — `ModuleNotFoundError: forge.lifecycle` / missing attributes.

- [ ] **Step 3: Implement `forge/lifecycle/rates.py`, `forge/lifecycle/state.py`, `forge/lifecycle/__init__.py`**

`rates.py`: the two dicts verbatim + `converted_units` using `RATES` and `CurrencyPrecisionAuditor.audit_amount_to_units(currency, amount).expected_integer_units`. The auditor handles ISO 4217 (JPY zero-decimal, IDR two-decimal) — do not special-case either; do not modify the auditor's currency sets.
`state.py`: `Transition` frozen dataclass, the `TRANSITIONS` tuple verbatim, `find_transition`, `evaluate_guard`.
`__init__.py`: export the public names above.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest -q` — expected 87 + 5 = 92 passed (existing suite untouched).
```bash
git add forge/lifecycle/ tests/test_lifecycle.py
git commit -m "feat(lifecycle): track definitions, transitions, guards, and mock rate table"
```

---

### Task 2: Event engine — processing, validation, idempotency, audit trail

**Files:**
- Create: `forge/lifecycle/engine.py`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Consumes: Task 1's `TRANSITIONS`, `find_transition`, `evaluate_guard`, `INITIAL_STATES`, `rates.converted_units`, `rates.COUNTRY_CURRENCY`.
- Produces (exact, used by Tasks 3-5):
  - `forge.lifecycle.engine.EventRecord` (frozen dataclass): `event_id: str, type: str, occurred_at: str, source: str, amount_units: int, currency: str, result: str, reason: str`
  - `forge.lifecycle.engine.LifecycleResult` (frozen dataclass): `tracks: dict[str, str | None]`, `history: tuple[EventRecord, ...]` (global, file order), `tracks_history: dict[str, tuple[EventRecord, ...]]` (per-track, file order), `converted_units_expected: int`
  - `forge.lifecycle.engine.LifecycleEngine`:
    - `__init__(self, events: list[dict])`
    - `run(self, country: str = "US") -> LifecycleResult`

- [ ] **Step 1: Write the failing tests**

```python
HAPPY = [
    {"event_id": "e1", "type": "auth.accepted", "occurred_at": "2026-11-03T10:00:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e2", "type": "capture.accepted", "occurred_at": "2026-11-03T10:01:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e3", "type": "clearing.submitted", "occurred_at": "2026-11-03T10:02:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e4", "type": "clearing.accepted", "occurred_at": "2026-11-03T10:03:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e5", "type": "settlement.submitted", "occurred_at": "2026-11-03T10:04:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
    {"event_id": "e6", "type": "settlement.accepted", "occurred_at": "2026-11-03T10:05:00Z", "source": "mock-file", "amount_units": 100, "currency": "USD"},
]


class TestEngine(unittest.TestCase):
    def test_happy_path_settles(self):
        res = LifecycleEngine(HAPPY).run()
        self.assertEqual(res.tracks["settlement"], "SETTLED")
        self.assertEqual([r.result for r in res.history], ["applied"] * 6)
        self.assertEqual(len(res.history), 6)

    def test_out_of_order_rejected(self):
        # capture before auth
        events = [HAPPY[1]] + [HAPPY[0]] + HAPPY[2:]
        res = LifecycleEngine(events).run()
        self.assertEqual(res.history[0].result, "rejected")
        self.assertIn("eligible authorization", res.history[0].reason)

    def test_wrong_amount_rejected(self):
        events = [dict(HAPPY[0]), dict(HAPPY[1], amount_units=200)]
        res = LifecycleEngine(events).run()
        self.assertEqual(res.history[1].result, "rejected")
        self.assertIn("$1", res.history[1].reason)

    def test_phase2_event_inactive(self):
        events = [dict(HAPPY[0]), {"event_id": "x", "type": "refund.accepted", "occurred_at": "t", "source": "mock-file", "amount_units": 100, "currency": "USD"}]
        res = LifecycleEngine(events).run()
        self.assertEqual(res.history[1].result, "rejected")
        self.assertIn("inactive", res.history[1].reason)

    def test_duplicate_event_id(self):
        events = [dict(HAPPY[0])] + [dict(HAPPY[0])]
        res = LifecycleEngine(events).run()
        self.assertEqual([r.result for r in res.history], ["applied", "duplicate"])
        self.assertEqual(res.tracks["authorization"], "AUTHORIZED")  # unchanged by replay

    def test_replayable_and_hermetic(self):
        r1 = LifecycleEngine(HAPPY).run()
        r2 = LifecycleEngine(HAPPY).run()
        self.assertEqual([r.result for r in r1.history], [r.result for r in r2.history])
        self.assertEqual(r1.tracks, r2.tracks)

    def test_unknown_event_type(self):
        events = [dict(HAPPY[0]), {"event_id": "u", "type": "bogus.event", "occurred_at": "t", "source": "mock-file", "amount_units": 100, "currency": "USD"}]
        res = LifecycleEngine(events).run()
        self.assertEqual(res.history[1].result, "rejected")
        self.assertIn("unknown", res.history[1].reason)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: FAIL — `ModuleNotFoundError: forge.lifecycle.engine`.

- [ ] **Step 3: Implement `forge/lifecycle/engine.py`**

Processing in file order. `run_currency = rates.COUNTRY_CURRENCY[country]`; `converted_units_expected = rates.converted_units(run_currency)`. Maintain `captured_total_units` (sum of `amount_units` over applied `capture.accepted` events). For each event dict (in this validation order):
1. shape: missing/extra required keys or wrong types → `rejected` "invalid event payload".
2. duplicate `event_id` → `duplicate`.
3. `type` in `INACTIVE_EVENT_TYPES` → `rejected` f"track {track} inactive in phase 1".
4. `type` not found in `TRANSITIONS` → `rejected` "unknown event type".
5. transition's track not in `ACTIVE_TRACKS` → `rejected` f"track {track} inactive in phase 1" (defensive; unreachable given step 3/4).
6. currency: `ev["currency"] != run_currency` → `rejected` f"currency mismatch: file currency {ev['currency']} must be {run_currency}".
7. amount: `ev["amount_units"] != converted_units_expected` → `rejected` f"mock rule: only $1.00 in {run_currency} ({converted_units_expected} minor units); got {amount_units}".
8. own-state precondition: when `from_state is None` the track must currently be `None` (not started); otherwise current track state must equal `from_state` → else `rejected` f"invalid transition {event_type} from {current}".
9. guard: `evaluate_guard(guard, tracks, remaining_units)` where `remaining_units = converted_units_expected − captured_total_units` → else `rejected` with the guard reason.

On success: set the track's state to `to_state`, and if the event is `capture.accepted`, add `amount_units` to `captured_total_units`; record `applied`. All recorded events keep their `result`/`reason`; every event is appended to `history` (global) and its track's `tracks_history` list. `tracks` starts at `INITIAL_STATES` (copy). `converted_units_expected` holds the run-currency value computed at the top.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: PASS (Task 1 + Task 2 tests).

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest -q`
```bash
git add forge/lifecycle/engine.py tests/test_lifecycle.py
git commit -m "feat(lifecycle): event engine with validation, idempotency, and audit trail"
```

---

### Task 3: Derived transaction aggregate

**Files:**
- Create: `forge/lifecycle/aggregate.py`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Consumes: `LifecycleResult.tracks` from Task 2.
- Produces (used by Task 5 CLI):
  - `forge.lifecycle.aggregate.LifecycleAggregate` (frozen dataclass):
    `authorization: str | None`, `capture: str | None`, `clearing: str | None`, `settlement: str | None`,
    `needs_handling: bool` (True iff clearing in {`CLEARING_FAILED`} or settlement in {`SETTLEMENT_FAILED`}),
    `failed: bool` (True iff authorization == `DECLINED`),
    `is_settled: bool` (True iff settlement == `SETTLED`),
    `summary: str` — one-line derived label, exact precedence:
      `"declined"` if `failed`; `"needs_handling"` if `needs_handling`; `"settled"` if `is_settled`;
      else the furthest reached track state: settlement→clearing→capture→authorization non-None,
      else `"none"`.
  - `forge.lifecycle.aggregate.build_aggregate(tracks: dict[str, str | None]) -> LifecycleAggregate`
  - `forge.lifecycle.aggregate.CLEARING_FAILED = "CLEARING_FAILED"` / `SETTLEMENT_FAILED = "SETTLEMENT_FAILED"` module constants reused by tests.

- [ ] **Step 1: Write the failing tests**

```python
class TestAggregate(unittest.TestCase):
    def test_settled_aggregate(self):
        tracks = {"authorization": "AUTHORIZED", "capture": "CAPTURED", "clearing": "CLEARED", "settlement": "SETTLED"}
        a = build_aggregate(tracks)
        self.assertTrue(a.is_settled)
        self.assertFalse(a.failed)
        self.assertFalse(a.needs_handling)
        self.assertEqual(a.summary, "settled")

    def test_settlement_failed_is_needs_handling_not_failed(self):
        tracks = {"authorization": "AUTHORIZED", "capture": "CAPTURED", "clearing": "CLEARED", "settlement": "SETTLEMENT_FAILED"}
        a = build_aggregate(tracks)
        self.assertTrue(a.needs_handling)
        self.assertFalse(a.failed)
        self.assertEqual(a.summary, "needs_handling")

    def test_declined_is_failed(self):
        tracks = {"authorization": "DECLINED", "capture": None, "clearing": None, "settlement": None}
        a = build_aggregate(tracks)
        self.assertTrue(a.failed)
        self.assertEqual(a.summary, "declined")

    def test_furthest_reached_when_not_terminal(self):
        tracks = {"authorization": "AUTHORIZED", "capture": "CAPTURED", "clearing": "CLEARING_PENDING", "settlement": None}
        a = build_aggregate(tracks)
        self.assertEqual(a.summary, "clearing_pending")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: FAIL — `ModuleNotFoundError: forge.lifecycle.aggregate`.

- [ ] **Step 3: Implement `forge/lifecycle/aggregate.py`**

Derived read model — computes from `tracks` only, stores nothing. `summary` uses the exact precedence above; `clearing_pending` comes from the furthest-reached fallback (lowercase the non-None state name).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest -q`
```bash
git add forge/lifecycle/aggregate.py tests/test_lifecycle.py
git commit -m "feat(lifecycle): derived transaction aggregate read model"
```

---

### Task 4: Reconciliation (Phase 1)

**Files:**
- Create: `forge/lifecycle/reconciliation.py`
- Test: `tests/test_reconciliation.py`

**Interfaces:**
- Consumes: nothing from earlier tasks except the event-file JSON shape (Task 2's dict fields `event_id, type, occurred_at, amount_units, currency`).
- Produces (used by Task 5 CLI):
  - `forge.lifecycle.reconciliation.ReconRow` (frozen dataclass): `event_id: str, status: str, diffs: tuple[str, ...]`
    status ∈ {`match`, `mismatch`, `missing_external`, `unexpected_external`}
  - `forge.lifecycle.reconciliation.ReconciliationReport` (frozen dataclass): `rows: tuple[ReconRow, ...]`, `counts: dict[str, int]`, `matches: int`, `mismatches: int`, `missing_external: int`, `unexpected_external: int`
  - `forge.lifecycle.reconciliation.reconcile(internal: list[dict], external: list[dict]) -> ReconciliationReport`
  - Diff fields (exact): `type`, `occurred_at`, `amount_units`, `currency`. `event_id` is the join key, never diffed. Engine metadata (`result`, `reason`, `source`) is never diffed.
  - `forge.lifecycle.reconciliation.events_from_file(path: str) -> list[dict]` — read JSON file, return the `events` list (file shape: `{"events": [...]}`).

- [ ] **Step 1: Write the failing tests**

```python
INT = [
    {"event_id": "e1", "type": "auth.accepted", "occurred_at": "t1", "amount_units": 100, "currency": "USD"},
    {"event_id": "e2", "type": "capture.accepted", "occurred_at": "t2", "amount_units": 100, "currency": "USD"},
    {"event_id": "e3", "type": "clearing.accepted", "occurred_at": "t3", "amount_units": 100, "currency": "USD"},
]


class TestReconciliation(unittest.TestCase):
    def test_exact_match(self):
        ext = [dict(e) for e in INT]
        rep = reconcile(INT, ext)
        self.assertEqual(rep.matches, 3)
        self.assertEqual(rep.counts["mismatch"], 0)

    def test_mismatch_per_field(self):
        ext = [dict(INT[0], amount_units=999), dict(e) for e in INT[1:]]
        rep = reconcile(INT, ext)
        self.assertEqual(rep.mismatches, 1)
        self.assertEqual(rep.rows[0].diffs, ("amount_units",))

    def test_missing_and_unexpected(self):
        ext = [dict(e) for e in INT] + [{"event_id": "e9", "type": "auth.declined", "occurred_at": "t9", "amount_units": 100, "currency": "USD"}]
        internal_missing_one = INT[:-1]
        rep = reconcile(internal_missing_one, ext)
        self.assertEqual(rep.missing_external, 1)  # e3 present externally only
        self.assertEqual(rep.unexpected_external, 1)  # e9

    def test_metadata_never_diffed(self):
        internal = [dict(INT[0])]
        external = [dict(INT[0], result="applied", reason="x", source="reconciliation")]
        rep = reconcile(internal, external)
        self.assertEqual(rep.matches, 1)
        self.assertEqual(rep.rows[0].diffs, ())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_reconciliation.py -q`
Expected: FAIL — `ModuleNotFoundError: forge.lifecycle.reconciliation`.

- [ ] **Step 3: Implement `forge/lifecycle/reconciliation.py`**

Join by `event_id`. Field diff over the exact four fields. Reconcile is read-only — it returns a report and never writes to any lifecycle history. `events_from_file` reads `{"events": [...]}`; missing file or malformed JSON raises `FileNotFoundError`/`ValueError` naturally.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_reconciliation.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest -q`
```bash
git add forge/lifecycle/reconciliation.py tests/test_reconciliation.py
git commit -m "feat(lifecycle): phase-1 reconciliation over event files"
```

---

### Task 5: CLI — `forge lifecycle` and `forge reconcile`

**Files:**
- Modify: `forge/cli/main.py` (subcommand registration ~633-685; new command functions)
- Test: `tests/test_issuer.py`

**Interfaces:**
- Consumes: `LifecycleEngine`, `LifecycleResult`, `build_aggregate`, `reconcile`, `events_from_file` from Tasks 1-4.
- Produces: two argparse subcommands. Text output + `--json`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_issuer.py -q`
Expected: FAIL — `usage: forge ... invalid choice: 'lifecycle'`.

- [ ] **Step 3: Wire the two subcommands in `forge/cli/main.py`**

- `p_lifecycle = sub.add_parser("lifecycle", help="Event-driven per-track lifecycle simulator (mock-only)")` with `--events` (required, path), `--country` (default "US", choices=COUNTRY_CURRENCY), `--json`.
- `cmd_lifecycle(a)` → load events, `LifecycleEngine(events).run(country=a.country)`, build aggregate, print:
  - text: a `Lifecycle Trace:` block listing each `EventRecord` as `  e1 auth.accepted -> applied (reason)` using the existing `dim`/`bold`/`warn` helpers; a `Tracks:` block; `Summary : <summary>`; `Amount  : <currency> <units>`; `$1 rule  : expected <expected> minor units`.
  - json: `{"tracks": ..., "aggregate": <aggregate.__dict__>, "audit": [record.__dict__ ...], "currency": ..., "expected_units": ...}`.
- `p_reconcile = sub.add_parser("reconcile", help="Phase-1 reconciliation over event files")` with `--internal` (required), `--external` (required), `--json`.
- `cmd_reconcile(a)` → `events_from_file` both, `reconcile(...)`, print text rows + counts; `--json` emits the report.
- Return 0 on success, nonzero only on file/JSON errors.
- Register both in `main()`'s dispatch (mirror how `cmd_funnel`/`cmd_currency` are dispatched).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_issuer.py -q`
Expected: PASS (4 new tests; existing CLI tests still green).

- [ ] **Step 5: Full suite twice + commit**

Run: `python3 -m pytest -q` twice; identical counts both runs (hermetic).
```bash
git add forge/cli/main.py tests/test_issuer.py
git commit -m "feat(lifecycle): forge lifecycle and forge reconcile CLI commands"
```

---

### Task 6: Docs + final gate

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-11-03-forge-lifecycle-design.md` (status → implemented)

- [ ] **Step 1: Update README**

Add a `### <N>. Forge Lifecycle Simulator (\`forge lifecycle\`)` section: what it is (event-driven per-track simulator, mock-only, no inference), the $1-rule, the active tracks, the `SETTLED`-is-not-finished rule, an example `forge lifecycle --events happy.json --json` + `forge reconcile --internal --external --json` line, and the note that Reversal/Dispute/Refund tracks are declared but inactive in Phase 1.

- [ ] **Step 2: Final verification**

Run: `python3 forge.py selftest` (offline) and `python3 -m pytest -q` once. No `forge doctor`, no `run --target`, no binlist/proxy calls — mocks only, per constraint.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-11-03-forge-lifecycle-design.md
git commit -m "docs: document forge lifecycle and reconciliation"
```
