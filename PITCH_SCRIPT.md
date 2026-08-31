# 🎤 SOW-TaskMaster — Pitch Script

**Track:** Task Master · **Stack:** Google ADK + Gemini · **Demo length:** 4–5 min live · **Talk total:** 5 min + Q&A

> How to use this: the script is written for **one presenter + one demo driver**. **[DEMO]** lines are
> driver actions; everything else is spoken. Time estimate per beat is in brackets. Rehearse the
> live run at least twice before judging day.

---

## 1. Hook — "The problem that won't die" (0:00–0:45)

> *(No demo yet. Stand next to the diagram, not the terminal.)*

"Every company that sells services signs Statements of Work. And almost every one of those SOWs still
moves through the same broken pipeline: an email to the account team, a Word draft that gets version-confused,
three people manually checking the numbers, a customer redline that starts the whole thing over, and
finally a signature — if nothing got dropped along the way.

The cost isn't the paperwork. It's the **lack of a brain**: no single place that knows what stage a deal
is in, no consistent validation, no audit trail, and a human doing every stitch by hand.

**What we built is that brain.** An orchestrating Task Master that runs the whole lifecycle, delegates to
seven specialised agents, escalates to humans only at real decision points, and explains every step it took."

---

## 2. Architecture — "One brain, seven workers" (0:45–1:45)

> *(Point at the README Mermaid diagram, or one slide.)*

"Three layers.

**Layer one — the orchestrator, the Task Master.** It owns a resumable six-stage state machine:
intake, drafting, validation, approval, customer review, signing. It doesn't do the work — it *delegates*.

**Layer two — specialised agents**, built on Google ADK as proper `LlmAgent`s: an intake agent that
parses the request, a drafting agent that builds the SOW from a template, a validation agent, an approval
router, a customer liaison, a signature agent, and a notifier. Each does one job well — which is exactly
how you'd staff it with humans.

**Layer three — the mocks.** Every integration — inbox, email, approvals, e-signature — sits behind a
`Protocol` interface. The demo runs entirely on mocks, and swapping in DocuSign, Gmail or Slack later is
a one-file change. The orchestrator never knows the difference.

One design decision worth calling out: validation pass/fail is **deterministic rules, not LLM judgement**.
The LLM summarizes and parses and negotiates; it doesn't decide whether a deal is deliverable. That's what
makes this demo reproducible and trustworthy — and in production, auditable."

---

## 3. Live Demo — "Watch a deal close itself" (1:45–4:15)

> **[DEMO]** Terminal A (mock mode): `python main.py --scenario high` — a £120K request.

*(narrate as it runs)*

"Here's a high-value request — £120,000, 24 weeks. The Task Master creates a tracked case. The intake
agent pulls out customer, scope, budget, timeline. The drafting agent fills the template. Validation runs
three checks — margin, timeline feasibility, delivery capacity — all pass, with reasoning printed next to
each one.

Watch the approval step — this is the routing rule live: because the deal crosses **£50,000**, the Task
Master escalates the approval chain from one approver to two, adding a VP. That's FR5 in action — routing
by value, not by whoever's online.

Now the part I love. The customer comes back with a redline: *extend the warranty from 12 to 24 months.*
No email thread of despair. The liaison agent captures it, the drafting agent re-renders a v2, resends,
and the customer approves. One negotiation round, fully logged.

And finally, the signature agent sends the document for e-signature, confirms completion, files, and —
done. Scroll up and you can read **every agent's action and reasoning** from intake to signing. That's
our audit trail."

> **[DEMO]** Terminal B (webhook mode): `SIGNING_MODE=webhook` + `python main.py --serve`, open browser.

"Now the human side. Same system, one config flip — `SIGNING_MODE=webhook` — and instead of completing
instantly, the case **parks at awaiting_signature**. This is the DocuSign seam. One click simulates the
e-signature provider's webhook callback — the exact integration contract DocuSign uses in production —
and the case completes.

And the human-in-the-loop: if validation really is unpassable, the case doesn't die, it **blocks** with a
decision ID, and this dashboard turns into a decision queue — approve, override, resend, or reject.
Every decision is recorded in the same audit trail."

> **[DEMO]** In the terminal: `python main.py --query "how many cases are complete?"`

"And because the state store that drives the agents is the same one that answers questions: *where is SOW
number one-two-three right now?* — natural language, no dashboard digging."

---

## 4. Honesty — "What's mocked, what's real, why that's the point" (4:15–4:45)

"Let me be explicit about the boundary.

**Real and working today:** the multi-agent orchestration, the state machine, the delegation, the HITL
loop, the webhook contract, the audit trail, the query engine.

**What's simulated:** the inbox, email thread, the DocuSign callback, and approver responses are
in-process mocks. That's deliberate — it makes the demo deterministic, and it's the story you should
judge us on: every mock sits behind a narrow interface (`ports.py`). Swapping `MockESign` for the
DocuSign SDK is a file swap, not an architecture change."

---

## 5. Close — "Why this wins" (4:45–5:00)

"SOW-TaskMaster turns a manual, error-prone, email-based process into an **observable, resumable,
human-supervised machine**. The orchestrator is the centerpiece — not one big LLM call, but a real
multi-agent system with delegation, escalation, and explainability. It runs end-to-end in minutes,
it's honest about what's mocked, and every piece of integration is one clean swap away from production."

**"We'd love to show you the dashboard — and answer your Q&A."**
---

## 6. Q&A cheat sheet

| Likely question | Answer |
|---|---|
| "Why deterministic validation instead of the LLM?" | Pass/fail on money and timelines must be audit-proof. Rules give reproducibility; the LLM writes a human summary around the same numbers. |
| "How would you connect real DocuSign?" | Implement `ESignPort` (`send_for_signature`, `check_status`, `get_signed_document`) with the DocuSign SDK; keep the existing webhook route but receive real envelope events. Nothing in the Task Master changes. |
| "What happens if a case fails validation?" | It blocks (status `blocked`) with a decision ID and appears in the HITL queue. A human can override with notes, or reject. The override is logged as a `Human` timeline entry. |
| "Is state lost if the process restarts?" | No — every case is persisted as JSON per step; `run_lifecycle_from()` resumes from the current stage. The e2e test T3 proves a lost envelope still replays (HTTP 409 + retry). |
| "What would you do with more time?" | Real adapters (Gmail, DocuSign, Slack approvals), a database-backed store, multi-case concurrency + SLA timers per case, and a Cloud Run deployment. |
| "The negotiation loop is scripted — is that cheating?" | The *contract* is real (redline → re-draft → re-approve); the *customer* is scripted so the demo is reliable. The liaison agent code path is identical to a live-email implementation. |