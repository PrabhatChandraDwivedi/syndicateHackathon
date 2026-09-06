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

Still missing:

| Missing | Needed for | Fix |
|---|---|---|
| **A tunnel** (ngrok / cloudflared) | Dodo webhooks reaching `localhost:8000` | `winget install Cloudflare.cloudflared` then `cloudflared tunnel --url http://localhost:8000` |
| **Neatlogs API key** | H9 tracing — the audit→reasoning link | Sign up at neatlogs.com, copy project key |
| **Dodo test account** | §8 payment feed | Ask in `#syndicate-help` for same-day verification |

Keys you already have: **TensorMux** (`tmx_…`) and **OpenAI**.

> **Use the OpenAI key as the router's secondary provider.** TensorMux exposes one model
> (`glm-4-7-flash`), so the fallback chain is `TensorMux → OpenAI → degrade case to queued`. That
> makes the chaos harness's "LLM 500" injection a real test instead of a mocked one.

---

## 2. Repo bootstrap — MO does this first, alone

Fifty-seven agents cannot start until these exist. Anything here that's missing becomes a race
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
| `app/models/` — Pydantic models for every §3 entity | Every one of the 57 agents imports these |
| `app/db/schema.sql` + migration runner | Same |
| `app/harness/audit.py` hash-chain writer | Referenced by policy, pipeline, API, evals |
| OpenAPI stub for every §12 route | Lets SO-8 (UI) build against a mock instead of waiting on SO-7 |
| **Package skeleton** — every directory in §16 with `__init__.py` | Otherwise agents race to create the same folders and collide on imports |
| `tests/conftest.py`, `pytest.ini` | Workers must ship tests; they need the fixtures to exist |
| `.github/workflows/ci.yml` | AO fixes CI automatically, but only if CI exists |
| `.ao/tasks/A01.md … A57.md` | One task file per worker — this is also your AO evidence trail |

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
| H9 Neatlogs | A45 | `neatlogs` | **`NEATLOGS_API_KEY`** | account signup |
| H10 TensorMux router | A46 | `openai` | `TENSORMUX_*` ✓, `OPENAI_API_KEY` ✓ | ready now |
| H11 Audit + evidence | A14/A15 | stdlib | — | models |

**Dodo** (A47/A48/A49) additionally needs `DODO_API_KEY`, `DODO_WEBHOOK_SECRET`, and a running
tunnel. It is the only sub-tree with an external dependency that can't be resolved on this machine
right now — sequence it last within SO-9.

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
1. Fill .env  (TensorMux ✓, OpenAI ✓, Neatlogs ⨯, Dodo ⨯)
2. uv venv && uv pip install -r requirements.txt
3. MO builds the contract  → models, schema, audit writer, OpenAPI stub,
                             package skeleton, conftest, CI
4. MO writes .ao/tasks/A01..A57.md
5. MO merges the contract to main   ← nothing dispatches before this
6. Dispatch SO-1 … SO-11 in parallel
7. SO-9 sequences Dodo last (external dependency)
```
