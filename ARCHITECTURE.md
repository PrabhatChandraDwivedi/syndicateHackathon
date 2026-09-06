# ReconcileOS — Final Architecture

**Autonomous Finance Reconciliation & Close Agent**
**Syndicate by Maximor · Track 2 — Autonomous Office of the CFO**

**Status:** Final, build-ready. Supersedes `docs/Track-2-Original-Architecture.md` (kept for reference).

> ### ⏱ Ten hours · ~45 parallel agents via AO
> The build window is **10 hours**. Capacity is not the constraint — we can run 40–50 coding agents
> in parallel through Agent Orchestrator. **Collision is the constraint.** Every feature in this
> document ships; the plan in §17 is engineered so that no two agents ever touch the same file, and
> all contracts are frozen before fan-out. Read §17 before writing any code.

---

## 0. What changed from the original spec, and why

The original spec (`docs/Track-2-Original-Architecture.md`) is a good *product* document but an
under-specified *engineering* document. A parallel spec (AgentLedger) proposed a TypeScript/Next.js/
Supabase stack with Supabase Auth, RBAC, Upstash Redis, and Vercel. Both are trimmed here.

### Removed — deliberately, not by accident

| Removed | Why |
|---|---|
| Login / signup / sessions | Zero judging weight. Single-operator demo app. |
| 2FA / MFA | Same. Costs hours, earns nothing. |
| Supabase Auth, RBAC, reviewer roles | Replaced by a single `actor_id` field on every audit event. Role separation is *modelled in data*, not enforced by a login wall. |
| Multi-tenancy | Single org (`abc_software`). `entity_id` exists in the schema so multi-tenancy is a later migration, not a rewrite. |
| Upstash Redis | SQLite handles idempotency keys and locks at demo scale. One less hosted dependency to fail on stage. |
| Vercel / managed hosting | We run our own server (`uvicorn`). Fully local demo = no network risk during the video. |
| Kafka / RabbitMQ / K8s / microservices | An in-process job queue backed by a SQLite `outbox` table is sufficient and is *visible* in the audit trail. |
| Vector DB / embeddings | Merchant and entity resolution is solved better and more explainably by normalization + RapidFuzz + a learned alias table. |
| Live GST portal / live bank / live ERP connectors | Adapters sit behind an interface; inputs are CSV/JSON + Dodo test-mode webhooks. |
| Full GL replacement, tax filing engine, payroll | Out of Track 2's demonstrable scope. |

Everything else from the original spec **ships**. Nothing was cut for time — see §17.

### Added — the harness layer

The original doc described *what the agent does*. It barely described *what the agent runs on*.
Sections 4–13 define **twelve harnesses** plus the four sponsor integrations (**AO, Neatlogs,
TensorMux, Dodo Payments**). These are where "Technical Execution & Reliability" (25%) and
"AO Usage & Build Process" (25%) — half the total score — are actually won.

---

## 1. One-paragraph product statement

Finance teams spend their month asking the same question in four costumes: *two systems describe
the same money differently — which records are the same event, and what do I do about the ones
that aren't?* ReconcileOS is one agent with one operating loop that ingests both sides, normalizes
identities, matches deterministically first and probabilistically second, auto-resolves only what
policy says is safe, escalates the rest to a human with evidence and alternatives, turns each human
decision into a scoped reusable rule, and writes a hash-chained audit event for every state change.
The output is a continuously-improving **close-readiness** number instead of a month-end fire drill.

**All four workflows are built end-to-end** (same engine, different record sets):

| # | Workflow | Set A | Set B | Question |
|---|---|---|---|---|
| 1 | Card merchant normalization | Card transactions | Merchant master + GL categories | Who is this merchant, how is it classified? |
| 2 | Cash application | Incoming bank / Dodo payments | Open AR invoices | Which invoice(s) did this cash settle? |
| 3 | Ops ↔ ERP ↔ Bank close | Ops/sales export | ERP + bank | Do the systems agree, what blocks close? |
| 4 | GST purchase reconciliation | Purchase register | GSTR-2B | Which invoices are supported / missing / mismatched? |

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
      S6[Ops / Sales export]
      S7["Dodo Payments<br/>test-mode webhooks"]
    end

    subgraph HARNESS["Harness layer"]
      ING[H1 Ingestion + freshness]
      TOOL[H2 Typed tool registry]
      IDEM[H3 Idempotency + action state]
      GUARD[H4 Guardrails / validators]
      SCHED[H5 Scheduler]
      REPLAY[H6 Replay]
      EVAL[H7 Eval harness]
      CHAOS[H8 Chaos injection]
      NOTIF[H9 Notifications]
      OBS[H10 Neatlogs tracing]
      LLM[H11 TensorMux model router]
      AUD[H12 Hash-chained audit + evidence pack]
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
    REPLAY -.reruns.- ENG
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
| Dev orchestration | **AO** | See §5 and §17. Mandatory. |

**No auth of any kind.** The server binds to localhost. `actor_id` is set by a header
(`X-Actor-Id`, defaults to `finance_user_01`) purely so the audit log has an author.

---

## 3. Canonical data model

**This is the single most important artifact in the build.** ~45 agents code against it
simultaneously, so it is frozen in Wave 0 (§17) and any change after that requires an explicit
contract-amendment task. Fields marked **new** are harness additions to the original spec.

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
OpsRecord:     ops_id, order_ref, date, gross_amount, fees, net_amount,
               channel, raw_payload                        # new: Workflow 3

ReconciliationCase:
  case_id, workflow, source_ids[], candidate_target_ids[]
  status: proposed|auto_resolved|queued|approved|rejected|deferred|reversed
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

RunRecord:                                # new: replay + eval anchor
  run_id, started_at, policy_version, rule_snapshot_id,
  source_file_ids[], neatlogs_trace_id, metrics_json
```

---

## 4. The harness layer

Twelve harnesses. Each is a module under `app/harness/`, each is owned by exactly one agent in
Wave 1, each is independently testable, and each produces something a judge can see.

### H1 — Ingestion harness
- Adapter per source; the engine never sees a raw CSV column name.
- **Column sniffing** with a per-adapter mapping file, so a slightly-different export doesn't crash the demo.
- **File fingerprinting** (`sha256`) → re-uploading the same file is a no-op, not a duplicate.
- **Freshness stamps**: every `source_file` carries `as_of`. Policy blocks auto-actions when data is stale (§10, `STALE_SOURCE_DATA`).
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
ingest_purchase_register · ingest_gstr2b · ingest_ops_export
ingest_dodo_webhook

normalize_entity · resolve_merchant · find_customer_candidates
find_invoice_candidates · score_invoice_allocation · match_gst_invoice
match_ops_to_erp · match_erp_to_bank · detect_duplicate_transaction
compute_residual · classify_reconciliation_exception · explain_case

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

### H4 — Guardrail harness (the anti-hallucination layer)
Runs on every LLM output before it can become a proposal:
1. **Schema validation** — structured output or reject.
2. **Existence check** — every referenced `invoice_id` / `case_id` / `merchant_id` must exist in SQLite. A model-invented invoice is rejected, not surfaced.
3. **Arithmetic verifier** — Python recomputes every sum, split, and residual. The model never owns a number.
4. **Evidence completeness** — a proposal with no citable evidence rows cannot be auto-resolved.
5. **Materiality + policy check** — see §10.
6. **Failure direction:** a guardrail rejection never crashes and never silently drops a case. It downgrades the case to `queued` with `exception_type` set and logs *why*. Degradation is always toward human review.

### H5 — Scheduler harness (continuous close)
APScheduler runs the pipeline on an interval (demo: every 60s; production framing: nightly).
This is what makes "continuous close" real rather than a slide: the close-readiness number moves
on its own between demo beats.

### H6 — Replay harness
`python -m app.replay --run-id <id>` re-executes a historical run from stored raw payloads at the
recorded `policy_version` and rule snapshot. Answers the auditor's question — *"why did the system
do this in September?"* — deterministically, months later.

### H7 — Evaluation harness
See §11. Golden dataset + scorecard + regression gate.

### H8 — Chaos / failure-injection harness
`--chaos` injects, on demand: a **stale GSTR-2B extract**, a **duplicated bank file**, **malformed
rows**, a **truncated invoice export**, a **500 from the LLM provider**, and a **mid-run crash**.
**Purpose:** the requirements explicitly reward "reliability beyond the happy path." This proves it
in 15 seconds of video instead of claiming it on a slide. Expected behaviour under chaos: zero
duplicate side effects, zero silent auto-resolutions, cases degrade to `queued`, audit chain intact.

### H9 — Notification harness
Sinks: console, file, Slack webhook, SMTP — all behind one interface. Vendor emails and controller
alerts are **drafted always, sent only after approval**. The demo runs console + file so nothing
leaves the machine, with the Slack sink shown as configured-but-gated.

### H10 — Observability harness → **Neatlogs** (§6)
### H11 — Model router harness → **TensorMux** (§7)
### H12 — Audit & evidence-pack harness (§13)

---

## 5. AO (Agent Orchestrator) — mandatory, 25% of score

AO is not a runtime dependency of ReconcileOS. It is the **development harness** — and with ~45
agents building this system in 10 hours, it is also the only reason the build is feasible at all.
That makes AO usage genuinely load-bearing here rather than a checkbox, which is exactly the story
the judges are looking for.

### How we use it
- **`.ao/` in the repo root, committed in the first 30 minutes**, before any feature code:
  - `.ao/orchestrator-rules.md` — task decomposition, boundary enforcement, dedup, dependency detection, evidence-before-integration, *reject fabricated eval numbers*, Track-2 scope compliance.
  - `.ao/worker-rules.md` — **file-ownership boundaries are absolute**; a worker that needs a file it doesn't own raises a dependency instead of editing it. Mandatory tests per unit. No credentials in task descriptions.
  - `.ao/tasks/` — one file per task from §17's breakdown, so the decomposition itself is in git history.
- **~45 workers in isolated worktrees, one PR each**, fanned out in waves (§17).
- **AO handles CI fixes and merge conflicts** on worker PRs — with disjoint file ownership there should be almost none, which is the whole design.
- **Orchestrator gates merges** on: tests pass, contract unchanged, eval scorecard not regressed, audit invariants hold.

### Evidence we produce for the judges
| Artifact | Where |
|---|---|
| `.ao/` rules + ~45 task files | repo root, committed first |
| `docs/AO-SESSIONS.md` — session count, task→PR→commit table, dashboard screenshots | repo |
| Commit trailer `AO-Session: <id>` on worker commits | git log |
| ~45 PRs / branches showing genuine parallel execution | GitHub |
| ~20s of the demo video showing the live AO dashboard mid-run | demo |

> **Hold the line:** if a module was written outside AO, say so. Fabricated AO evidence is a
> disqualification risk and the rules state judges may verify commit logs.

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
- Guardrail rejections traced as explicit **error events** with the rejected payload — so a hallucinated invoice ID is visible, not buried.

### The integration that matters
**`neatlogs_trace_id` is stored on `ReconciliationCase`, `RunRecord`, and every `AuditEvent`.**
Each case detail page has a *"View agent reasoning →"* link straight into the Neatlogs trace.
That closes the loop the judges care about: the audit trail doesn't just say *what* was decided,
it links to *the actual reasoning that produced it.*

### Failure analysis loop
Traces from the eval run (§11) are grouped by `exception_type` and failure mode in Neatlogs; the
top recurring failure becomes the next AO task. That cycle — trace → failure cluster → fix →
re-score — is the "evaluation loop demonstrating improvement" the requirements ask for, and with
this many agents we can run it more than once.

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

- **Fallback chain** — if the primary model errors or times out, route to the secondary; if both fail, the case degrades to `queued`. The pipeline never dies on an LLM outage.
- **Cost metering** — per-call tokens and cost land on the case (`token_cost_usd`), aggregated into the KPI **"cost per exception resolved."** That is a real, defensible efficiency number, and it drops between Run 1 and Run 2 as learned rules displace LLM calls.
- **Deterministic-first is a cost strategy, not just an accuracy one.** The dashboard shows `% of cases resolved with zero LLM calls`.

---

## 8. Dodo Payments — a live third-party financial feed

The original spec's inputs are all CSVs. Dodo test mode gives us **one genuinely live, external,
event-driven source** — which makes the demo materially more credible and satisfies "genuine tool usage."

### Integration
- **Outbound:** a seed script creates test-mode products, customers, one-time payments, a subscription, and a refund — the kind of AR activity a SaaS company actually has.
- **Inbound:** `POST /webhooks/dodo` receives `payment.succeeded`, `payment.failed`, `refund.succeeded`, `subscription.renewed`, `dispute.opened`.
  - **HMAC-SHA256 verification** using the `webhook-id` / `webhook-timestamp` / `webhook-signature` headers. (This is *signature* verification, not user auth — it stays.)
  - Handler is **idempotent on `webhook-id`** via H3; replayed webhooks are no-ops.
- Each verified event becomes a `FinancialTransaction` with `source=dodo`, `external_id=payment_id`, and flows into **cash application (Workflow 2)** exactly like a bank line.

### Why this earns points beyond "we used a sponsor"
Payment-processor settlements produce *real* reconciliation exceptions, for free:
- **Gross vs net** — customer paid ₹30,000, payout is ₹29,115 after fees → `PROCESSOR_FEE_DIFFERENCE`, resolved with a fee explanation rather than reported as a false mismatch. Proves the agent knows *not every difference is an error*.
- **Timing** — payment succeeds on the 30th, payout lands on the 2nd → `SETTLEMENT_TIMING`, a legitimate cut-off difference the agent must *explain*, not "fix."
- **Refunds** — a refund after invoice settlement forces a `REFUND_REVERSAL` audit event, proving history is never overwritten.
- **Disputes** — `DISPUTE_HOLD` parks the receivable and blocks close, exercising the blocker path on the dashboard.

Test mode only. Live keys are never used; `.env.example` ships `DODO_MODE=test` and the server
refuses to boot in `live` mode.

---

## 9. Exception taxonomy

Explicit types make the agent testable, demoable, and gradeable.

**Card:** `UNKNOWN_MERCHANT` · `AMBIGUOUS_MERCHANT` · `CATEGORY_UNCERTAIN` · `DUPLICATE_CARD_TRANSACTION`
**Cash application:** `NO_INVOICE_MATCH` · `MULTIPLE_PLAUSIBLE_MATCHES` · `ONE_TO_MANY_PAYMENT` · `PARTIAL_PAYMENT` · `OVERPAYMENT` · `UNDERPAYMENT` · `UNKNOWN_PAYER`
**Close:** `BANK_LEDGER_DIFFERENCE` · `OPS_ERP_MISSING_RECORD` · `INTERCOMPANY_DIFFERENCE` · `ACCRUAL_REQUIRED` · `FX_REVALUATION_PENDING` · `STALE_SOURCE_DATA`
**GST:** `MISSING_IN_2B` · `MISSING_IN_ERP` · `GSTIN_MISMATCH` · `INVOICE_NUMBER_MISMATCH` · `DATE_MISMATCH` · `TAXABLE_VALUE_MISMATCH` · `TAX_AMOUNT_MISMATCH` · `DUPLICATE_INVOICE`
**Processor (from Dodo):** `PROCESSOR_FEE_DIFFERENCE` · `SETTLEMENT_TIMING` · `REFUND_REVERSAL` · `DISPUTE_HOLD`

---

## 10. Policy engine — configuration, not code

`config/policies.yaml`, versioned. The active `policy_version` is stamped on every case and audit
event so a decision can always be read against the rules that were live at the time.

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
  - if: exception_type in [DISPUTE_HOLD, INTERCOMPANY_DIFFERENCE]
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

### Golden dataset — `evals/golden/` (400 records, ground-truth labelled)

| Bucket | Count |
|---|---|
| Clean deterministic matches | 230 |
| Merchant alias variants (incl. 3 Starbucks + 2 Uber forms) | 40 |
| 1:many cash bundles | 20 |
| Partial / over / under payments | 20 |
| Unknown payer — must stay unapplied | 10 |
| GST exact matches | 30 |
| GST mismatches (tax, taxable, number-format, missing-in-2B, duplicate) | 30 |
| Ops↔ERP↔bank differences (incl. fee + timing) | 10 |
| Processor exceptions (Dodo) | 5 |
| Duplicates / stale / malformed (chaos) | 5 |

**How the labels are produced — this is the integrity question.** `seed/generate.py` builds each
record *from* a known ground truth and emits the label alongside the data. Nothing is back-filled
from the agent's own output, which would make the scorecard circular and worthless. Before the run,
a **stratified 40-record sample is read by a human** to confirm the generator's labels are correct.
That sample check is what we claim in the README — no more, no less.

### Metrics — `python -m evals.run` → `evals/reports/scorecard.md`
1. Match accuracy = `correct / matchable`
2. Precision & recall **per exception type**
3. **Unsafe auto-resolution rate** — auto-resolved cases ground truth says were wrong. **Target: 0.** The safety metric; non-zero fails the gate.
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

> ⚠️ **Those numbers are the shape we expect, not results.** They are placeholders until
> `evals/run.py` produces them at T+7:00. Whatever it prints goes in the video and on Devpost, even
> if it's less flattering. Fabricated results are an explicit disqualification risk.

The second half of that line matters as much as the first: **learning must not buy accuracy with
safety.** The eval asserts both.

### Regression gate
The AO orchestrator (§5) blocks merges if unsafe-auto-resolve > 0 or if match accuracy regresses
more than 1 point against the committed baseline.

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
GET  /runs · GET /runs/{id}    run history, for replay
GET  /metrics                  KPIs incl. cost/case, auto-resolve %, LLM-free %
POST /admin/reset              reload seed data (demo takes)
```

`X-Actor-Id` names the human on audit events. Absent → `finance_user_01`. That is the entire
identity story, by design.

**This contract is frozen at T+0:30** (§17, Wave 0) so frontend and backend agents never block each
other. Changes after that require a contract-amendment task, not a unilateral edit.

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
- **Hash-chained.** `this_hash = sha256(prev_hash | seq | payload)`. `GET /audit/verify` walks the chain and reports the first break. Tampering with history is detectable without any access control.
- **Provenance on everything.** `inputs_hash`, `source_file_id`, `policy_version`, `model_version`, `rule_ids_used`, `neatlogs_trace_id` on each case.
- **Evidence pack.** Per case: source rows (both sides), candidate set, scores, policy evaluated, human decision, resulting rule, and the trace link — a ZIP an auditor can be handed.
- **Reversibility.** Any resolved case can be reversed; the reversal is an event, the original stands.

> An auditor six months later asks *"why was this ₹30,000 allocated to these three invoices?"* and
> gets a complete answer without needing the original operator's memory. That is the actual product.

---

## 14. Failure modes and controls

| # | Risk | Control |
|---|---|---|
| 1 | Two similar merchants/vendors merged | Never auto-resolve on name similarity alone when material (H4 + policy) |
| 2 | Combinatorial explosion in cash application | Pre-filter by customer, open status, currency, date window; cap bundle size at 4; cap candidate set |
| 3 | System forces a perfect match | Residual cash / residual invoice balance are first-class; `compute_residual` is deterministic |
| 4 | One bad human approval poisons future runs | Rules are scoped, versioned, visible, use-counted, expiring, one-click disable-able |
| 5 | LLM invents a record | H4 existence check against SQLite; candidate IDs may only come from tool output |
| 6 | Stale source data | Freshness stamps + policy block → `STALE_SOURCE_DATA` |
| 7 | Tax/compliance overreach | GST module reconciles and classifies evidence; eligibility judgments stay approval-gated |
| 8 | Retry causes duplicate posting or duplicate email | H3 idempotency keys + `ActionState` + append-only audit |
| 9 | LLM provider outage mid-demo | TensorMux fallback chain; then degrade to `queued`, never crash |
| 10 | Same file uploaded twice | H1 file fingerprint → no-op |
| 11 | Guardrail rejects a valid case | Degrades to human review, never to silent auto-resolve — the failure direction is always safe |
| 12 | **45 agents collide on one file** | **Disjoint file ownership + frozen contracts (§17). The single biggest schedule risk in this build.** |

---

## 15. Three-minute demo script

The narrative is **one hero case + one learning proof + one reliability proof.** Nothing else.

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:20 | **Problem** | Close Readiness at **71%**, four workflows red, ₹4.2L of unresolved impact. *"Finance keeps comparing systems that describe the same money differently."* |
| 0:20–1:00 | **Hero case — cash application** | ₹30,000 from XYZ Retail, reference `SERVICES JUNE`. Agent proposes INV-101 + 102 + 103 at 0.87 confidence with four evidence lines and two ranked alternatives. **Approve.** Audit event appears; a bundle rule is written. |
| 1:00–1:25 | **GST exception** | INV-101: ERP ₹1,800 vs GSTR-2B ₹1,600 → `TAX_AMOUNT_MISMATCH`, 0.99. Agent drafts the vendor correction email. Human approves *sending* — showing the reasoning/action permission split. |
| 1:25–1:50 | **Learning + Dodo** | Fresh card statement with `SBX*COFFEE 0811` → auto-resolves from the rule learned earlier, **zero LLM calls**. A live Dodo test payment fires a webhook and lands in the queue mid-demo. |
| 1:50–2:15 | **Reliability** | Hit `--chaos`: re-upload a file (no-op), stale GSTR-2B (blocked, not guessed), forced LLM 500 (falls back, then queues). **Zero duplicate actions.** Then `GET /audit/verify` → chain OK. |
| 2:15–2:40 | **Measurable result + AO** | Scorecard: exception queue **−53%**, unsafe auto-resolutions **0**, cost/case **−41%**, readiness **71% → 89%**. Cut to the **AO dashboard** showing ~45 parallel workers and the session count. |
| 2:40–3:00 | **Close** | *"The human still owns judgment. The agent owns the investigation, the evidence, the memory, and the proof."* Neatlogs trace link clicked from an audit row. |

Every number spoken in the video comes from `evals/reports/scorecard.md`, which is committed and reproducible.

---

## 16. Repository layout

```
syndicateHackathon/
├── .ao/
│   ├── orchestrator-rules.md
│   ├── worker-rules.md
│   └── tasks/                  # one file per §17 task
├── app/
│   ├── main.py                 # FastAPI; neatlogs.init() first
│   ├── adapters/               # bank, card, ar, purchase, gstr2b, ops, dodo
│   ├── models/                 # Pydantic + SQLite schema  ← frozen in Wave 0
│   ├── engine/                 # normalize, merchant, cash, subsetsum, scoring,
│   │                           # gst, close, exceptions
│   ├── policy/                 # policies.yaml loader + evaluator
│   ├── memory/                 # learned rules
│   ├── harness/                # ingestion, tools, idempotency, guardrails,
│   │                           # scheduler, replay, evals, chaos, notify,
│   │                           # tracing, modelrouter, audit
│   └── api/                    # routes  ← contract frozen in Wave 0
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

## 17. Build plan — 10 hours, ~45 parallel agents

### The governing constraint

Agent capacity is effectively unlimited; **coordination is not**. Forty agents editing one codebase
produce merge conflicts faster than they produce features. Two rules make the fan-out work, and
everything below exists to enforce them:

> **Rule 1 — Disjoint ownership.** Every file has exactly one owning agent. A worker that needs a
> file it does not own raises a dependency; it never edits across the boundary.
>
> **Rule 2 — Contracts before code.** The data model (§3) and the API contract (§12) are frozen in
> Wave 0. Everything after that codes against a fixed interface, so agents never wait on each other.

Amdahl still applies: parallelism collapses build time but not *integration* time. Hence a dedicated
integration wave and standing integration agents, not a merge free-for-all at hour 8.

### Time budget

```
10:00  total
-1:30  README + AO-SESSIONS + rehearsal + record + post + Devpost   (HARD REQUIREMENT)
-1:30  integration waves (cannot be parallelised away)
-0:45  eval run + scorecard
──────
 6:15  parallel build time — but ~45× wide
```

**Code freeze at T+8:00.** Whatever runs then is the submission. A half-finished feature at T+9:00
costs the video, and the video is a required submission field.

---

### Wave 0 — Contract lock · T+0:00–0:30 · **1 agent, serial**

Nothing else may start until this merges. This is the highest-leverage 30 minutes of the build.

| ID | Deliverable |
|---|---|
| **A00** | Repo scaffold · `.ao/orchestrator-rules.md` + `.ao/worker-rules.md` **committed first** · SQLite DDL for every table in §3 · Pydantic models · `AuditEvent` hash-chain writer · OpenAPI stub for every route in §12 · `.env.example` · pytest + CI skeleton · `app/main.py` with `neatlogs.init()` at the top |

Output: a merged `main` that every subsequent agent branches from. **Then fan out.**

---

### Wave 1 — Parallel build · T+0:30–4:00 · **34 agents**

Every agent owns its files exclusively, ships unit tests, and opens one PR.

**Adapters (6)** — depend on: schema only
| ID | Owns |
|---|---|
| A01 | `adapters/bank.py` + column-mapping config |
| A02 | `adapters/card.py` |
| A03 | `adapters/ar_invoices.py` |
| A04 | `adapters/purchase_register.py` |
| A05 | `adapters/gstr2b.py` |
| A06 | `adapters/ops_export.py` |

**Harness (10)** — depend on: schema only
| ID | Owns |
|---|---|
| A07 | `harness/ingestion.py` — fingerprinting, freshness, quarantine (H1) |
| A08 | `harness/tools.py` — typed registry + permission tiers (H2) |
| A09 | `harness/idempotency.py` — keys + `ActionState` (H3) |
| A10 | `harness/guardrails.py` — schema/existence/arithmetic/evidence validators (H4) |
| A11 | `harness/scheduler.py` (H5) |
| A12 | `harness/replay.py` (H6) |
| A13 | `harness/chaos.py` — all 6 injections (H8) |
| A14 | `harness/notify.py` — console/file/Slack/SMTP sinks (H9) |
| A15 | `harness/audit.py` — append-only writer + chain verify (H12) |
| A16 | `harness/evidence_pack.py` — ZIP export (H12) |

**Engine — matching (8)** — depend on: schema only
| ID | Owns |
|---|---|
| A17 | `engine/normalize.py` — text/case/punctuation/store-suffix normalization |
| A18 | `engine/merchant.py` — alias table + RapidFuzz resolution (Workflow 1) |
| A19 | `engine/entity.py` — customer/vendor identity resolution |
| A20 | `engine/cash_candidates.py` — bounded candidate generation (Workflow 2) |
| A21 | `engine/subsetsum.py` — capped combinatorial allocation |
| A22 | `engine/scoring.py` — feature weights → confidence |
| A23 | `engine/residual.py` — partial/over/under settlement |
| A24 | `engine/duplicates.py` — duplicate transaction/invoice detection |

**Engine — GST (3)**
| ID | Owns |
|---|---|
| A25 | `engine/gst_match.py` — GSTIN/invoice/date/amount exact matching |
| A26 | `engine/gst_mismatch.py` — fuzzy invoice-number, mismatch classification |
| A27 | `engine/gst_vendor.py` — vendor grouping + correction-email drafting |

**Engine — close (3)** — Workflow 3, fully built
| ID | Owns |
|---|---|
| A28 | `engine/close_ops_erp.py` — ops↔ERP matching, missing-record detection |
| A29 | `engine/close_bank.py` — ERP↔bank, fee and timing differences |
| A30 | `engine/close_advanced.py` — intercompany, accrual, FX revaluation cases |

**Policy, memory, taxonomy (4)**
| ID | Owns |
|---|---|
| A31 | `policy/engine.py` + `config/policies.yaml` |
| A32 | `memory/rules.py` — learned rule store, scope, expiry, disable |
| A33 | `engine/exceptions.py` — full §9 taxonomy + classifier |
| A34 | `engine/explain.py` — evidence assembly + alternatives ranking |

---

### Wave 2 — Integration & interfaces · T+3:30–5:30 · **11 agents**

Starts 30 min before Wave 1 ends, against merged branches.

| ID | Owns |
|---|---|
| **I01** | **Pipeline wiring** — orchestrates ingest → normalize → match → policy → case. The one genuinely central task; give it your strongest agent |
| **I02** | **Merge shepherd** — reviews and lands Wave 1 PRs, resolves conflicts, enforces contract |
| A35 | `api/` core routes — ingest, run, metrics, admin/reset |
| A36 | `api/` case routes — queue, detail, decision, rules |
| A37 | `api/` audit routes — stream, verify, evidence-pack, runs |
| A38 | `ui/` screen 1 — Close Readiness dashboard |
| A39 | `ui/` screen 2 — Exception Queue |
| A40 | `ui/` screen 3 — Case Detail |
| A41 | `ui/` screens 4+5 — Rules Learned, Audit Timeline |
| A42 | `integrations/neatlogs.py` — spans, trace-id propagation into cases and audit |
| A43 | `integrations/tensormux.py` — router, fallback chain, cost metering |

---

### Wave 3 — Data, evals, sponsors, hardening · T+5:30–7:45 · **10 agents**

| ID | Owns |
|---|---|
| A44 | `seed/generate.py` — 400-record dataset **with ground truth emitted alongside** |
| A45 | `evals/run.py` — all 9 metrics |
| A46 | `evals/report.py` — scorecard renderer |
| A47 | `integrations/dodo.py` — client + test-mode seeder |
| A48 | `api/webhooks_dodo.py` — HMAC verify + idempotent handler |
| A49 | `engine/processor_exceptions.py` — fee, timing, refund, dispute cases |
| **I03** | **End-to-end test agent** — full run green, chaos suite green, audit chain verified |
| **I04** | **Demo data curator** — makes §15's exact cases present and visually clean |
| A50 | `README.md` — setup instructions (required submission field) |
| A51 | `docs/AO-SESSIONS.md` — session count, task→PR table, dashboard screenshots |

**T+7:00 — human runs the eval**, confirms the 12 rules, runs Run 2, commits the real scorecard.
**T+7:45 — dry-run the demo once, end to end.**

---

### Wave 4 — Freeze and ship · T+8:00–10:00 · **no code**

| Time | Work |
|---|---|
| 8:00 | 🔒 **CODE FREEZE** |
| 8:00–8:30 | Final README pass, AO-SESSIONS screenshots, architecture link |
| 8:30–9:15 | Record the demo video — budget for 3 takes |
| 9:15–10:00 | Post publicly to X or LinkedIn; submit post URL + repo + architecture to Devpost |

---

### Checkpoints — the plan's circuit breakers

| At | Test | If failing |
|---|---|---|
| **T+0:30** | Is Wave 0 merged and green? | **Do not fan out.** A broken contract multiplied by 34 agents is the one unrecoverable failure in this plan |
| **T+4:00** | Are ≥28 of 34 Wave 1 PRs merged? | Land what's green, defer the rest to stretch; I01 proceeds with stubs |
| **T+5:30** | Does one full run produce cases end-to-end? | Freeze feature work. Wave 3 agents redirect to making the existing path solid |
| **T+7:00** | Is `scorecard.md` real and committed? | Stop everything else. It is a required submission field |
| **T+7:45** | Has the demo been dry-run once? | Cut straight to freeze; ship what runs |

### If something must go — cut order

Full scope is planned, but under pressure drop in this order:
Slack/SMTP sinks → replay harness → evidence-pack ZIP → advanced close cases (intercompany/FX/accrual)
→ Dodo disputes and subscriptions → screens 4–5 folded into Case Detail.

**Never cut, at any checkpoint:** the hash-chained audit log · the guardrail layer (H4) ·
`scorecard.md` · `.ao/` evidence · the README. Three of those are explicit submission requirements
and all four are where half the score lives.

### Standing instructions for every worker agent

1. You own your files. Never edit a file you don't own — raise a dependency instead.
2. The data model and API contract are frozen. Code against them; do not amend them.
3. Ship unit tests with your module. A PR without tests does not merge.
4. Never fabricate an eval number, a metric, or a test result.
5. No credentials in code, task descriptions, or commit messages.
6. Small PRs. One module, one PR, one concern.

---

## 18. How this maps to the judging rubric

| Criterion | Weight | Where it's earned |
|---|---|---|
| **AO Usage & Build Process** | 25% | §5 + §17 — `.ao/` rules committed first, ~45 parallel worktree PRs, `AO-SESSIONS.md`, commit trailers, AO dashboard on camera. AO isn't decoration here; a 10-hour build of this size is only possible because of it |
| **Technical Execution & Reliability** | 25% | §4 harnesses, §11 eval gate with unsafe-auto-resolve = 0, §13 hash-chained audit, §14 controls, chaos demo |
| **Track Fit & Real-World Value** | 25% | Four genuine Office-of-the-CFO workflows, full exception taxonomy, human review gates, evidence packs, close readiness |
| **Demo & Usability** | 15% | §15 — one hero case, one learning proof, one reliability proof, in 3 minutes |
| **Innovation** | 10% | Reconciliation as a reusable operating layer; audit events that link to the agent's own reasoning trace; learning measured against a safety metric, not just an accuracy one |

---

## 19. Scope discipline

**Must ship:** canonical store · card normalization · cash matching incl. 1:many · GST reconciliation ·
Ops↔ERP↔Bank close matching · exception queue · confidence + evidence · approve/edit/reject/defer ·
rule memory · hash-chained audit · evidence packs · close-readiness dashboard · replay · chaos ·
Neatlogs · TensorMux · Dodo webhooks · eval scorecard · AO evidence

**Stretch:** real vendor email send · live ERP/bank connectors · richer FX depth ·
automatic journal generation · remittance PDF extraction · second failure-analysis→fix→re-score cycle

**Do not build:** authentication of any kind · 2FA · RBAC · multi-tenancy · general-ledger
replacement · tax filing engine · payroll · a generic autonomous-CFO chatbot · UI polish beyond legibility

> **The standing rule:** if a feature cannot appear in the 3-minute video *or* in
> `evals/reports/scorecard.md`, it does not get built during the hackathon.

---

*One agent. One loop. Resolve what is certain, escalate what is not, remember the judgment, prove what happened.*
