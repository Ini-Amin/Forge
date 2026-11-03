# Forge Lifecycle: event-driven per-track state machine + reconciliation

Date: 2026-11-03
Status: proposed (awaiting approval)
Size: project — Phase 1 MVP (execution authorized), Phase 2-3 deferred

## Why

The funnel snapshots a transaction at authorization time and reports a static
`money_lifecycle` + `rails_state`. Nothing simulates what happens *after* that
decision: capture, clearing, settlement, and the post-settlement world
(disputes, refunds, reversals). `forge lifecycle` is an explicit
event-driven simulator for that. `forge reconcile` (Phase 1) compares internal
records against supplied external/mock records.

## Goals

- Simulate a transaction's lifecycle from `AUTHORIZED` forward, driven ONLY by
  explicitly supplied mock events — never inferred, never fabricated.
- Per-track state machine: a transaction can simultaneously be `SETTLED`
  (Settlement track) and `CHARGEBACK_RECEIVED` (Dispute track).
- Invalid transitions rejected with auditable reasons; other tracks untouched.
- Deterministic, replayable, idempotent event processing.
- Geo-coherent mock amounts: base `$1.00` converts to the destination
  country's currency via an explicit fixture rate table (never a runtime
  invention), rendered in correct minor units.
- Reconciliation in Phase 1: compare internal records vs supplied
  external/mock records, reporting differences — never mutating lifecycle state.
- Probe / Lifecycle / Reconciliation are separate concerns and never interfere.

## Non-goals / anti-goals

- No runtime-invented rates, no invented timing. Conversion happens ONLY through
  the explicit fixture rate table in `forge/lifecycle/rates.py`; anything else
  is rejected. Amounts are `(currency, minor_units)` carried verbatim from
  events.
- No inference: success of prior states NEVER advances the lifecycle. Absence of
  optional-track events = empty event list for that track, never a fabricated
  transition, never marks the transaction failed/incomplete.
- Refund / Dispute / Reversal are Phase 2. Their state names exist in the
  shared vocabulary but NO event/transition is wired until implemented.
- No real endpoints; suite stays hermetic (mock events only).
- Reconciliation does not alter lifecycle state and is not blocked by absent
  optional events.

## Amount rule (mock)

- Base amount is always `$1.00 USD` = `amount_units: 100`.
- **Geo-coherent conversion (user-selected):** when a destination country/
  currency is chosen, the base `$1.00` converts into that currency using an
  EXPLICIT mock rate table supplied in the fixtures (`forge/lifecycle/rates.py`),
  e.g. `USD→JPY = 150.00`. Rates are sourced constants, never invented at
  runtime; an unknown currency is rejected with an auditable reason.
- Conversion result is rendered in that currency's minor units using
  `CurrencyPrecisionAuditor.audit_amount_to_units` (correct per ISO 4217:
  JPY zero-decimal → ¥150 = 150 units, not 15000).
- Mock validator REJECTS any event whose base `amount_units != 100` (rule:
  only $1 in mock), with the reason recorded in the audit trail. Converted
  values derive deterministically from the rate table.
- A file must not mix currencies: all events in one run share the run's target
  currency (default USD). Country/geo-coherent fields are provenance metadata;
  the rate table is the only conversion authority.

## Architecture

Three layers:

1. **Event history** (source of truth, immutable, append-only):
   each track keeps its own ordered list. Every event carries:
   `event_id` (idempotency key), `type`, `occurred_at`, `source` (provenance:
   "mock-file", "cli", "reconciliation"), `amount_units` (int), `currency`,
   result (`applied | rejected | duplicate`), reason (str).
2. **Track states**: one current state per track, transitions only through
   valid edges. Track definitions own their states/events/edges.
3. **Transaction aggregate** (derived read model, never a stored status):
   computed from track states on demand. Never a scalar "status" field.

### Track vocabulary (shared, declared now; only Phase 1 tracks active)

- Authorization: `PENDING, AUTHORIZED, DECLINED`
- Capture: `CAPTURED, PARTIALLY_CAPTURED`
- Clearing: `CLEARING_PENDING, CLEARED, CLEARING_FAILED`
- Settlement: `SETTLEMENT_PENDING, SETTLED, SETTLEMENT_FAILED`
- Reversal: `REVERSED, VOIDED` — **Phase 2, inactive**
- Dispute: `DISPUTED, CHARGEBACK_RECEIVED, CHARGEBACK_WON, CHARGEBACK_LOST` — **Phase 2, inactive**
- Refund: `REFUND_PENDING, PARTIALLY_REFUNDED, REFUNDED` — **Phase 2, inactive**

`SETTLED` is terminal ONLY within the Settlement track — never a global
"transaction finished" flag.

### Phase 1 active events (explicit only)

- `auth.accepted` (PENDING → AUTHORIZED), `auth.declined` (PENDING → DECLINED)
- `capture.accepted` (AUTHORIZED → CAPTURED; needs eligible auth: sisa > 0)
- `clearing.accepted` (CAPTURED → CLEARED), `clearing.failed` (CAPTURED → CLEARING_FAILED)
- `settlement.accepted` (CLEARED → SETTLED), `settlement.failed` (CLEARED → SETTLEMENT_FAILED)

Cross-track guards:
- `capture.accepted` requires Authorization track in `AUTHORIZED` and
  remaining = authorized − sum(captured) > 0.
- `clearing.accepted` requires Capture in `CAPTURED`.
- `settlement.accepted` requires Clearing in `CLEARED`.

Rejected guard → event recorded as `rejected` + reason; no other track changes.

### Reconciliation (Phase 1)

`forge reconcile` reads internal records (the lifecycle's applied events) and
a supplied external/mock record set (same schema). For each record:
- exact match → `match`
- same `event_id`, differing fields → `mismatch` (per-field diff, no FX)
- present internally but not externally → `missing_external`
- present externally but not internally → `unexpected_external`
Output is a report; it never writes to lifecycle event history.

## CLI surface

- `forge lifecycle --events <file.json> [--country US] [--json]`
  Events in, audit trail out. `--country` selects the geo-coherent conversion
  target (default US); amounts are reported in that country's currency.
  `--json` machine-readable.
- `forge reconcile --internal <file.json> --external <file.json> [--json]`
- `forge lifecycle` and `forge reconcile` never touch network/proxy.

## Files

- New: `forge/lifecycle/__init__.py`, `forge/lifecycle/state.py` (tracks,
  states, transitions), `forge/lifecycle/engine.py` (event processing,
  guards, idempotency), `forge/lifecycle/aggregate.py` (derived read model),
  `forge/lifecycle/rates.py` (explicit mock FX fixture table),
  `forge/lifecycle/reconciliation.py`
- Modify: `forge/cli/main.py` (two new subcommands)
- Tests: `tests/test_lifecycle.py`, `tests/test_reconciliation.py`

## Left to the builder

- Exact JSON event schema field names and ordering.
- Audit-trail rendering format in text vs `--json`.
- Which events drive each per-field mismatch report line.

## Settled decisions (controller calls, 2026-11-03)

- **Processing order:** file order. Deterministic and replayable; `occurred_at`
  is provenance metadata, never drives ordering. Events arriving out of logical
  order are recorded `rejected` with the guard reason.
- **File scope:** one `--events` file = one transaction. No transaction_id in
  Phase 1; one aggregate per run.
- **Reconcile inputs:** both `--internal` and `--external` are event files in
  the same schema. `forge lifecycle --json` emits an event-list export usable
  as `--internal`. Diff is per-event by `event_id` over input fields only
  (`type`, `occurred_at`, `amount_units`, `currency`); engine metadata
  (`result`, `reason`, `source`) is never diffed.
- **Mixed currency:** a file containing events with differing `currency` is
  rejected with an auditable reason (all events in one run share the run's
  target currency — the base is always USD `$1.00`, converted per country).
