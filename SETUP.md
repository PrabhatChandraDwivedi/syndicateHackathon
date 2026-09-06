# Setup — what must exist before agents start

Three layers: your **machine**, the **repo bootstrap** (MO's job, blocks everything), and the
**per-harness requirements** each agent inherits.

---

## 1. Machine setup

Already present on this machine:

| Tool | Version | For |
|---|---|---|
| git | 2.46.2 | — |
| `gh` | 2.92.0, authed | Agents open PRs. Scopes: `repo`, `workflow`, `gist`, `read:org` |
| **AO desktop app** | installed | The build harness. 25% of the score |
| Claude Code | 2.1.220 | The coding agent AO drives |
| Python | 3.13.2 | Backend. Neatlogs needs `>=3.10,<3.14` ✓ |
| uv | 0.10.2 | Fast venv + installs |
| Node | 24.13.0 | UI (Vite + React) |
| Docker | 29.6.1 | Not required |
| OBS | installed | Demo video recording |

**Nothing is missing.** All three keys are in hand: **TensorMux** (`tmx_…`), **OpenAI**, and
**Neatlogs**. No tunnel is needed — live Dodo webhooks were dropped (see below), so every source is
a local file and the whole system runs offline.

> **OpenAI is primary, TensorMux is the fallback leg.** The chain is
> `OpenAI → TensorMux → degrade case to queued`, which makes the chaos harness's "LLM 500"
> injection a real test rather than a mocked one. Both keys are verified working against their live
> endpoints. Flip the order in `config/models.yaml` if OpenAI spend becomes a concern — TensorMux's
> 50M tokens are free.

> **Dodo Payments is dropped from the critical path.** It is the hackathon's credits partner, not a
> scored integration — it appears in none of the eleven rules and no rubric line. It was the only
> sub-tree needing an external account and a public tunnel, and a live webhook mid-recording is a
> demo risk for zero marginal points. The *finance content* is kept: processor fee and settlement-
> timing differences are reconciled from a **payout report CSV** (`app/adapters/payout_report.py`).
> Live webhook ingestion is specified and sits in Stretch — adding it later is one new source, not
> an architectural change.

---

## 2. Repo bootstrap — MO does this first, alone

The 56 worker agents cannot start until these exist. Anything here that's missing becomes a race
between agents to create the same file.

Already committed:

- `ARCHITECTURE.md` — the spec
- `.ao/orchestrator-rules.md` — MO + SO rules, global invariants
- `.ao/worker-rules.md` — file boundaries, integrity rules, PR discipline
- `.env.example` — every variable, documented
- `requirements.txt` — pinned floors

Still owed by MO **before dispatch**:

| Item | Why it blocks |
|---|---|
| `app/models/` — Pydantic models for every §3 entity | Every one of the 56 workers imports these |
| `app/db/schema.sql` + migration runner | Same |
| `app/harness/audit.py` hash-chain writer | Referenced by policy, pipeline, API, evals |
| OpenAPI stub for every §12 route | Lets SO-8 (UI) build against a mock instead of waiting on SO-7 |
| **Package skeleton** — every directory in §16 with `__init__.py` | Otherwise agents race to create the same folders and collide on imports |
| `tests/conftest.py`, `pytest.ini` | Workers must ship tests; they need the fixtures to exist |
| `.github/workflows/ci.yml` | AO fixes CI automatically, but only if CI exists |
| `.ao/tasks/` — one file per worker (56) | Your AO evidence trail |

Bootstrap commands:

```bash
uv venv
uv pip install -r requirements.txt
cp .env.example .env        # then fill in the keys
```

---

## 3. Per-harness setup

What each harness needs to exist before its owning agent can build it.

| Harness | Owner | Packages | Env / external | Blocked on |
|---|---|---|---|---|
| H1 Ingestion | A07 | pandas | — | models |
| H2 Tool registry | A08 | pydantic | — | models |
| H3 Idempotency | A09 | stdlib | — | `ActionState` table |
| H4 Guardrails | A10 | pydantic | — | models + DB handle |
| H5 Scheduler | A11 | apscheduler | — | pipeline entrypoint |
| H6 Evals | A51 | pandas | — | policy (safety metric) |
| H7 Chaos | A12 | stdlib | — | ingestion + router |
| H8 Notifications | A13 | httpx | `SLACK_WEBHOOK_URL` *(optional)* | — |
| H9 Neatlogs | A45 | `neatlogs` | `NEATLOGS_API_KEY` ✓ | ready now |
| H10 Model router | A46 | `openai` | `OPENAI_API_KEY` ✓, `TENSORMUX_*` ✓ | ready now |
| H11 Audit + evidence | A14/A15 | stdlib | — | models |
| Payout report adapter | A47 | pandas | — | models |

**Every harness is unblocked.** No sub-tree waits on an external account or a network call.

### Two ordering traps

1. **`neatlogs.init()` must run before any LLM client import.** Auto-instrumentation patches
   libraries at import time. It goes at the very top of `app/main.py`, above `from openai import …`.
   If A45 and MO disagree about this line, MO wins — it's in the contract.
2. **The OpenAPI stub must exist before SO-8 starts**, or five UI agents idle waiting on five API
   agents.

---

## 4. AO setup

1. Launch the AO desktop app and point it at this repo.
2. Set the coding agent to **Claude Code** (installed).
3. Base branch `main`; each worker gets its own worktree and PR.
4. Load `.ao/orchestrator-rules.md` as the orchestrator prompt and `.ao/worker-rules.md` as the
   worker prompt.
5. Create tasks from `.ao/tasks/`, one per worker agent.
6. Enable CI-fix and merge-conflict handling.

**Record AO sessions from the first commit.** Judges count sessions from the demo video, and the
video must show the AO dashboard. Starting AO late makes the evidence look retrofitted.

---

## 5. Order of operations

```
1. Fill .env  (TensorMux ✓, OpenAI ✓, Neatlogs ✓)
2. uv venv && uv pip install -r requirements.txt
3. MO builds the contract  → models, schema, audit writer, OpenAPI stub,
                             package skeleton, conftest, CI
4. MO writes the 56 task files under .ao/tasks/
5. MO merges the contract to main   ← nothing dispatches before this
6. Dispatch SO-1 … SO-11 in parallel — all eleven are unblocked
```
