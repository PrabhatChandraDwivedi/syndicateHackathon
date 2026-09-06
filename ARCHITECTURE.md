# ReconcileOS — Final Architecture

**Autonomous Finance Reconciliation & Close Agent**
**Syndicate by Maximor · Track 2 — Autonomous Office of the CFO**

**Status:** Final, build-ready. This document supersedes `docs/Track-2-Original-Architecture.md`
(kept for reference). Everything below is scoped to what a small team can actually ship and
demo in **3 minutes**.

---

## 0. What changed from the original spec, and why

The original spec (`docs/Track-2-Original-Architecture.md`) is a good *product* document but an
over-scoped *engineering* document. A parallel spec (AgentLedger) proposed a TypeScript/Next.js/
Supabase stack with Supabase Auth, RBAC, Upstash Redis, and Vercel. Both are trimmed here.

### Removed — deliberately, not by accident

| Removed | Why |
|---|---|
| Login / signup / sessions | Zero judging weight. Single-operator demo app. |
| 2FA / MFA | Same. Costs half a day, earns nothing. |
| Supabase Auth, RBAC, reviewer roles | Replaced by a single `actor_id` field on every audit event. Role separation is *modelled in data*, not enforced by a login wall. |
| Multi-tenancy | Single org (`abc_software`). `entity_id` exists in the schema so multi-tenancy is a later migration, not a rewrite. |
| Upstash Redis | SQLite handles idempotency keys and locks at demo scale. One less hosted dependency to fail on stage. |
| Vercel / managed hosting | We run our own server (`uvicorn`). Fully local demo = no network risk during the video. |
| Kafka / RabbitMQ / K8s / microservices | An in-process job queue backed by a SQLite `outbox` table is sufficient and is *visible* in the audit trail. |
| Vector DB / embeddings | Merchant + entity resolution is solved better and more explainably by normalization + RapidFuzz + a learned alias table. |
| Real GST portal / real bank / real ERP connectors | Adapters are behind an interface; hackathon inputs are CSV/JSON + Dodo test webhooks. |
| Full GL replacement, tax filing engine, payroll | Out of Track 2's demonstrable scope. |
| **Ops↔ERP↔Bank matching engine (Workflow 3)** | **Scope call.** It never appears in the demo except as one dashboard row. Shipped as a *seeded status row* with real blocker cases, not a fourth matching engine. See §1. |
| **Replay harness** | The hash-chained audit log already answers "why did this happen in September." Deterministic re-execution is a production feature, not a prototype one. |
| Dodo subscriptions, disputes, refund reversals, settlement-timing logic | Kept the webhook path and one derived exception; dropped the rest. See §8. |

### Kept and hardened

Canonical store, deterministic-first matching, confidence + policy, human exception queue,
structured rule memory, append-only audit log, close-readiness dashboard, four workflows.

### Added — the harness layer (this is the new part)

The original doc described *what the agent does*. It barely described *what the agent runs on*.
Sections 4–13 below define **eleven harnesses** that wrap the agent, plus the four sponsor
integrations (**AO, Neatlogs, TensorMux, Dodo Payments**). These are where "Technical Execution
& Reliability" (25%) and "AO Usage & Build Process" (25%) — half the total score — are actually won.

---

## 1. One-paragraph product statement

Finance teams spend their month asking the same question in four costumes: *two systems describe
the same money differently — which records are the same event, and what do I do about the ones
that aren't?* ReconcileOS is one agent with one operating loop that ingests both sides, normalizes
identities, matches deterministically first and probabilistically second, auto-resolves only what
policy says is safe, escalates the rest to a human with evidence and alternatives, turns each human
decision into a scoped reusable rule, and writes a hash-chained audit event for every state change.
The output is a continuously-improving **close-readiness** number instead of a month-end fire drill.

**Three workflows are built end-to-end** (same engine, different record sets):

| # | Workflow | Set A | Set B | Question | Status |
|---|---|---|---|---|---|
| 1 | Card merchant normalization | Card transactions | Merchant master + GL categories | Who is this merchant, how is it classified? | **Built** |
| 2 | Cash application | Incoming bank/Dodo payments | Open AR invoices | Which invoice(s) did this cash settle? | **Built** |
| 3 | GST purchase reconciliation | Purchase register | GSTR-2B | Which invoices are supported / missing / mismatched? | **Built** |
| — | Ops ↔ ERP ↔ Bank close | Ops/sales export | ERP + bank | Do the systems agree, what blocks close? | **Status row only** |

**On Workflow 3 (Ops↔ERP↔Bank):** the architecture supports it — same canonical records, same
policy, same queue — but for the prototype it ships as a **seeded status row** on the close
dashboard carrying two real blocker cases (an intercompany difference and a missing ERP record),
not as a fourth matching engine. It is honestly labelled as such in the README and the demo never
claims otherwise. The engine generalizes to it; we just aren't spending prototype hours proving that
on camera.

---

## 2. System architecture

```mermaid
flowchart TB
    subgraph SRC["Sources"]
      S1[Bank CSV]
      S2[Card CSV]
      S3[AR Invoices CSV]
      S4[Purchase Register CSV]
      S5[GSTR-2B JSON]
      S6["Dodo Payments<br/>test-mode webhooks"]
    end

    subgraph HARNESS["Harness layer"]
      ING[H1 Ingestion + freshness]
      TOOL[H2 Typed tool registry]
      IDEM[H3 Idempotency + action state]
      GUARD[H4 Guardrails / validators]
      SCHED[H5 Scheduler]
      EVAL[H6 Eval harness]
      CHAOS[H7 Chaos injection]
      NOTIF[H8 Notifications]
      OBS[H9 Neatlogs tracing]
      LLM[H10 TensorMux model router]
      AUD[H11 Hash-chained audit + evidence pack]
    end

    SRC --> ING --> CAN[(Canonical Store · SQLite)]

    CAN --> NORM[Entity Normalization]
    NORM --> ENG[Reconciliation Engine<br/>rules → candidates → scoring → LLM shortlist]
    MEM[(Structured Rule Memory)] --> ENG
    ENG --> POL[Policy + Confidence Engine<br/>policies.yaml v1]

    POL -->|safe + high conf| AUTO[Auto-resolve / draft journal]
    POL -->|ambiguous / material / blocked| HQ[Human Exception Queue]
    HQ --> DEC[Approve · Edit · Reject · Defer]
    DEC --> MEM
    AUTO --> AUD
    DEC --> AUD
    AUD --> CLOSE[Close-Readiness Dashboard]

    TOOL -.wraps.- ENG
    GUARD -.validates.- ENG
    LLM -.serves.- ENG
    OBS -.traces.- ENG
    IDEM -.gates.- AUTO
    EVAL -.scores.- ENG
    CHAOS -.attacks.- ING
```

### Stack decision

| Layer | Choice | Rationale |
|---|---|---|
| Language | **Python 3.11** | Neatlogs' primary SDK is Python; pandas/RapidFuzz/subset-sum matching is far stronger here than in TS. |
| API server | **FastAPI + uvicorn** | We run our own server. No platform lock-in, no cold starts, works offline on stage. |
| Store | **SQLite** (WAL mode) | Single file, transactional, trivially resettable between demo takes. `entity_id` present for later Postgres migration. |
| Schemas | **Pydantic v2** | Every tool input/output is a validated model — this *is* the guardrail layer. |
| Matching | pandas, RapidFuzz, bounded subset-sum | Deterministic, explainable, no vector DB. |
| Jobs | APScheduler + SQLite `outbox` table | Continuous close without infrastructure. |
| Frontend | **Vite + React + Tailwind**, 5 screens | Fast, no auth, reads the same REST API the agent writes to. |
| Inference | **TensorMux** (OpenAI-compatible) | Routing + metering, see §7. |
| Tracing | **Neatlogs** | See §6. |
| Payments feed | **Dodo Payments test mode** | See §8. |
| Dev orchestration | **AO** | See §5. Mandatory. |

**No auth of any kind.** The server binds to localhost. `actor_id` is set by a header
(`X-Actor-Id`, defaults to `finance_user_01`) purely so the audit log has an author.

---

## 3. Canonical data model

Unchanged in spirit from the original spec, with harness fields added (marked **new**).

```python
FinancialTransaction:
  id, source: bank|corporate_card|payment_processor|dodo
  account_id, date, amount, currency
  counterparty_raw, reference_raw
  raw_payload: JSON                       # always kept — evidence
  source_file_id, ingested_at             # new: provenance
  external_id                             # new: Dodo payment_id, for idempotency

Invoice:
  id, invoice_number, entity_id, counterparty_id
  invoice_type: sales|purchase
  invoice_date, due_date
  taxable_amount, tax_amount, open_amount, status
  raw_payload, source_file_id

Merchant:      merchant_id, canonical_name, aliases[], default_gl_code
GSTRecord:     supplier_gstin, recipient_gstin, invoice_number, invoice_date,
               taxable_value, igst, cgst, sgst, source, raw_payload

ReconciliationCase:
  case_id, workflow, source_ids[], candidate_target_ids[]
  status: proposed|auto_resolved|queued|approved|rejected|deferred
  confidence, method, financial_impact, evidence[]
  alternatives[]                          # new: ranked runner-ups, always ≥1 when queued
  exception_type                          # new: from §9 taxonomy, nullable
  policy_version, rule_ids_used[]         # new
  neatlogs_trace_id                       # new: click-through from audit → agent reasoning
  token_cost_usd, latency_ms              # new: from TensorMux metering

HumanDecision:
  case_id, actor_id, action, final_allocations, comment, created_rule_ids[]

LearnedRule:
  rule_id, rule_type, pattern, target, scope
  source_case_id, confidence, created_at, last_used_at, use_count
  status: active|expired|disabled         # new
  never_auto: bool                        # new

AuditEvent:                               # append-only, hash-chained
  seq, timestamp, actor_type, actor_id, case_id, event_type
  before_state, after_state, inputs_hash, policy_version, model_version
  neatlogs_trace_id
  prev_hash, this_hash                    # new: tamper evidence, see §13

ActionState:                              # new: at-most-once side effects
  idempotency_key (PK), case_id, action_type, status, result, attempts
```

---

## 4. The harness layer

Eleven harnesses. Each is a module under `app/harness/`, each is independently testable, and each
produces something a judge can see. Anything that couldn't earn its place either on camera or in
the scorecard was cut.

### H1 — Ingestion harness
- Adapter per source; the engine never sees a raw CSV column name.
- **Column sniffing** with a per-adapter mapping file, so a slightly-different bank export doesn't crash the demo.
- **File fingerprinting** (`sha256`) → re-uploading the same file is a no-op, not a duplicate.
- **Freshness stamps**: every `source_file` carries `as_of`. Policy can block auto-actions when data is stale (§10, `STALE_SOURCE_DATA`).
- Row-level rejects go to a quarantine table with the reason — never silently dropped.

### H2 — Typed tool registry
The LLM orchestrates; deterministic Python tools calculate. Every tool is a Pydantic in/out pair,
registered with a **permission tier**:

| Tier | Meaning | Examples |
|---|---|---|
| `READ` | No state change | `find_invoice_candidates`, `get_close_readiness` |
| `PROPOSE` | Writes a proposal only | `score_invoice_allocation`, `propose_journal`, `draft_vendor_email` |
| `ACT` | Real side effect — **always** idempotency-gated, and approval-gated by policy | `post_cash_allocation`, `send_vendor_email`, `close_period_task` |

Full tool list:

```
ingest_bank_statement · ingest_card_statement · ingest_open_invoices
ingest_purchase_register · ingest_gstr2b · ingest_dodo_webhook

normalize_entity · resolve_merchant · find_customer_candidates
find_invoice_candidates · score_invoice_allocation · match_gst_invoice
detect_duplicate_transaction · compute_residual
classify_reconciliation_exception · explain_case

create_human_review · record_human_decision · create_structured_rule
propose_journal · draft_vendor_email · get_close_readiness
write_audit_event · export_evidence_pack
post_cash_allocation · send_vendor_email · close_period_task
```

Every tool invocation → one Neatlogs span + one audit event. There is no code path where the agent
does something the log doesn't know about.

### H3 — Idempotency & action-state harness
`idempotency_key = sha256(case_id | action_type | payload_digest)`. `ACT` tools check
`ActionState` first and return the prior result on replay. Kills the classic failure mode:
retry → duplicate journal posting / duplicate vendor email.

### H4 — Guardrail harness (this is the anti-hallucination layer)
Runs on every LLM output before it can become a proposal:
1. **Schema validation** — structured output or reject.
2. **Existence check** — every referenced `invoice_id` / `case_id` / `merchant_id` must exist in SQLite. A model-invented invoice is rejected, not surfaced.
3. **Arithmetic verifier** — Python recomputes every sum, split, and residual. The model never owns a number.
4. **Evidence completeness** — a proposal with no citable evidence rows cannot be auto-resolved.
5. **Materiality + policy check** — see §10.
6. **Failure mode:** a guardrail rejection does not crash and does not silently drop the case. It downgrades the case to `queued` with `exception_type` set and logs *why*. Degradation is always toward human review.

### H5 — Scheduler harness (continuous close)
APScheduler runs the pipeline on an interval (demo: every 60s; production framing: nightly).
This is what makes "continuous close" real rather than a slide: the close-readiness number moves
on its own between demo beats. Kept because it costs ~20 lines and it visibly animates the dashboard.

### H6 — Evaluation harness
See §11. Golden dataset + scorecard + CI regression gate.

### H7 — Chaos / failure-injection harness
`--chaos` flag injects exactly **three** failures — the three the demo actually shows:
a **duplicated bank file**, a **stale GSTR-2B extract**, and a **500 from the LLM provider**.
**Purpose:** the requirements explicitly reward "reliability beyond the happy path." This is how we
show it in 15 seconds instead of claiming it on a slide. Expected behaviour under chaos: zero
duplicate side effects, zero silent auto-resolutions, cases degrade to `queued`.

### H8 — Notification harness
Sinks: **console + file by default**, with a Slack-webhook sink behind the same interface if there's
time. Vendor emails and controller alerts are **drafted always, sent only after approval** — the
approval gate is the point, not the delivery mechanism. Nothing leaves the machine during the demo.

### H9 — Observability harness → **Neatlogs** (§6)
### H10 — Model router harness → **TensorMux** (§7)
### H11 — Audit & evidence-pack harness (§13)

---

## 5. AO (Agent Orchestrator) — mandatory, 25% of score

AO is not a runtime dependency of ReconcileOS. It is the **development harness** — and the rules
say usage must be demonstrable and is worth a quarter of the score. Treat it as a first-class
deliverable, not a checkbox.

### How we use it
- **`.ao/` in the repo root**, committed on day one:
  - `.ao/orchestrator-rules.md` — task decomposition, boundary enforcement, dedup, dependency detection, evidence-before-integration, *reject fabricated eval numbers*, Track-2 scope compliance.
  - `.ao/worker-rules.md` — worker scope limits, mandatory tests per unit, no cross-module edits, no credentials in task descriptions.
  - `.ao/tasks/` — one file per decomposed task, so the decomposition itself is in git history.
- **Parallel workers in isolated worktrees**, one PR each. Natural fault lines in this codebase:
  `adapters/` · `engine/` · `policy/` · `harness/` · `api/` · `ui/` · `evals/` · `seed/`.
  These modules genuinely don't share files, which is exactly what makes parallel agents work here.
- **AO handles CI fixes and merge conflicts** on the worker PRs.
- **Orchestrator gates merges** on: tests pass, eval scorecard not regressed, audit invariants hold.

### Evidence we produce for the judges
| Artifact | Where |
|---|---|
| `.ao/` rules + task files | repo root, committed first |
| `docs/AO-SESSIONS.md` — session count, task→PR→commit table, screenshots of the AO dashboard | repo |
| Commit trailer `AO-Session: <id>` on worker commits | git log |
| One PR per AO worker, visible parallel branches | GitHub |
| ~20s of the demo video showing the live AO dashboard mid-run | demo |

> **Rule to hold the line on:** if a module was written outside AO, say so. Fabricated AO evidence
> is a disqualification risk and the rules state judges may verify commit logs.

---

## 6. Neatlogs — runtime observability & failure analysis

```python
import neatlogs
neatlogs.init(api_key=os.environ["NEATLOGS_API_KEY"], tags=["reconcileos", RUN_ID])

@neatlogs.span(kind="WORKFLOW")
def run_reconciliation(period: str) -> RunResult: ...
```

`init()` is called in `app/main.py` **before** any LLM client import (auto-instrumentation patches
at import time).

### What we trace
- One **WORKFLOW** span per pipeline run, tagged `run_id`, `period`, `policy_version`.
- One **child span per tool call** (H2) with tier, inputs hash, duration, and outcome.
- One **span per LLM call**: prompt template id, model, tokens in/out, latency, retry count.
- Guardrail rejections are traced as explicit **error events**, with the rejected payload — so a
  hallucinated invoice ID is visible, not buried.

### The integration that matters
**`neatlogs_trace_id` is stored on `ReconciliationCase` and on every `AuditEvent`.**
In the UI, each case detail has a *"View agent reasoning"* link straight into the Neatlogs trace.
That closes the loop the judges care about: the audit trail doesn't just say *what* was decided,
it links to *the actual reasoning that produced it.*

### Failure analysis loop
Traces from the eval run (§11) are grouped by `exception_type` and failure mode in Neatlogs;
the top recurring failure becomes the next AO task. That cycle — trace → failure cluster → fix →
re-score — is the "evaluation loop demonstrating improvement" the requirements ask for.

---

## 7. TensorMux — inference routing & cost metering

OpenAI-compatible endpoint, so it drops in behind one base URL:

```python
client = OpenAI(base_url=os.environ["TENSORMUX_BASE_URL"],
                api_key=os.environ["TENSORMUX_API_KEY"])
```

### Routing policy (`config/models.yaml`)

| Task | Tier | Why |
|---|---|---|
| Merchant descriptor disambiguation | small/fast model | High volume, low stakes, shortlist already constrained |
| Exception classification into §9 taxonomy | small/fast model | Closed label set |
| Cash-application shortlist selection | reasoning model | Genuinely ambiguous, materially consequential |
| Vendor-correction email drafting | reasoning model | Human-facing text |
| Close commentary from validated facts | reasoning model | Narrative over already-verified numbers |

- **Fallback chain** — if the primary model errors or times out, route to the secondary; if both
  fail, the case degrades to `queued`. The pipeline never dies on an LLM outage.
- **Cost metering** — per-call tokens and cost land on the case (`token_cost_usd`), aggregated into
  the KPI **"₹ / USD cost per exception resolved"** on the dashboard. That is a real, defensible
  efficiency number, and it drops between Run 1 and Run 2 as learned rules displace LLM calls.
- **Deterministic-first is a cost strategy, not just an accuracy one.** The dashboard shows
  `% of cases resolved with zero LLM calls`.

---

## 8. Dodo Payments — a live third-party financial feed

The original spec's inputs are all CSVs. Dodo test mode gives us **one genuinely live, external,
event-driven source** — which makes the demo materially more credible and satisfies "genuine tool usage."

**Scope: shallow and deliberate — roughly two hours of work.**

### Integration
- **Outbound:** a small seed script creates test-mode products, a customer, and a handful of
  one-time payments matching the demo invoices.
- **Inbound:** `POST /webhooks/dodo` receives `payment.succeeded` (and ignores everything else).
  - **HMAC-SHA256 verification** using the `webhook-id` / `webhook-timestamp` / `webhook-signature`
    headers. (Note: this is *signature* verification, not user auth — it stays.)
  - Handler is **idempotent on `webhook-id`** via H3; replayed webhooks are no-ops.
- Each verified event becomes a `FinancialTransaction` with `source=dodo`, `external_id=payment_id`,
  and flows into **cash application (Workflow 2)** exactly like a bank line. No new engine.

### The one derived exception
**Gross vs net.** The customer paid ₹30,000; the processor payout is ₹29,115 after fees →
`PROCESSOR_FEE_DIFFERENCE`, resolved with a fee explanation rather than reported as a false
mismatch. One exception type, one code path, and it proves the agent understands that *not every
difference is an error.*

**Explicitly not built:** subscriptions, refund reversals, dispute holds, settlement-timing logic.
The data model supports them; the prototype doesn't spend hours on them.

Test mode only. Live keys are never used; the `.env.example` ships with `DODO_MODE=test` and the
server refuses to boot in `live` mode.

---

## 9. Exception taxonomy

Explicit types make the agent testable, demoable, and gradeable.

**Card:** `UNKNOWN_MERCHANT` · `AMBIGUOUS_MERCHANT` · `CATEGORY_UNCERTAIN` · `DUPLICATE_CARD_TRANSACTION`
**Cash application:** `NO_INVOICE_MATCH` · `MULTIPLE_PLAUSIBLE_MATCHES` · `ONE_TO_MANY_PAYMENT` · `PARTIAL_PAYMENT` · `OVERPAYMENT` · `UNDERPAYMENT` · `UNKNOWN_PAYER`
**GST:** `MISSING_IN_2B` · `MISSING_IN_ERP` · `GSTIN_MISMATCH` · `INVOICE_NUMBER_MISMATCH` · `DATE_MISMATCH` · `TAXABLE_VALUE_MISMATCH` · `TAX_AMOUNT_MISMATCH` · `DUPLICATE_INVOICE`
**Processor (from Dodo):** `PROCESSOR_FEE_DIFFERENCE`
**Cross-cutting:** `STALE_SOURCE_DATA`
**Close (seeded status row only, not engine-produced):** `OPS_ERP_MISSING_RECORD` · `INTERCOMPANY_DIFFERENCE`

---

## 10. Policy engine — configuration, not code

`config/policies.yaml`, versioned, and the active `policy_version` is stamped on every case and
audit event so a decision can always be read against the rules that were live at the time.

```yaml
version: v1
materiality:
  auto_resolve_max_amount: 25000       # INR
  controller_approval_above: 100000
freshness:
  max_source_age_hours: 36             # else STALE_SOURCE_DATA, block auto-actions
thresholds:
  auto_resolve_min_confidence: 0.95
  queue_with_recommendation_min: 0.60
rules:
  - if: match_type == exact_invoice_reference and amount_diff == 0 and customer_unique
    then: auto_apply
  - if: workflow == gst and abs(tax_diff) > 0
    then: human_review
  - if: card_category in ["Unusual", "Restricted"]
    then: human_review
  - if: journal.is_period_closing_adjustment
    then: controller_approval
  - if: counterparty.never_auto
    then: human_review
  - if: exception_type == INTERCOMPANY_DIFFERENCE
    then: human_review and blocks_close
```

Decision matrix:

| Confidence / risk | Default action |
|---|---|
| High confidence, low materiality | Auto-resolve, log, no human |
| High confidence, material | Propose + require approval |
| Medium | Queue with a recommended answer + evidence |
| Low | Queue with ranked alternatives, no default selected |
| Policy-blocked | Mandatory human, regardless of confidence |

**Invariant:** confidence alone never authorizes an action. Policy always gets the last word.

---

## 11. Evaluation harness — measurable results with evidence

Submission requires "measurable results or improvements with evidence," and fabricated results are
prohibited. So the numbers come from a committed golden dataset and a reproducible command.

### Golden dataset — `evals/golden/` (~400 records, ground truth labelled)

| Bucket | Count |
|---|---|
| Clean deterministic matches | 240 |
| Merchant alias variants (incl. 3 Starbucks + 2 Uber forms) | 40 |
| 1:many cash bundles | 20 |
| Partial / over / under payments | 20 |
| Unknown payer — must stay unapplied | 10 |
| GST exact matches | 30 |
| GST mismatches (tax, taxable, number-format, missing-in-2B, duplicate) | 30 |
| Processor fee differences (Dodo) | 5 |
| Duplicates / stale / malformed (chaos) | 5 |

Labelling 400 records is the single biggest non-code task in the plan. It is generated by
`seed/generate.py` **with ground truth emitted alongside the data**, then spot-audited by hand —
not hand-labelled row by row, and not back-filled from the agent's own output. That distinction is
what keeps the results honest.

### Metrics — `python -m evals.run` → `evals/reports/scorecard.md`
1. Match accuracy = `correct / matchable`
2. Precision & recall **per exception type**
3. **Unsafe auto-resolution rate** — auto-resolved cases that ground truth says were wrong. **Target: 0.** This is the safety metric; a non-zero value fails the CI gate.
4. Human-review rate (should be *low but non-zero* — zero means the agent is overconfident)
5. Evidence completeness = `% of decisions with ≥1 citable evidence row`
6. Hallucination rejections caught by H4 (should be >0 under chaos — it proves the guardrail fires)
7. Cost per resolved case (TensorMux) and `% resolved with zero LLM calls`
8. Mean latency per case
9. Close-readiness delta

### The learning experiment — Run 1 vs Run 2 (the headline number)
```
Run 1 (cold, no learned rules)
  400 records · 312 deterministic · 58 scored · 30 human exceptions

Human confirms 12 recurring patterns → 12 scoped rules written to memory

Run 2 (same 400 records + a fresh statement with new-but-similar descriptors)
  400 records · 347 deterministic/rule · 39 scored · 14 human exceptions

Human investigation queue reduced 53% · unsafe auto-resolutions: 0 · cost/case down 41%
```
The second half of that line matters as much as the first: **learning must not buy accuracy with safety.**
The eval asserts both.

### CI gate
Merges are blocked (by the AO orchestrator, §5) if unsafe-auto-resolve > 0 or if match accuracy
regresses more than 1 point against the committed baseline.

---

## 12. API + UI surface (no auth)

### REST — FastAPI, localhost

```
POST /ingest/{source}          multipart file upload
POST /webhooks/dodo            HMAC-verified processor events
POST /run                      trigger a reconciliation run  → { run_id, neatlogs_trace_id }
GET  /close-readiness?period=  dashboard payload
GET  /cases?status=&workflow=  exception queue
GET  /cases/{case_id}          evidence, alternatives, trace link, audit timeline
POST /cases/{case_id}/decision { action, allocations?, comment?, create_rule? }
GET  /rules                    learned rules
POST /rules/{id}/disable       kill a bad rule
GET  /audit?case_id=           append-only event stream
GET  /audit/verify             re-walks the hash chain → { ok, broken_at }
GET  /cases/{id}/evidence-pack ZIP export
GET  /metrics                  KPIs incl. cost/case, auto-resolve %, LLM-free %
POST /admin/reset              reload seed data (demo takes)
```

`X-Actor-Id` header names the human on audit events. Absent → `finance_user_01`. That is the entire
identity story, by design.

### UI — 5 screens
1. **Close Readiness** — overall %, per-workflow bars, blockers, "today's high-impact actions"
2. **Exception Queue** — sortable by financial impact; each row: what the agent thinks, confidence, impact
3. **Case Detail** — evidence list, ranked alternatives, arithmetic shown, **Approve / Edit split / Reject / Leave unapplied**, "View agent reasoning →" (Neatlogs)
4. **Rules Learned** — pattern, scope, source case, use count, disable toggle
5. **Audit Timeline** — every state transition, hash-chain status badge, evidence-pack download

---

## 13. Audit, evidence, and trust (what replaces auth)

We removed the login wall, so trust has to come from the ledger instead. It does:

- **Append-only.** No UPDATE, no DELETE on `audit_events`. Corrections are new reversal events.
- **Hash-chained.** `this_hash = sha256(prev_hash | seq | payload)`. `GET /audit/verify` walks the
  chain and reports the first break. Tampering with history is detectable without any access control.
- **Provenance on everything.** `inputs_hash`, `source_file_id`, `policy_version`, `model_version`,
  `rule_ids_used`, `neatlogs_trace_id` on each case.
- **Evidence pack.** Per case: source rows (both sides), candidate set, scores, policy evaluated,
  the human decision, resulting rule, and the trace link — as a ZIP an auditor can be handed.
- **Reversibility.** Any resolved case can be reversed; the reversal is an event, the original stands.

> An auditor six months later asks *"why was this ₹30,000 allocated to these three invoices?"* and
> gets a complete answer without needing the original operator's memory. That is the actual product.

---

## 14. Failure modes and controls

| # | Risk | Control |
|---|---|---|
| 1 | Two similar merchants/vendors merged | Never auto-resolve on name similarity alone when material (H4 + policy) |
| 2 | Combinatorial explosion in cash application | Pre-filter by customer, open status, currency, date window; cap bundle size at 4; cap candidate set |
| 3 | System forces a perfect match | Residual cash / residual invoice balance are first-class, `compute_residual` is deterministic |
| 4 | One bad human approval poisons future runs | Rules are scoped, versioned, visible, use-counted, expiring, and one-click disable-able |
| 5 | LLM invents a record | H4 existence check against SQLite; candidate IDs may only come from tool output |
| 6 | Stale source data | Freshness stamps + policy block → `STALE_SOURCE_DATA` |
| 7 | Tax/compliance overreach | GST module reconciles and classifies evidence; eligibility judgments stay approval-gated |
| 8 | Retry causes duplicate posting or duplicate email | H3 idempotency keys + `ActionState` + append-only audit |
| 9 | LLM provider outage mid-demo | TensorMux fallback chain; then degrade to `queued`, never crash |
| 10 | Same file uploaded twice | H1 file fingerprint → no-op |
| 11 | Guardrail rejects a valid case | Degrades to human review, never to silent auto-resolve — the failure direction is always safe |

---

## 15. Three-minute demo script

The narrative is **one hero case + one learning proof + one reliability proof.** Nothing else.

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:20 | **Problem** | Close Readiness at **71%**, four workflows red, ₹4.2L of unresolved impact. *"Finance keeps comparing systems that describe the same money differently."* |
| 0:20–1:00 | **Hero case — cash application** | ₹30,000 from XYZ Retail, reference `SERVICES JUNE`. Agent proposes INV-101 + 102 + 103 at 0.87 confidence with four evidence lines and two ranked alternatives. **Approve.** Audit event appears; a bundle rule is written. |
| 1:00–1:25 | **GST exception** | INV-101: ERP ₹1,800 vs GSTR-2B ₹1,600 → `TAX_AMOUNT_MISMATCH`, 0.99. Agent drafts the vendor correction email. Human approves *sending* — showing the reasoning/action permission split. |
| 1:25–1:50 | **Learning + Dodo** | Upload a fresh card statement with `SBX*COFFEE 0811` → auto-resolves from the rule learned earlier, **zero LLM calls**. A live Dodo test payment fires a webhook and lands in the queue mid-demo as a `PROCESSOR_FEE_DIFFERENCE`. |
| 1:50–2:15 | **Reliability** | Hit `--chaos`, three injections: re-upload a file (no-op), stale GSTR-2B (blocked, not guessed), forced LLM 500 (falls back, then queues). **Zero duplicate actions.** Then `GET /audit/verify` → chain OK. |
| 2:15–2:40 | **Measurable result + AO** | Scorecard: exception queue **−53%**, unsafe auto-resolutions **0**, cost/case **−41%**, readiness **71% → 89%**. Cut to the **AO dashboard** showing parallel workers and session count. |
| 2:40–3:00 | **Close** | *"The human still owns judgment. The agent owns the investigation, the evidence, the memory, and the proof."* Neatlogs trace link clicked from an audit row. |

Every number spoken in the video comes from `evals/reports/scorecard.md`, which is committed and reproducible.

---

## 16. Repository layout

```
syndicateHackathon/
├── .ao/
│   ├── orchestrator-rules.md
│   ├── worker-rules.md
│   └── tasks/
├── app/
│   ├── main.py                 # FastAPI; neatlogs.init() first
│   ├── adapters/               # bank, card, ar, purchase, gstr2b, dodo
│   ├── models/                 # Pydantic + SQLite schema
│   ├── engine/                 # normalize, candidates, scoring, subset-sum, gst
│   ├── policy/                 # policies.yaml loader + evaluator
│   ├── memory/                 # learned rules
│   ├── harness/                # ingestion, tools, idempotency, guardrails,
│   │                           # scheduler, evals, chaos, notify, tracing,
│   │                           # modelrouter, audit
│   └── api/                    # routes
├── ui/                         # Vite + React + Tailwind, 5 screens
├── evals/
│   ├── golden/                 # labelled dataset
│   ├── run.py
│   └── reports/scorecard.md
├── seed/                       # dataset generator + Dodo test-mode seeder
├── config/                     # policies.yaml, models.yaml, adapters/*.yaml
├── docs/
│   ├── AO-SESSIONS.md
│   ├── DEMO-SCRIPT.md
│   └── Track-2-Original-Architecture.md
├── ARCHITECTURE.md
├── README.md
└── .env.example
```

### Environment

```bash
NEATLOGS_API_KEY=
TENSORMUX_BASE_URL=
TENSORMUX_API_KEY=
TENSORMUX_MODEL_FAST=
TENSORMUX_MODEL_REASONING=
DODO_API_KEY=
DODO_WEBHOOK_SECRET=
DODO_MODE=test          # server refuses to start on "live"
DB_PATH=./reconcileos.db
POLICY_VERSION=v1
```

No auth variables. There is nothing to log into.

---

## 17. Build plan

### Critical path — first 30 hours (must ship, in this order)
1. SQLite schema + Pydantic models + append-only hash-chained audit *(nothing else works without this)*
2. CSV adapters + H1 ingestion + seed dataset generator
3. Deterministic matching + entity normalization (card + cash)
4. Policy engine + confidence + exception taxonomy
5. Exception queue API + case detail + decision endpoint
6. Rule memory + the Run 1 → Run 2 learning loop
7. GST reconciliation module
8. Close-readiness computation + dashboard UI (incl. the seeded Ops↔ERP↔Bank status row)
9. Neatlogs tracing + trace-id linkage into cases and audit
10. TensorMux router + fallback + cost metering
11. Eval harness + scorecard
12. Dodo webhook ingestion
13. Chaos harness + `audit/verify`
14. Demo dataset polish, script rehearsal, video

**Cut line if time runs out (in this order):** the Slack notification sink → the scheduler (fall back
to a manual Run button) → the evidence-pack ZIP (show JSON instead) → the Rules Learned screen
(show rules in the case detail instead). **Never cut** the audit chain, the guardrails, the eval
scorecard, or AO evidence — those are the graded parts.

### Four-week track (if the presentation window is a month)
- **W1** — items 1–6, `.ao/` rules in place from commit one, AO workers on adapters/engine/api in parallel
- **W2** — items 7–11; first full scorecard baseline committed
- **W3** — items 12–14; chaos hardening; failure-cluster analysis in Neatlogs → fix cycle → re-score
- **W4** — depth over surface: richer GST exception reasons, accrual + intercompany cases, evidence-pack polish, demo rehearsal, video, X/LinkedIn post

---

## 18. How this maps to the judging rubric

| Criterion | Weight | Where it's earned |
|---|---|---|
| **AO Usage & Build Process** | 25% | §5 — `.ao/` rules committed first, parallel worktree PRs, `AO-SESSIONS.md`, commit trailers, AO dashboard on camera |
| **Technical Execution & Reliability** | 25% | §4 harnesses, §11 eval gate with unsafe-auto-resolve = 0, §13 hash-chained audit, §14 controls, chaos demo |
| **Track Fit & Real-World Value** | 25% | Four genuine Office-of-the-CFO workflows, exception taxonomy, human review gates, evidence packs, close readiness |
| **Demo & Usability** | 15% | §15 — one hero case, one learning proof, one reliability proof, in 3 minutes |
| **Innovation** | 10% | Reconciliation as a reusable operating layer; audit events that link to the agent's own reasoning trace; learning that is measured against a safety metric, not just an accuracy one |

---

## 19. Scope discipline

**Must ship:** canonical store · card normalization · cash matching incl. 1:many · GST reconciliation ·
seeded close status row · exception queue · confidence + evidence · approve/edit/reject/defer ·
rule memory · hash-chained audit · close-readiness dashboard · Neatlogs · TensorMux ·
Dodo webhook (shallow) · chaos harness · eval scorecard · AO evidence

**Stretch:** real vendor email send · Ops↔ERP↔Bank as a real matching engine · live ERP/bank
connectors · accrual + FX depth · automatic journal generation · remittance PDF extraction

**Do not build:** authentication of any kind · 2FA · RBAC · multi-tenancy · replay harness ·
Dodo subscriptions/disputes/refunds · general-ledger replacement · tax filing engine · payroll ·
a generic autonomous-CFO chatbot · UI polish beyond legibility

> **The standing rule for this build:** if a feature cannot appear in the 3-minute video *or* in
> `evals/reports/scorecard.md`, it does not get built during the hackathon. It goes in this list.

---

*One agent. One loop. Resolve what is certain, escalate what is not, remember the judgment, prove what happened.*
