# ReconcileOS

**Autonomous reconciliation for the office of the CFO.**

Finance teams close the books by tying together feeds that never quite agree: a corporate card
statement, a bank statement, an ERP invoice ledger, an ops export, a processor payout report, and
GSTR-2B filings. Most of that work is matching rows, chasing the ones that don't match, and being
able to prove afterwards why each decision was made.

ReconcileOS does the matching deterministically, scores its own confidence, and then **refuses to
act unattended when it shouldn't** — routing anything ambiguous, material, or risky to a human
queue. Every outcome is written to a hash-chained audit log, and every case can be exported as a
self-contained evidence pack.

---

## Why this is not just a matching script

The interesting engineering is in what happens when matching is *uncertain*:

- **Confidence is explainable, not a black box.** Every score decomposes into weighted features
  (amount, reference, merchant, date proximity) and emits human-readable reasons.
- **Policy is configuration, not code.** Thresholds live in `config/policies.yaml`. Changing what
  auto-resolves does not require a code change.
- **The safety metric is measured, not asserted.** `evals/` scores the engine against a labelled
  golden set. Its headline number is `unsafe_auto_resolve` — how often the system auto-resolved
  something a human should have seen. It must be **0**.
- **Hallucinations cannot reach the ledger.** When the LLM adjudicates an ambiguous match, its
  answer is validated against the real candidate ids. A proposed id that doesn't exist is rejected.
- **The audit log is tamper-evident.** Each event hashes over the previous one, so an edited row
  breaks the chain and `GET /audit/verify` reports where.

---

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

The demo dataset generates itself on first run. No database to provision, no auth to configure —
the server binds to localhost and `actor_id` comes from an `X-Actor-Id` header purely so the audit
log has an author.

Run the evaluation harness:

```bash
python -m evals.run          # writes evals/reports/scorecard.md
pytest -q                    # full test suite
```

---

## What it does

| Workflow | Module |
|---|---|
| Card ↔ bank cash matching, incl. 1:many aggregated payouts | `app/engine/matching.py` |
| Merchant resolution and descriptor normalization | `app/engine/normalize.py` |
| GST purchase register ↔ GSTR-2B, with input-tax-credit risk | `app/engine/gst.py` |
| Ops ↔ ERP ↔ bank three-way close | `app/engine/close.py` |
| Processor settlement (gross − fees = net) | `app/adapters/payout.py` |

Supporting harness:

| Concern | Module |
|---|---|
| Hash-chained audit + verification | `app/harness/audit.py` |
| Evidence pack (ZIP per case) | `app/harness/evidence.py` |
| Guardrails / validators | `app/harness/guardrails.py` |
| Idempotency (exactly-once actions) | `app/harness/idempotency.py` |
| Notification outbox | `app/harness/notify.py` |
| Chaos injection | `app/harness/chaos.py` |
| Neatlogs tracing | `app/harness/tracing.py` |
| Model router (TensorMux → OpenAI failover) | `app/harness/modelrouter.py` |
| Learned rule memory | `app/memory/rules.py` |

---

## How matching works

1. **Normalize.** Strip card-network noise from descriptors (`POS VISA STARBUCKS INDIA PVT LTD
   4412998` → `STARBUCKS`), coerce amounts and dates, resolve the merchant by fuzzy match.
2. **Detect duplicates** — identical amount, date and descriptor.
3. **Detect splits.** One bank credit may be the aggregate of several card rows. Bounded subset-sum
   finds the combination.
4. **Match one-to-one**, ranking candidates by `(reference_exact, confidence, -date_delta)` so a
   shared payment reference always wins ties.
5. **Classify the exception** — the taxonomy is ordered, so a duplicate outranks an unmatched row.
6. **Apply policy** to decide auto-resolve vs. human review.
7. **Write an audit event** for every case, chained to the last.

A source or target is consumed at most once across the whole pass.

---

## Deliberate design decisions

**Aggregated payouts never auto-resolve.** Subset-sum is a heuristic: several different
combinations of card rows can sum to the same bank total, so a 1:many match can be coincidentally
wrong. `split_payment` is in `blocked_exception_types`, so a human confirms it. This was found by
the eval harness, not by inspection — the first scorecard run reported `unsafe_auto_resolve: 1`.

**The LLM is not on the critical path.** Deterministic rules do the matching. The model only
adjudicates the ambiguous band (0.60 ≤ confidence < 0.85), its output is guardrail-validated, and
if it fails or is unavailable the pipeline degrades to the deterministic result.

**Tracing degrades silently.** If `NEATLOGS_API_KEY` is absent or the SDK errors, the app runs
identically. A tracing failure can never break a reconciliation run.

**The UI is one self-contained HTML file.** Not a Vite/React build. It has no build step and no CDN
dependencies, so it works offline. This is a deliberate deviation from the original architecture
document, chosen so the demo cannot fail on stage because of a network or toolchain problem.

---

## Environment

```bash
NEATLOGS_API_KEY=      # optional; tracing no-ops without it
OPENAI_API_KEY=        # optional; adjudication degrades without it
TENSORMUX_API_KEY=     # optional; primary inference provider
DB_PATH=./reconcileos.db
POLICY_VERSION=v1
```

No auth variables. There is nothing to log into.

---

## Testing

Every module ships with its own test suite. Beyond per-module tests, the build is gated on two
end-to-end verifiers that exercise real behaviour rather than mocks:

- a full pipeline run asserting the planted demo scenarios actually occur (a duplicate is caught,
  the aggregated payout is matched by subset-sum, the audit chain verifies)
- the eval scorecard, which fails the build if `unsafe_auto_resolve` is anything but 0

---

## How this was built

The application code in this repository was written by LLM worker agents driven by a custom
orchestrator (`gpt-5-nano` and `glm-4-7-flash` behind an OpenAI-compatible interface). The
orchestrator dispatches narrowly-scoped tasks with disjoint file ownership, verifies each one
against a mechanical check, feeds failures back for repair, and escalates to a larger-context model
when a worker loops on the same broken output. A second model reviews finished code against its
specification to catch requirements that were silently skipped.
