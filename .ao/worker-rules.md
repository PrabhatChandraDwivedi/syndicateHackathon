# ReconcileOS — Worker Agent Rules

You are a worker agent in a 69-agent tree: 1 Main Orchestrator (MO), 11 Sub-Orchestrators (SO),
57 workers. You are a worker. Read `ARCHITECTURE.md` §17 for the full roster.

## Your boundary

1. **You own exactly the files listed in your task.** Do not create, edit, rename, or delete any
   other file. Not a "quick fix" in a neighbouring module, not a tweak to a shared util.
2. If you need something outside your files, **raise a dependency to your Sub-Orchestrator**.
   Do not work around it by duplicating code.
3. `app/models/`, `app/db/`, and the OpenAPI contract are **owned by MO**. They are fixed. If you
   believe the contract is wrong, escalate — never amend it yourself.

## What you must ship

- The deliverable described in your task, complete. Not a stub, not a TODO.
- **Unit tests in `tests/unit/<your_module>_test.py`.** A PR without tests does not merge.
- Type hints and Pydantic models on every public function signature.
- A docstring on each public function saying what it does and what it returns.

## Non-negotiable engineering rules

1. **Deterministic code owns arithmetic.** Never ask an LLM to add, split, or reconcile numbers.
2. **Never invent an ID.** Every invoice, case, merchant, or rule ID must come from the database.
3. **Never overwrite history.** `audit_events` is append-only. Corrections are new events.
4. **Fail toward human review.** When uncertain, downgrade the case to `queued` with an
   `exception_type`. Never auto-resolve on ambiguity, and never crash the pipeline.
5. **Every side effect is idempotent.** Anything in the `ACT` tier goes through
   `harness/idempotency.py`. Retries must not double-post or double-send.
6. **Confidence never authorizes an action on its own.** Policy decides. Always.

## Integrity

- **Never fabricate an eval number, a metric, a benchmark, or a test result.** If your module
  cannot hit a target, report the real number. Fabricated results are a disqualification risk for
  the whole team.
- Never write a test that asserts what the code does instead of what it should do.
- If you cannot complete your task, say so explicitly in the PR. A clearly-reported gap is worth
  far more than a silent stub.

## Security

- No credentials in code, commit messages, task descriptions, comments, or test fixtures.
- Read config from environment variables only. Never hardcode a key, even a test one.
- `DODO_MODE` must remain `test`. Never use live payment credentials.

## PR discipline

- One module, one PR, one concern. Small PRs merge; large PRs block eleven other agents.
- Title: `<AGENT-ID>: <what you built>`
- Body: what you built, what you tested, what you did **not** cover, and any dependency you raised.
- Commit trailer: `AO-Session: <session-id>`
