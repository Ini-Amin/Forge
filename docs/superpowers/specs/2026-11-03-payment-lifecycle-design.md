# Payment Lifecycle: authorization / clearing / settlement

Date: 2026-11-03
Status: ~~proposed (awaiting approval)~~ implemented — Phase A and Phase C
landed 2026-11-03; optional wrap-up B skipped (YAGNI)
Size: small, in two phases (A then C); B optional wrap-up

## Why

`forge funnel` labels a card that passes the 4-layer risk gate as `SETTLED`.
Approval is an **authorization-time** decision; settlement is a separate,
later event (batch clearing, funding window). Today forge claims money moved
when all it modeled is "the card was approved". The card-rails lifecycle —
auth-hold/capture, batch clearing, settlement — is absent.

## Goals

- Stop presenting approval as settlement: passing disposition becomes
  `AUTHORIZED`, not `SETTLED`.
- Make the money lifecycle visible and deterministic: an `AUTHORIZED`
  transaction carries an `AUTH → CLEAR → SETTLE` trace.
- No invented rates, no money amounts, no dates arithmetic. Rules derive
  from fields forge already carries (funding type, currency, country).

## Non-goals / anti-goals

- No invented clearing/settlement failure probabilities (forge's honesty rule).
- No amounts tested or exercised anywhere in the mock lifecycle.
- No real endpoints in tests; suite stays hermetic (mock/fixtures only).
- No new CLI commands in phase A.

## Approach

Selected: **A first, then C**.

### Phase A — fix the adjective, trace the money

`forge/defenders/funnel.py`:

- `final_disposition` passing value `SETTLED` → `AUTHORIZED`. Rejections
  (`REJECTED_BY_*`, `CHALLENGE_3DS`) unchanged.
- New field `money_lifecycle: list[StageVerdict]`, three staged records
  (authorization, clearing, settlement).
  - final == `AUTHORIZED`: authorization PASS ("approved at issuer layer;
    authorization only"), clearing PASS ("routable for clearing in
    <currency>"), settlement DEFERRED for credit cards ("funds move after the
    capture window — not settled at approval"), PASS for debit ("same-day
    batch"), PASS for prepaid ("balance deducted at capture").
  - final != `AUTHORIZED`: authorization carries the actual disposition;
    clearing/settlement verdict `N_A` ("never reached — <disposition>").
- Verdict vocabulary: `PASS` / `DEFERRED` / `BLOCK` / `N_A`. No amounts.

`forge/cli/main.py`:

- Badge color: `AUTHORIZED` renders neutral (warn), not the ok-green used for
  `SETTLED`.
- `cmd_funnel` text + JSON and the `cmd_run` audit artifact include
  `money_lifecycle`.

Tests (`tests/test_defenders_advanced.py`, `tests/test_issuer.py`):

- `SETTLED` expectation → `AUTHORIZED`.
- New: passing funnel yields 3 lifecycle stages; credit → settlement
  DEFERRED; prepaid → PASS; rejected funnel yields `N_A` for clearing and
  settlement.

### Phase C — card-rails state machine (after A)

`forge/payments/state_machine.py`: extend the lifecycle to card-rails states
(`AUTHORIZED → CAPTURED → CLEARED → SETTLED` plus failure edges wired to the
existing decline taxonomy), and have phase A's trace report the reached
state. Scope confirmed in its own design/plan step after A lands.

### B — optional wrap-up

Only if A and C are done and a standalone `forge lifecycle` command adds
real value; otherwise skipped (YAGNI).

## The knock-on decision

I get to name the lifecycle detail strings and the order of the three
stages; the user sets the *semantics* rules (credit DEFERRED, debit PASS,
prepaid PASS). `AUTHORIZED` replaces `SETTLED` in `funnel.py`, `main.py`
(two call sites + audit), and one test assertion.