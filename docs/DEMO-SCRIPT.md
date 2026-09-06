# ReconcileOS — three-minute demo script

The demo makes three claims and proves each one on screen: **it does the work**, **it knows when
not to act**, and **it can prove what it did**.

Setup before recording:

```bash
pip install -r requirements.txt
uvicorn app.main:app
# open http://127.0.0.1:8000
```

Have a second terminal ready for the audit and eval commands.

---

## 0:00 — 0:20 · The problem

> "Closing the books means tying together feeds that never agree. A corporate card statement, a
> bank statement, an ops export, supplier GST filings. Most of the month-end is matching rows and
> chasing the ones that don't match — and then proving why every decision was made."

Show the dashboard with the run not yet started.

---

## 0:20 — 0:50 · One run, end to end

Click **Run reconciliation**.

> "One run ingests both feeds, normalizes them, and matches them."

Point at the stat tiles as they fill in: close readiness, total cases, auto-resolved, needs review,
and the audit chain reading **VERIFIED**.

> "It resolved the clean matches by itself and pushed the rest to a human queue. Nothing here is a
> mock — this is a real pipeline run against the seeded dataset."

---

## 0:50 — 1:25 · The hero case: an aggregated payout

Open the case with method **one_to_many**.

> "This bank credit is a single aggregated payout. It doesn't equal any one card transaction — it's
> the sum of two of them. Bounded subset-sum found the combination."

Show the reasons on the case detail.

> "And notice it did **not** auto-resolve it. Subset-sum is a heuristic: several different
> combinations can add up to the same total, so a 1:many match can be coincidentally wrong. Policy
> requires a human to confirm it. That rule lives in `config/policies.yaml`, not in code."

Show `config/policies.yaml` briefly — `blocked_exception_types` including `split_payment`.

---

## 1:25 — 1:50 · The duplicate

Open the case with exception **duplicate_transaction**.

> "Same amount, same date, same merchant as an earlier transaction. Flagged as a duplicate, and
> duplicates outrank every other exception in the taxonomy — so this can never be quietly
> auto-resolved either."

---

## 1:50 — 2:20 · Proof: the audit chain and the evidence pack

> "Every decision writes an audit event, and each event hashes over the one before it."

In the terminal:

```bash
curl -s localhost:8000/audit/verify
```

> "The chain verifies. If anyone edits a row after the fact, this reports exactly where it broke —
> that's what replaces authentication as the trust mechanism here."

Back on the case, click the evidence pack download.

> "And any case exports as a self-contained ZIP: the case, its audit events, the underlying
> transactions, and a manifest. That's what you hand an auditor."

---

## 2:20 — 2:50 · Proof: the safety metric

```bash
python -m evals.run
cat evals/reports/scorecard.md
```

> "We score the engine against a labelled golden set. The headline number isn't accuracy — it's
> `unsafe_auto_resolve`: how often the system resolved something a human should have seen. It has
> to be zero."

Point at `unsafe_auto_resolve: 0` and `RESULT: PASS`.

> "This is the loop working, not a number we wrote down. The **first** run of this scorecard
> reported `unsafe_auto_resolve: 1` — it caught that aggregated payouts were auto-resolving. We
> changed the policy, not the label, and re-scored."

---

## 2:50 — 3:00 · Close

> "Deterministic matching, explainable confidence, policy as configuration, a tamper-evident audit
> trail, and a safety metric that gates the build. Reconciliation as an operating layer, not a
> one-off script."

---

## If something goes wrong on stage

- **The UI doesn't load** — it's one static HTML file with no build step and no CDN calls; hit
  `/docs` for the API directly, every number on the dashboard comes from `/metrics` and
  `/close-readiness`.
- **No network** — nothing in the demo path requires it. Tracing no-ops without a key and LLM
  adjudication degrades to the deterministic result.
- **Need a clean slate between takes** — `POST /admin/reset`, then click Run again.
