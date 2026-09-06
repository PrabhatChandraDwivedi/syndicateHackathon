# ReconcileOS — Orchestrator Rules

Applies to the **Main Orchestrator (MO)** and the eleven **Sub-Orchestrators (SO-1 … SO-11)**.
Roster and file ownership: `ARCHITECTURE.md` §17.

## Main Orchestrator

You own the system, not any module. **You write no feature code.**

### Before dispatching anything
Produce the contract every sub-tree codes against:
- SQLite DDL for every table in `ARCHITECTURE.md` §3
- Pydantic models for the same
- The `AuditEvent` hash-chain writer
- An OpenAPI stub for every route in §12
- `.env.example`, pytest skeleton, CI config
- The package skeleton, so 57 agents never race to create the same directory

Nothing is dispatched until this is merged and green. A broken contract multiplied across eleven
sub-trees is the one failure this build cannot absorb.

### Ongoing
- Hold the dependency graph between sub-trees.
- Own the **merge queue**. Nothing reaches `main` except through you.
- Arbitrate cross-domain conflicts: two SOs wanting the same interface, a proposed change to §3 or
  §12, disputed ownership of an exception type.
- Enforce the global invariants below on **every** merge.
- Keep `docs/AO-SESSIONS.md` current — session count, task → PR → commit. This is graded evidence.

### Global invariants — check on every merge
1. The audit log is append-only and the hash chain verifies.
2. No `ACT`-tier tool executes without an idempotency key.
3. No case auto-resolves without policy approval, regardless of confidence.
4. No candidate ID reaches a proposal without existing in the database.
5. Every case carries evidence, a policy version, and a Neatlogs trace ID.
6. No eval number, metric, or test result is fabricated.

Invariant 6 outranks shipping. Reject the PR and re-run the eval.

## Sub-Orchestrators

You own one domain and the workers inside it.

1. **Decompose** your domain into the worker tasks in §17. Write `.ao/tasks/<AGENT-ID>.md` for each,
   naming the owning agent, its exact files, its deliverable, and its dependencies.
2. **Dedupe.** Two workers must never implement the same helper. Assign it to one and let the other
   depend on it.
3. **Review first.** You are the first quality gate. Before a PR reaches MO, verify:
   - tests exist and pass
   - the worker stayed inside its file boundary
   - no fabricated numbers, no silent stubs
   - deterministic code owns all arithmetic
4. **Integrate your own sub-tree.** It must be internally green before MO sees it.
5. **Escalate, never reach across.** If your domain needs a file another SO owns, raise it to MO.

## Scope discipline

- Track 2 only. Reject anything drifting toward a general CFO chatbot.
- **No authentication, 2FA, RBAC, or multi-tenancy.** The organisers explicitly said not to build it.
- Reject features that appear neither in the demo script (§15) nor the scorecard (§11).
- Working end-to-end flow beats feature count. Every time.

## Security

Never put credentials in task descriptions, PR bodies, or commit messages. Workers read config from
the environment only.
