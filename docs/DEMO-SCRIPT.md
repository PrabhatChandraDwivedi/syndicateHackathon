# ReconcileOS — three-minute demo script

Three claims, each proved on screen:

1. **An agent runs the close.** It decides what to do; it is not a script with a dashboard.
2. **It knows what it is not allowed to do.** Policy refuses it, and you watch that happen.
3. **It learns from you** — but only as far as you have let it.

---

## Before you record

```bash
pip install -r requirements.txt
uvicorn app.main:app
# open http://127.0.0.1:8000
```

Start from a genuinely clean slate, or the "it learned" beat will not land:

```bash
rm -rf data/ seed/data/          # forgets learned rules, drafts and the audit chain
```

then restart the server. The page should open showing dashes, not numbers.
Keep a second terminal ready for the audit and eval commands.

> The page opens **empty on purpose**. Nothing is computed until the agent acts — every figure
> you see later exists because it did something.

---

## 0:00 — 0:20 · The problem

> "Closing the books means tying together feeds that never agree. A card statement, a bank
> statement, an operations export, supplier GST filings. Most of month-end is matching rows,
> chasing the ones that don't match, and then proving why every decision was made."

Show the empty dashboard. Point at the dashes.

> "Nothing here has run yet."

---

## 0:20 — 1:00 · The agent works

Press **Run the whole close**.

> "This isn't a reconciliation button. The agent gets one goal — close the books — and it chooses
> what to do."

As the timeline fills in, narrate what it actually chose (it varies between runs):

> "It ran the reconciliation itself. Then checked GST against what suppliers filed. Then tied
> operations through to the bank. Each of those is a tool it picked, not a step we scripted."

> "It can only touch the ledger through those tools, and every argument is schema-validated before
> it runs — so a hallucinated invoice id is rejected, not executed."

Point at the figures that just appeared: close readiness, cases, audit chain **Intact**.

---

## 1:00 — 1:30 · It refuses to overstep ← the one to land

Scroll to the **Exceptions** table. Double-click the row with **split payment**.

> "One bank credit that equals the sum of several card lines, found by subset-sum. That's a
> heuristic — more than one combination can add up to the same total — so it can be coincidentally
> wrong."

> "So policy refuses to let it auto-resolve. Not because the model chose to be careful: the tool
> re-checks policy itself. Even with a confident rationale it cannot resolve a duplicate or a split
> payment. The agent decides *what to do*; it does not decide *what it's allowed to do*."

Show `config/policies.yaml` — `blocked_exception_types`.

> "And that's configuration, not code."

*If the agent attempted a blocked case this run, the step is marked **Refused by policy** in the
timeline — show that instead, it's stronger. It won't happen every run.*

---

## 1:30 — 2:10 · It asks, then learns

Point at **Waiting on you**.

> "It didn't guess on this one. Same merchant, same amount, two days apart — but the payment
> references don't match, so it asked."

Press **Approve and remember**. Show the rule appear in **What the agent has learned**.

> "That's now a rule. Watch what it does with it."

Press **Run the whole close** again. Show that case resolving itself, tagged **from memory**.

> "Second run, handled on its own. It asks once, learns from the answer, and stops asking."

Then the part that matters:

> "But the trust is bounded. Look at the rule: it's **provisional** until it's been applied a few
> times without being reversed, and it's valid only up to a capped amount near the one it learned
> on. A much larger charge from the same merchant comes straight back to a human — it doesn't
> inherit a small case's approval. And if I ever reject something it resolved this way, the rule is
> revoked immediately."

---

## 2:10 — 2:40 · GST, and chasing the vendor

Scroll to **GST · input tax credit**.

> "Same run. It compared our purchase register against GSTR-2B. Three matched. One invoice the
> supplier filed nine hundred and ninety nine rupees light. And one they never filed at all — which
> puts **₹2,160 of input tax credit at risk**. That's the number a CFO actually wants."

Double-click the **Supplier has not filed** row for the explanation.

> "And both of those are the supplier's to fix, so it drafts the chasers."

Show **Vendor chasers** with the two drafts.

*If the agent didn't draft them this run, press **Draft all mails** — same code, you're overriding
whether it happens, not how.*

> "Prepared, not sent. Nothing leaves the building without a person pressing send. Notice the third
> finding has no button — that invoice is in GSTR-2B but not in our register. That's our own
> bookkeeping gap, not theirs. Emailing the supplier about it would be wrong."

---

## 2:40 — 2:55 · Proof

Scroll to **Month close**.

> "Two orders tied out, one settled eight hundred and fifty short, one with neither invoice nor
> settlement, and a bank credit nothing explains. Close readiness: fifty percent."

In the terminal:

```bash
curl -s localhost:8000/audit/verify
python -m evals.run && tail -12 evals/reports/scorecard.md
```

> "Every decision — the agent's and mine — is in one hash-chained audit log. Edit any row and this
> tells you exactly where it broke."

> "And we score the engine against a labelled set. The headline number isn't accuracy, it's
> **unsafe_auto_resolve**: how often it resolved something a human should have seen. It has to be
> zero."

> "The first time we ran this it was **one**. It caught that aggregated payouts were auto-resolving.
> We changed the policy, not the label, and re-scored."

---

## 2:55 — 3:00 · Close

> "An agent that runs the close, refuses what it isn't allowed to touch, asks when it's unsure, and
> learns from the answer — only as far as you've let it."

---

## If something goes wrong on stage

| Problem | What to do |
|---|---|
| Agent run fails or the model is unreachable | It returns a readable summary, not an error. Every other panel still works. |
| Agent didn't draft the chasers | Press **Draft all mails**, or **Draft mail** on a single row. |
| Agent's step sequence differs from this script | Expected — it's a live model. Narrate what it actually did; the tools are the same. |
| No network | Only the agent's reasoning needs it. Matching, GST and close are fully deterministic; tracing no-ops without a key. |
| UI won't load | One static file, no build, no CDN. `/docs` exposes every endpoint. |
| Need a clean slate between takes | **Start over** on the page. To also forget what it learned: stop the server, `rm -rf data/`, restart. |

---

## What a judge can check afterwards

- `GET /agent/last` — the agent's full reasoning trace, tools and observations
- `GET /audit/verify` — the hash chain over every decision, human and agent
- `evals/reports/scorecard.md` — `unsafe_auto_resolve: 0`, `RESULT: PASS`
- `config/policies.yaml` — the controls, as configuration
- Neatlogs — a span per agent step and per tool call, with refusals recorded as error-level
  detections
