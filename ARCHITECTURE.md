# ReconcileOS — Final Architecture

**Autonomous Finance Reconciliation & Close Agent**
**Syndicate by Maximor · Track 2 — Autonomous Office of the CFO**

**Status:** Final, build-ready. Supersedes `docs/Track-2-Original-Architecture.md` (kept for reference).

> ### Built by a 68-agent orchestration tree under Agent Orchestrator
> Every feature in this document ships. **§17 is the orchestration hierarchy and task division** —
> one Main Orchestrator, eleven Sub-Orchestrators, 56 worker agents. Each worker owns a bounded
> set of files with named deliverables and named dependencies.

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
| Live GST portal / live bank / live ERP connectors | Adapters sit behind an interface; inputs are CSV and JSON exports. |
| Full GL replacement, tax filing engine, payroll | Out of Track 2's demonstrable scope. |
| **Replay harness** | The hash-chained append-only audit log already answers "why did the system do this?" Deterministic re-execution is a production feature. |
| **Live Dodo Payments webhooks** | Optional sponsor integration, not a rule and not in the rubric. It was the only sub-tree with an external blocker (account verification + a public tunnel) and a live webhook mid-recording is a demo risk for zero points. **The finance content is kept** — processor settlement differences are reconciled from a payout report instead. See §8. |

Everything else from the original spec **ships**. See §17 for how the work divides across the orchestration tree.

### Added — the harness layer

The original doc described *what the agent does*. It barely described *what the agent runs on*.
Sections 4–13 define **eleven harnesses** plus the three sponsor integrations (**AO, Neatlogs,
TensorMux**). These are where "Technical Execution & Reliability" (25%) and
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
| 2 | Cash application | Incoming bank / processor payouts | Open AR invoices | Which invoice(s) did this cash settle? |
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
      S7["Processor payout report"]
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
      LLM[H10 Model router]
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
| Inference | **OpenAI** primary, **TensorMux** fallback | Both OpenAI-compatible. Routing, fallback + cost metering, see §7. |
| Tracing | **Neatlogs** | See §6. |
| Processor feed | **Payout report CSV** | See §8. No external dependency, no tunnel, no live call during the demo. |
| Dev orchestration | **AO** | See §5 and §17. Mandatory. |

**No auth of any kind.** The server binds to localhost. `actor_id` is set by a header
(`X-Actor-Id`, defaults to `finance_user_01`) purely so the audit log has an author.

---

## 3. Canonical data model

**This is the single most important artifact in the build.** Every agent codes against it, so it is
produced first by the Main Orchestrator (§17) and treated as fixed thereafter. Fields marked **new** are harness additions to the original spec.

```python
FinancialTransaction:
  id, source: bank|corporate_card|payment_processor
  account_id, date, amount, currency
  counterparty_raw, reference_raw
  raw_payload: JSON                       # always kept — evidence
  source_file_id, ingested_at             # new: provenance
  external_id                             # new: processor payment id, for idempotency

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

RunRecord:                                # new: run history + eval anchor
  run_id, started_at, policy_version, rule_snapshot_id,
  source_file_ids[], neatlogs_trace_id, metrics_json
```

---

## 4. The harness layer

Eleven harnesses. Each is a module under `app/harness/`, each is owned by exactly one worker agent (§17),
each is independently testable, and each produces something a judge can see.

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
ingest_payout_report

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

### H6 — Evaluation harness
See §11. Golden dataset + scorecard + regression gate.

### H7 — Chaos / failure-injection harness
`--chaos` injects, on demand: a **stale GSTR-2B extract**, a **duplicated bank file**, **malformed
rows**, a **truncated invoice export**, a **500 from the LLM provider**, and a **mid-run crash**.
**Purpose:** the requirements explicitly reward "reliability beyond the happy path." This proves it
in 15 seconds of video instead of claiming it on a slide. Expected behaviour under chaos: zero
duplicate side effects, zero silent auto-resolutions, cases degrade to `queued`, audit chain intact.

### H8 — Notification harness
Sinks: console, file, Slack webhook, SMTP — all behind one interface. Vendor emails and controller
alerts are **drafted always, sent only after approval**. The demo runs console + file so nothing
leaves the machine, with the Slack sink shown as configured-but-gated.

### H9 — Observability harness → **Neatlogs** (§6)
### H10 — Model router harness → **OpenAI + TensorMux** (§7)
### H11 — Audit & evidence-pack harness (§13)

---

## 5. AO (Agent Orchestrator) — mandatory, 25% of score

AO is not a runtime dependency of ReconcileOS. It is the **development harness** — and with a 68-agent
tree building this system in 10 hours, it is also the only reason the build is feasible at all.
That makes AO usage genuinely load-bearing here rather than a checkbox, which is exactly the story
the judges are looking for.

### How we use it
- **`.ao/` in the repo root, committed in the first 30 minutes**, before any feature code:
  - `.ao/orchestrator-rules.md` — task decomposition, boundary enforcement, dedup, dependency detection, evidence-before-integration, *reject fabricated eval numbers*, Track-2 scope compliance.
  - `.ao/worker-rules.md` — **file-ownership boundaries are absolute**; a worker that needs a file it doesn't own raises a dependency instead of editing it. Mandatory tests per unit. No credentials in task descriptions.
  - `.ao/tasks/` — one file per task from §17's breakdown, so the decomposition itself is in git history.
- **56 worker agents in isolated worktrees, one PR each**, dispatched through eleven Sub-Orchestrators (§17).
- **AO handles CI fixes and merge conflicts** on worker PRs — with disjoint file ownership there should be almost none, which is the whole design.
- **Orchestrator gates merges** on: tests pass, contract unchanged, eval scorecard not regressed, audit invariants hold.

### Evidence we produce for the judges
| Artifact | Where |
|---|---|
| `.ao/` rules + 56 task files | repo root, committed first |
| `docs/AO-SESSIONS.md` — session count, task→PR→commit table, dashboard screenshots | repo |
| Commit trailer `AO-Session: <id>` on worker commits | git log |
| 56 PRs / branches showing genuine parallel execution | GitHub |
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

## 7. Model router — OpenAI primary, TensorMux fallback

Two providers, both OpenAI-compatible, behind one client interface. **OpenAI is primary**;
**TensorMux is the fallback leg** and the hackathon's inference partner.

| Role | Provider | Model | Notes |
|---|---|---|---|
| **Primary** | OpenAI | `gpt-4o-mini` (bulk), `gpt-4.1` (reasoning-heavy) | Stronger instruction-following and reliable structured output, which the guardrail layer (H4) depends on |
| **Fallback** | TensorMux | `glm-4-7-flash` | 50M free tokens, `https://api.tensormux.com/v1`. Sign in at `app.tensormux.com`; key starts `tmx_` |
| **Last resort** | — | — | Degrade the case to `queued`. The pipeline never dies on an LLM outage |

```python
primary  = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
fallback = OpenAI(base_url=os.environ["TENSORMUX_BASE_URL"],
                  api_key=os.environ["TENSORMUX_API_KEY"])
```

Because both are OpenAI-compatible, swapping the order is a `models.yaml` edit — no call-site change.

### Routing policy (`config/models.yaml`)

| Concern | What the router does |
|---|---|
| **Task profiles** | Each call site declares a profile (`classify`, `disambiguate`, `select`, `draft`, `narrate`) with its own model, temperature, max-tokens, timeout and retry budget. Closed-label tasks get `gpt-4o-mini` and tight budgets; the cash-application shortlist gets `gpt-4.1` and a generous one |
| **Fallback chain** | OpenAI → TensorMux → **degrade the case to `queued`**. This is exactly what the chaos harness (H7) injects with its LLM-500 failure |
| **Cost metering** | Per-call tokens and cost land on the case (`token_cost_usd`), aggregated into the KPI **"cost per exception resolved"** |

### Two implementation notes for A46

1. **`glm-4-7-flash` is a reasoning model that returns its thinking in a separate `reasoning`
   field.** On a tight `max_tokens` it returns `content: null` with `finish_reason: "length"` and
   the answer stranded in `reasoning`. The fallback leg must budget generously and **must not treat
   empty `content` as failure** — check `reasoning` too, and only degrade to `queued` when both are
   empty. Verified against the live endpoint.
2. **OpenAI is billed pay-as-you-go.** Deterministic-first is therefore a cost strategy as well as
   an accuracy one: the dashboard shows `% of cases resolved with zero LLM calls`, and that number
   rises between Run 1 and Run 2 as learned rules displace model calls. If spend becomes a concern,
   flip the order in `models.yaml` — TensorMux's 50M tokens are free.

---

## 8. Processor settlement reconciliation

A payment processor is a second system that describes the same money differently — which makes it
the same problem as every other workflow here, and a genuinely common one in the Office of the CFO.

**Input:** a **payout report CSV** (`app/adapters/payout_report.py`), the export every processor
provides. Rows become `FinancialTransaction` with `source=payment_processor` and an `external_id`,
then flow into **cash application (Workflow 2)** exactly like a bank line. No new engine.

### Why this earns its place
Processor settlements produce reconciliation differences that are **legitimate, not errors** — and
an agent that knows the difference is exactly the depth Track 2 rewards:

- **Gross vs net** — the customer paid INR 30,000; the payout is INR 29,115 after fees →
  `PROCESSOR_FEE_DIFFERENCE`, resolved with a fee explanation rather than reported as a mismatch.
- **Settlement timing** — the payment succeeds on the 30th, the payout lands on the 2nd →
  `SETTLEMENT_TIMING`, a cut-off difference the agent must *explain*, not "fix."
- **Refunds** — a refund after invoice settlement forces a `REFUND_REVERSAL` audit event, proving
  history is never overwritten.
- **Chargebacks** — `DISPUTE_HOLD` parks the receivable and blocks close, exercising the blocker
  path on the dashboard.

> **On Dodo Payments.** Dodo is the hackathon's credits partner, not a scored integration — it
> appears in none of the eleven rules and in no rubric line. Live webhook ingestion (HMAC
> verification, idempotent handler, test-mode seeding) is designed and specified, but sits in
> **Stretch** (§19): it is the only piece of this build with an external blocker, and a live webhook
> firing mid-recording is a demo risk for no marginal score. The adapter boundary means adding it
> later is one new source, not an architectural change.

---

## 9. Exception taxonomy

Explicit types make the agent testable, demoable, and gradeable.

**Card:** `UNKNOWN_MERCHANT` · `AMBIGUOUS_MERCHANT` · `CATEGORY_UNCERTAIN` · `DUPLICATE_CARD_TRANSACTION`
**Cash application:** `NO_INVOICE_MATCH` · `MULTIPLE_PLAUSIBLE_MATCHES` · `ONE_TO_MANY_PAYMENT` · `PARTIAL_PAYMENT` · `OVERPAYMENT` · `UNDERPAYMENT` · `UNKNOWN_PAYER`
**Close:** `BANK_LEDGER_DIFFERENCE` · `OPS_ERP_MISSING_RECORD` · `INTERCOMPANY_DIFFERENCE` · `ACCRUAL_REQUIRED` · `FX_REVALUATION_PENDING` · `STALE_SOURCE_DATA`
**GST:** `MISSING_IN_2B` · `MISSING_IN_ERP` · `GSTIN_MISMATCH` · `INVOICE_NUMBER_MISMATCH` · `DATE_MISMATCH` · `TAXABLE_VALUE_MISMATCH` · `TAX_AMOUNT_MISMATCH` · `DUPLICATE_INVOICE`
**Processor (from the payout report):** `PROCESSOR_FEE_DIFFERENCE` · `SETTLEMENT_TIMING` · `REFUND_REVERSAL` · `DISPUTE_HOLD`

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
| Processor exceptions (payout report) | 5 |
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
GET  /runs · GET /runs/{id}    run history
GET  /metrics                  KPIs incl. cost/case, auto-resolve %, LLM-free %
POST /admin/reset              reload seed data (demo takes)
```

`X-Actor-Id` names the human on audit events. Absent → `finance_user_01`. That is the entire
identity story, by design.

**This contract is produced first by the Main Orchestrator** (§17) so frontend and backend agents
build against a fixed interface.

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

---

## 15. Three-minute demo script

The narrative is **one hero case + one learning proof + one reliability proof.** Nothing else.

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:20 | **Problem** | Close Readiness at **71%**, four workflows red, ₹4.2L of unresolved impact. *"Finance keeps comparing systems that describe the same money differently."* |
| 0:20–1:00 | **Hero case — cash application** | ₹30,000 from XYZ Retail, reference `SERVICES JUNE`. Agent proposes INV-101 + 102 + 103 at 0.87 confidence with four evidence lines and two ranked alternatives. **Approve.** Audit event appears; a bundle rule is written. |
| 1:00–1:25 | **GST exception** | INV-101: ERP ₹1,800 vs GSTR-2B ₹1,600 → `TAX_AMOUNT_MISMATCH`, 0.99. Agent drafts the vendor correction email. Human approves *sending* — showing the reasoning/action permission split. |
| 1:25–1:50 | **Learning + processor** | Fresh card statement with `SBX*COFFEE 0811` → auto-resolves from the rule learned earlier, **zero LLM calls**. Then a payout report lands: the agent explains a INR 885 fee difference instead of flagging a false mismatch. |
| 1:50–2:15 | **Reliability** | Hit `--chaos`: re-upload a file (no-op), stale GSTR-2B (blocked, not guessed), forced LLM 500 (falls back, then queues). **Zero duplicate actions.** Then `GET /audit/verify` → chain OK. |
| 2:15–2:40 | **Measurable result + AO** | Scorecard: exception queue **−53%**, unsafe auto-resolutions **0**, cost/case **−41%**, readiness **71% → 89%**. Cut to the **AO dashboard** showing the orchestration tree and the session count. |
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
│   ├── adapters/               # bank, card, ar, purchase, gstr2b, ops, payout
│   ├── models/                 # Pydantic + SQLite schema
│   ├── engine/                 # normalize, merchant, cash, subsetsum, scoring,
│   │                           # gst, close, exceptions
│   ├── policy/                 # policies.yaml loader + evaluator
│   ├── memory/                 # learned rules
│   ├── harness/                # ingestion, tools, idempotency, guardrails,
│   │                           # scheduler, evals, chaos, notify,
│   │                           # tracing, modelrouter, audit
│   └── api/                    # routes
├── ui/                         # Vite + React + Tailwind, 5 screens
├── evals/
│   ├── golden/                 # labelled dataset
│   ├── run.py
│   └── reports/scorecard.md
├── seed/                       # dataset generator + demo dataset
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
TENSORMUX_BASE_URL=https://api.tensormux.com/v1
TENSORMUX_API_KEY=            # tmx_...
TENSORMUX_MODEL=glm-4-7-flash
DB_PATH=./reconcileos.db
POLICY_VERSION=v1
```

No auth variables. There is nothing to log into.

---

## 17. Orchestration hierarchy and task division

Every feature in this document is built. The build is organised as a **two-tier orchestration tree**:
one **Main Orchestrator** that owns the system, **eleven Sub-Orchestrators** that each own one
domain, and **57 worker agents** that each own a bounded set of files.

```mermaid
flowchart TB
    MO["<b>MO — Main Orchestrator</b><br/>owns contract · merge queue · cross-cutting calls"]

    MO --> SO1["SO-1<br/>Ingestion"]
    MO --> SO2["SO-2<br/>Platform Harness"]
    MO --> SO3["SO-3<br/>Matching Engine"]
    MO --> SO4["SO-4<br/>GST"]
    MO --> SO5["SO-5<br/>Close"]
    MO --> SO6["SO-6<br/>Policy &amp; Memory"]
    MO --> SO7["SO-7<br/>Pipeline &amp; API"]
    MO --> SO8["SO-8<br/>Interface"]
    MO --> SO9["SO-9<br/>Sponsor Integrations"]
    MO --> SO10["SO-10<br/>Data &amp; Evaluation"]
    MO --> SO11["SO-11<br/>QA &amp; Submission"]

    SO1 --> W1["A01–A07, A47<br/>8 workers"]
    SO2 --> W2["A08–A15<br/>8 workers"]
    SO3 --> W3["A16–A23<br/>8 workers"]
    SO4 --> W4["A24–A26<br/>3 workers"]
    SO5 --> W5["A27–A30, A49<br/>5 workers"]
    SO6 --> W6["A31–A34<br/>4 workers"]
    SO7 --> W7["A35–A39<br/>5 workers"]
    SO8 --> W8["A40–A44<br/>5 workers"]
    SO9 --> W9["A45–A46<br/>2 workers"]
    SO10 --> W10["A50–A53<br/>4 workers"]
    SO11 --> W11["A54–A57<br/>4 workers"]
```

### 17.1 What each tier does

**MO — Main Orchestrator** *(1 agent)*
Owns the system, not any single module. Its responsibilities:
- Produces **A00, the foundation task**, before anything else is dispatched — the SQLite DDL, the
  Pydantic models (§3), the `AuditEvent` hash-chain writer, the OpenAPI stub for every route in §12,
  `.ao/orchestrator-rules.md`, `.ao/worker-rules.md`, `.env.example`, and the pytest skeleton.
  This is the contract all eleven sub-trees code against.
- Dispatches the eleven sub-orchestrators and holds the dependency graph between them.
- Owns the **merge queue**: nothing lands on `main` without passing through MO.
- Arbitrates any cross-domain conflict — two sub-orchestrators wanting the same interface, a
  proposed change to §3 or §12, a disagreement about exception-type ownership.
- Enforces the **global invariants** (§17.4). It writes no feature code.

**SO — Sub-Orchestrator** *(11 agents)*
Each owns one domain and the workers inside it:
- Decomposes its domain into the worker tasks listed below and writes `.ao/tasks/<AGENT-ID>.md`.
- Reviews its workers' PRs **before** they reach MO — a sub-orchestrator is the first quality gate.
- Verifies each worker shipped tests and stayed inside its file boundary.
- Integrates its own domain: the sub-tree must be internally green before MO sees it.
- Escalates to MO rather than editing outside its domain.

**Worker agents** *(57 agents)*
One bounded unit of work, an explicit file list, unit tests, one PR. Never edits outside its files.

---

### 17.2 The eleven sub-trees

#### SO-1 · Ingestion — 8 workers
**Owns:** `app/adapters/`, `config/adapters/`, `app/harness/ingestion.py`
**Depends on:** MO contract (models)

| ID | Owns | Deliverable |
|---|---|---|
| A01 | `app/adapters/bank.py`, `config/adapters/bank.yaml` | Bank statement CSV → `FinancialTransaction` |
| A02 | `app/adapters/card.py`, `config/adapters/card.yaml` | Corporate card CSV → `FinancialTransaction` |
| A03 | `app/adapters/ar_invoices.py`, `config/adapters/ar.yaml` | Open AR invoices CSV → `Invoice(sales)` |
| A04 | `app/adapters/purchase_register.py`, `config/adapters/purchase.yaml` | Purchase register CSV → `Invoice(purchase)` |
| A05 | `app/adapters/gstr2b.py`, `config/adapters/gstr2b.yaml` | GSTR-2B JSON/CSV → `GSTRecord` |
| A06 | `app/adapters/ops_export.py`, `config/adapters/ops.yaml` | Ops/sales export → `OpsRecord` |
| A47 | `app/adapters/payout_report.py`, `config/adapters/payout.yaml` | Processor payout report CSV → `FinancialTransaction(source=payment_processor)` |
| A07 | `app/harness/ingestion.py` | **H1** — file fingerprinting, column sniffing, `as_of` freshness stamps, row quarantine with reasons |

#### SO-2 · Platform Harness — 8 workers
**Owns:** `app/harness/` (except ingestion)
**Depends on:** MO contract (models, audit writer)

| ID | Owns | Deliverable |
|---|---|---|
| A08 | `app/harness/tools.py` | **H2** — typed tool registry, Pydantic in/out pairs, `READ` / `PROPOSE` / `ACT` permission tiers |
| A09 | `app/harness/idempotency.py` | **H3** — `idempotency_key` derivation, `ActionState` table, at-most-once `ACT` execution |
| A10 | `app/harness/guardrails.py` | **H4** — schema validation, DB existence check, arithmetic verifier, evidence-completeness check, safe downgrade to `queued` |
| A11 | `app/harness/scheduler.py` | **H5** — APScheduler continuous-close loop + SQLite `outbox` |
| A12 | `app/harness/chaos.py` | **H7** — all six injections: stale extract, duplicate file, malformed rows, truncated export, LLM 500, mid-run crash |
| A13 | `app/harness/notify.py` | **H8** — console / file / Slack webhook / SMTP sinks behind one interface, all approval-gated |
| A14 | `app/harness/audit.py` | **H11** — append-only writer, `prev_hash` / `this_hash` chaining, chain verification |
| A15 | `app/harness/evidence_pack.py` | **H11** — per-case ZIP: source rows, candidates, scores, policy evaluated, decision, resulting rule, trace link |

#### SO-3 · Matching Engine — 8 workers
**Owns:** `app/engine/` matching modules. **Workflows 1 and 2.**
**Depends on:** MO contract (models)

| ID | Owns | Deliverable |
|---|---|---|
| A16 | `app/engine/normalize.py` | Case, punctuation, store-number, corporate-suffix and location-token normalization |
| A17 | `app/engine/merchant.py` | **Workflow 1** — alias lookup, historical confirmed mappings, RapidFuzz resolution, canonical merchant + proposed GL category |
| A18 | `app/engine/entity.py` | Customer and vendor identity resolution, alias history |
| A19 | `app/engine/cash_candidates.py` | **Workflow 2, Pass A/B** — deterministic rules, then bounded candidate generation filtered by customer, open status, currency and date window |
| A20 | `app/engine/subsetsum.py` | Capped combinatorial allocation, maximum bundle size 4 |
| A21 | `app/engine/scoring.py` | Feature weights → confidence: amount fit, identity, invoice and due dates, reference tokens, past bundle behaviour |
| A22 | `app/engine/residual.py` | Partial, over- and under-settlement; explicit residual cash and residual invoice balance |
| A23 | `app/engine/duplicates.py` | Duplicate transaction and duplicate invoice detection |

#### SO-4 · GST — 3 workers
**Owns:** `app/engine/gst_*.py`. **Workflow 4.**
**Depends on:** MO contract (models); SO-3 normalization interface

| ID | Owns | Deliverable |
|---|---|---|
| A24 | `app/engine/gst_match.py` | GSTIN, invoice number, date and amount normalization; exact matching |
| A25 | `app/engine/gst_mismatch.py` | Fuzzy invoice-number handling (`INV-00123` vs `INV/123`) under policy; mismatch classification into the GST taxonomy |
| A26 | `app/engine/gst_vendor.py` | Exception grouping by vendor; correction-request drafting with exact invoice evidence; tracking unresolved items across filing periods |

#### SO-5 · Close — 5 workers
**Owns:** `app/engine/close_*.py`. **Workflow 3, fully built.**
**Depends on:** MO contract (models)

| ID | Owns | Deliverable |
|---|---|---|
| A27 | `app/engine/close_ops_erp.py` | Ops ↔ ERP matching, missing-record detection |
| A28 | `app/engine/close_bank.py` | ERP ↔ bank reconciliation, fee and timing difference explanation |
| A29 | `app/engine/close_advanced.py` | Intercompany differences, accrual-required cases, FX revaluation pending |
| A30 | `app/engine/close_readiness.py` | Per-workflow resolution percentages, blockers, overall readiness score, today's high-impact actions |
| A49 | `app/engine/processor_exceptions.py` | `PROCESSOR_FEE_DIFFERENCE`, `SETTLEMENT_TIMING`, `REFUND_REVERSAL`, `DISPUTE_HOLD` |

#### SO-6 · Policy & Memory — 4 workers
**Owns:** `app/policy/`, `app/memory/`, taxonomy and explanation
**Depends on:** MO contract (models)

| ID | Owns | Deliverable |
|---|---|---|
| A31 | `app/policy/engine.py`, `config/policies.yaml` | Versioned policy evaluation: materiality, freshness, thresholds, never-auto, controller approval, blocks-close |
| A32 | `app/memory/rules.py` | Learned rule store: type, pattern, scope, source case, confidence, use count, expiry, disable |
| A33 | `app/engine/exceptions.py` | Full §9 taxonomy plus classifier, across all four workflows |
| A34 | `app/engine/explain.py` | Evidence assembly and ranked-alternatives generation for every case |

#### SO-7 · Pipeline & API — 5 workers
**Owns:** `app/pipeline.py`, `app/api/`
**Depends on:** MO contract (OpenAPI stub); consumes every engine sub-tree

| ID | Owns | Deliverable |
|---|---|---|
| **A35** | `app/pipeline.py` | **Orchestration** — ingest → normalize → match → policy → case → audit. The central integrating task |
| A36 | `app/api/core.py` | `POST /ingest/{source}`, `POST /run`, `GET /metrics`, `POST /admin/reset` |
| A37 | `app/api/cases.py` | `GET /cases`, `GET /cases/{id}`, `POST /cases/{id}/decision` |
| A38 | `app/api/rules.py` | `GET /rules`, `POST /rules/{id}/disable` |
| A39 | `app/api/audit.py` | `GET /audit`, `GET /audit/verify`, `GET /cases/{id}/evidence-pack`, `GET /runs` |

#### SO-8 · Interface — 5 workers
**Owns:** `ui/`
**Depends on:** MO contract (OpenAPI stub) only — builds against a mock, never blocked by SO-7

| ID | Owns | Deliverable |
|---|---|---|
| A40 | `ui/src/screens/CloseReadiness.tsx` | **Screen 1** — overall %, per-workflow bars, blockers, high-impact actions |
| A41 | `ui/src/screens/ExceptionQueue.tsx` | **Screen 2** — sortable by financial impact; agent's view, confidence and impact per row |
| A42 | `ui/src/screens/CaseDetail.tsx` | **Screen 3** — evidence, ranked alternatives, arithmetic shown, Approve / Edit split / Reject / Leave unapplied, "View agent reasoning →" |
| A43 | `ui/src/screens/RulesLearned.tsx` | **Screen 4** — pattern, scope, source case, use count, disable toggle |
| A44 | `ui/src/screens/AuditTimeline.tsx` | **Screen 5** — every state transition, hash-chain status badge, evidence-pack download |

#### SO-9 · Sponsor Integrations — 2 workers
**Owns:** `app/integrations/`
**Depends on:** MO contract (models); SO-2 tool registry for span wrapping
**Both unblocked** — Neatlogs, TensorMux and OpenAI keys are all in hand.

| ID | Owns | Deliverable |
|---|---|---|
| A45 | `app/integrations/neatlogs.py` | **§6** — WORKFLOW span per run, child span per tool call, span per LLM call, guardrail rejections as error events, `neatlogs_trace_id` propagated onto cases, runs and audit events |
| A46 | `app/integrations/tensormux.py`, `config/models.yaml` | **§7** — OpenAI-compatible client, task-profile routing, **OpenAI → TensorMux → degrade-to-`queued`** fallback chain, per-call token and cost metering onto the case |

#### SO-10 · Data & Evaluation — 4 workers
**Owns:** `seed/generate.py`, `evals/`
**Depends on:** MO contract (models); SO-6 policy for the safety metric

| ID | Owns | Deliverable |
|---|---|---|
| A50 | `seed/generate.py` | 400-record golden dataset per the §11 table, **built from known ground truth with labels emitted alongside the data** |
| A51 | `evals/run.py` | All nine metrics from §11, including unsafe-auto-resolution rate and the Run 1 vs Run 2 learning comparison |
| A52 | `evals/report.py` | `evals/reports/scorecard.md` renderer |
| A53 | `evals/verify_labels.py` | Stratified 40-record label audit, so ground truth is checked rather than assumed |

#### SO-11 · QA & Submission — 4 workers
**Owns:** `tests/e2e/`, `README.md`, `docs/`
**Depends on:** merged output of every other sub-tree

| ID | Owns | Deliverable |
|---|---|---|
| A54 | `tests/e2e/` | Full run green, chaos suite green, audit chain verified, zero duplicate side effects on retry |
| A55 | `seed/demo_dataset.py`, `docs/DEMO-SCRIPT.md` | The exact §15 cases present and visually clean: the INR 30,000 XYZ Retail bundle, the INV-101 GST mismatch, `SBX*COFFEE 0811` |
| A56 | `README.md` | Problem statement, architecture summary, setup instructions, how to run the evals |
| A57 | `docs/AO-SESSIONS.md` | Session count, task → PR → commit table, AO dashboard screenshots |

---

### 17.3 Agent roster

| Tier | Count |
|---|---:|
| Main Orchestrator | 1 |
| Sub-Orchestrators (SO-1 … SO-11) | 11 |
| Worker agents | 56 |
| **Total** | **68** |

| Sub-tree | Workers |
|---|---:|
| SO-1 · Ingestion | 8 |
| SO-2 · Platform Harness | 8 |
| SO-3 · Matching Engine | 8 |
| SO-4 · GST | 3 |
| SO-5 · Close | 5 |
| SO-6 · Policy & Memory | 4 |
| SO-7 · Pipeline & API | 5 |
| SO-8 · Interface | 5 |
| SO-9 · Sponsor Integrations | 2 |
| SO-10 · Data & Evaluation | 4 |
| SO-11 · QA & Submission | 4 |

---

### 17.4 Escalation and reporting protocol

**Upward — worker → SO → MO**

| Situation | Handled by |
|---|---|
| Needs a file inside its own sub-tree | SO reassigns or sequences the two workers |
| Needs a file in another sub-tree | Escalate to MO; MO routes it to the owning SO |
| Wants to change the data model (§3) or API contract (§12) | **MO only.** Contract amendments are never unilateral |
| Ambiguity about which exception type owns a case | MO, since the taxonomy (§9) spans sub-trees |
| Sub-tree internally red | SO fixes before surfacing to MO |

**Downward — MO → SO → worker**
MO dispatches a domain brief; the SO decomposes it into `.ao/tasks/<AGENT-ID>.md` files and assigns
them. Every task file names the owning agent, its files, its deliverable, and its dependencies.

**Merge path**
`worker PR → SO review (tests present, boundary respected, domain green) → MO merge queue
→ global invariants checked → main`

---

### 17.5 Global invariants — enforced by MO, on every merge

1. The audit log is append-only and the hash chain verifies.
2. No `ACT`-tier tool executes without an idempotency key.
3. No case auto-resolves without policy approval, regardless of confidence.
4. No candidate ID reaches a proposal without existing in the database.
5. Every case carries evidence, a policy version, and a Neatlogs trace ID.
6. No eval number, metric, or test result is ever fabricated.

### 17.6 Standing instructions for every worker agent

1. You own the files listed in your row. Raise a dependency rather than editing outside them.
2. The data model (§3) and the API contract (§12) come from MO. Code against them.
3. Ship unit tests with your module. A PR without tests does not merge.
4. Never fabricate an eval number, a metric, or a test result.
5. No credentials in code, task descriptions, or commit messages.
6. One module, one PR, one concern.

---

## 18. How this maps to the judging rubric

| Criterion | Weight | Where it's earned |
|---|---|---|
| **AO Usage & Build Process** | 25% | §5 + §17 — `.ao/` rules committed first, 56 parallel worktree PRs, `AO-SESSIONS.md`, commit trailers, AO dashboard on camera. AO isn't decoration here; a 10-hour build of this size is only possible because of it |
| **Technical Execution & Reliability** | 25% | §4 harnesses, §11 eval gate with unsafe-auto-resolve = 0, §13 hash-chained audit, §14 controls, chaos demo |
| **Track Fit & Real-World Value** | 25% | Four genuine Office-of-the-CFO workflows, full exception taxonomy, human review gates, evidence packs, close readiness |
| **Demo & Usability** | 15% | §15 — one hero case, one learning proof, one reliability proof, in 3 minutes |
| **Innovation** | 10% | Reconciliation as a reusable operating layer; audit events that link to the agent's own reasoning trace; learning measured against a safety metric, not just an accuracy one |

---

## 19. Scope discipline

**Must ship:** canonical store · card normalization · cash matching incl. 1:many · GST reconciliation ·
Ops↔ERP↔Bank close matching · exception queue · confidence + evidence · approve/edit/reject/defer ·
rule memory · hash-chained audit · evidence packs · close-readiness dashboard · chaos ·
Neatlogs · TensorMux · processor payout reconciliation · eval scorecard · AO evidence

**Stretch:** live Dodo Payments webhook ingestion (HMAC verify + idempotent handler) · real vendor email send · live ERP/bank connectors · richer FX depth ·
automatic journal generation · remittance PDF extraction · second failure-analysis→fix→re-score cycle

**Do not build:** authentication of any kind · 2FA · RBAC · multi-tenancy · replay harness · general-ledger
replacement · tax filing engine · payroll · a generic autonomous-CFO chatbot · UI polish beyond legibility

> **The standing rule:** if a feature cannot appear in the 3-minute video *or* in
> `evals/reports/scorecard.md`, it does not get built during the hackathon.

---

## 20. Submission requirements

Hard requirements from the organisers. Missing any one of these invalidates the entry regardless of
how good the build is.

**Deadline:** September 7, 2026, 03:30 IST (September 6, 18:00 EDT).

### Accounts and registration
| Item | Where |
|---|---|
| Discord — **mandatory** | https://discord.gg/Sy3EwRBQX3 |
| Devpost — **the only official submission channel** | https://syndicate-by-maximor.devpost.com/ |
| Luma registration | https://luma.com/d0kq45ek |
| Hackathon pass (post it, tag AO) | https://aoagents.dev/hackathons/syndicate/pass/ |
| TensorMux key | https://app.tensormux.com |
| AI Grants India — GPT-5 Nano / credits | https://aigrants.in/form?ref=ao |
| Neatlogs key | https://neatlogs.com |

Dodo Payments is the credits partner, **not** a submission requirement — it appears in none of
the eleven rules and no rubric line.

**Every team member registers individually. One official submission per team.**

### Devpost submission fields
- Team name and team member names
- Selected track — **Track 2: Autonomous Office of the CFO**
- Public GitHub repository link
- Live project link, if deployed
- **Public link to the demo video posted on X or LinkedIn**
- Brief description of what was built
- **Explanation of how AO was used during the build**

### Demo video
- Posted publicly on **X or LinkedIn**; the post URL goes on Devpost. The video itself is not uploaded to Devpost.
- Must show **what the project does** *and* **the AO sessions used while building it**. Judges count AO sessions from the video — §15 reserves a beat for the AO dashboard.

### README must explain
- What the project does
- How to run it
- Which track it is submitted to
- What agent workflow was built
- What improved across iterations — this is `evals/reports/scorecard.md`
- Any demo or live links

### What the Track 2 judges said they are looking for
Quoted priorities, and where this architecture answers them:

| Judge question | Answered by |
|---|---|
| "Is the problem a genuine pain-point for people in the Office of the CFO?" | §1 — four real reconciliation workflows, not a CFO chatbot |
| "Is the human judgement side of the finance automation truly intuitive?" | §10 policy engine, §12 exception queue — the human is a judge, not a detective |
| "How deep and well thought through is the automation in context of the specific workflow?" | §9 exception taxonomy, §5–8 per-workflow depth |
| "How well grounded is this to be genuinely used by accountants in the real world?" | §13 audit trail and evidence packs, §14 failure controls |

They also said explicitly: **don't build login/auth/2FA unless it's core to the idea** (§0 already
removes it), **don't leave the demo video to the last minute**, and **3 minutes is not a lot of
time** (§15 is timed to the second).

---

*One agent. One loop. Resolve what is certain, escalate what is not, remember the judgment, prove what happened.*