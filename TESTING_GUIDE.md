# 🧪 SOW-TaskMaster — Testing Guide & Video Demo Script

Everything you need to test the deployed system and record a judge-ready demo video.

## 🔗 Live System

| | |
|---|---|
| **Dashboard URL** | https://sow-taskmaster-122458747029.us-central1.run.app |
| **API health** | https://sow-taskmaster-122458747029.us-central1.run.app/api/health |
| **Deployed env** | `USE_REAL_LLM=false` (mock LLM), `SIGNING_MODE=webhook` (sign via webhook button) |
| **Hosting** | Google Cloud Run (`us-central1`), project `my-agent-learning-project-01` |
| **GitHub** | https://github.com/PGogulakrishnan/SOW-TaskMaster |

> ⚠️ **Cloud Run is stateless.** Cases and the mock e-signature envelope live in-process; a cold start or
> new revision resets them. `--max-instances=1` keeps one warm instance, so during a demo the "sign now"
> webhook finds its envelope. If the dashboard shows zero cases, click **Start demo case** to create one.

---

## 1. Automated Test Round (what has been verified)

Run each check below against the live URL. These are the acceptance checks for submission.

### 1.1 Health & dashboard

```powershell
# PowerShell
Invoke-RestMethod "https://sow-taskmaster-122458747029.us-central1.run.app/api/health"
# expect: {"ok":true,"llm":false,"model":"gemini-2.5-flash"}

# open dashboard in a browser (or curl -I)
curl.exe -I https://sow-taskmaster-122458747029.us-central1.run.app/
# expect: HTTP 200
```

### 1.2 Full lifecycle via API (the acceptance path)

```powershell
$base = "https://sow-taskmaster-122458747029.us-central1.run.app"

# (a) Start a demo case — parks at awaiting_signature in webhook mode
$s = Invoke-RestMethod -Method Post -Uri "$base/api/cases/start" -ContentType 'application/json' -Body '{}'
$s.case_id
# expect: {"case_id":"SOW-XXXXXXXX","status":"awaiting_signature","stage":"SIGNING"}

# (b) Simulate the DocuSign webhook callback
Invoke-RestMethod -Method Post -Uri "$base/api/webhooks/esign/$($s.case_id)"
# expect: {"case_id":"SOW-XXXXXXXX","status":"complete"}

# (c) Inspect the case timeline (explainability)
$d = Invoke-RestMethod "$base/api/cases/$($s.case_id)"
$d.status          # complete
$d.current_stage   # COMPLETE
$d.signature_status# signed
$d.timeline.Count  # 21 actions
$d.timeline[0] | ConvertTo-Json   # TaskMaster created the case

# (d) Natural-language status query
Invoke-RestMethod -Method Post -Uri "$base/api/query" -ContentType 'application/json' `
  -Body (@{question="how many cases are complete?"} | ConvertTo-Json)
# expect: "1 of 1 case(s) are complete/signed."
```

### 1.3 What was verified (recorded, pass/fail)

| # | Check | Live expected | Verified |
|---|---|---|---|
| T1 | `/api/health` returns ok + llm=false | `{"ok":true,...}` | ✅ |
| T2 | Dashboard `/` serves HTML 200 | 200, title "SOW-TaskMaster" | ✅ |
| T3 | Start case → parks `awaiting_signature` (webhook gate) | `SIGNING` stage | ✅ |
| T4 | Webhook `/api/webhooks/esign/{id}` → `complete` | `COMPLETE` | ✅ |
| T5 | Case detail: signature signed, 21 actions w/ reasoning | `signed`, count>0 | ✅ |
| T6 | `/api/query` answers natural language | "1 of 1 complete" | ✅ |
| T7 | Local e2e suite (mock LLM) | ALL PASS | ✅ |
| T8 | Local drafting/llm_utils tests | PASS | ✅ |
---

## 2. 🎥 Video Testing Script (record this)

**Total ≈ 4–5 minutes.** One screen, no cuts needed. Record at 1080p, microphone at a comfortable level,
have the dashboard open at the start.

### Scene 1 — Setup & architecture (00:00–00:45)

- Open **GitHub repo** (`https://github.com/PGogulakrishnan/SOW-TaskMaster`) — show README top: title,
  the FR/NFR features table, and scroll to the **two Mermaid diagrams**.
- **Say:** "This is SOW-TaskMaster — a multi-agent SOW signing automation built with Google ADK and Gemini.
  One Task Master orchestrator, seven supporting agents, resumable state machine, human-in-the-loop
  decisions. Every agent decision is logged with its reasoning."

### Scene 2 — Live deployment, end-to-end (00:45–03:00)

- Open the **live dashboard**: https://sow-taskmaster-122458747029.us-central1.run.app
- Click **"Start demo case"**. Watch the case appear in the grid (`active` → moving through stages).
- The case should **park at `awaiting_signature`** (webhook mode). **Say:** "The SOW has been drafted,
  validated, approved internally, and sent to the customer. One redline round happened — the customer
  requested an extended warranty — and the draft was regenerated at version two. Now the case is parked,
  waiting for the e-signature provider to confirm — exactly like DocuSign in production."
- Click the case row → scroll the **"Agent action timeline"** (21 actions, expand if collapsed).
  Click a couple of entries to show **reasoning** text. **Say:** "Every action — who did what and why.
  This is the audit trail."
- Click **"Simulate DocuSign webhook (sign now)"**.
- The case turns `COMPLETE`. **Say:** "The webhook callback marks the envelope signed, files the final
  SOW, and triggers project kickoff."
- Show the **"Final SOW draft"** section (click to expand) — scroll through the document, point at
  the **24-month warranty** and the signature block. **Say:** "The customer's redline is reflected in
  the final contract."

### Scene 3 — Human-in-the-loop (03:00–03:45)

- Trigger (or note) a blocked case. From the live API:
  ```powershell
  $bad = @{ request_text = "Project: Rushed Deal`nCustomer: Test Corp`nBudget: 200 GBP`nTimeline: 200 weeks" } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "https://sow-taskmaster-122458747029.us-central1.run.app/api/cases/start" -ContentType 'application/json' -Body $bad
  ```
  Expected: case is **blocked** (escalated) at a human decision point.
- **Say:** "When automation can't resolve something — failed validation, rejected approval — the Task
  Master escalates to a human with a decision ID instead of guessing. That's FR8: humans at genuine
  decision points only."

### Scene 4 — Natural-language querying (03:45–04:15)

- Back in the dashboard, use the query box (or):
  ```powershell
  Invoke-RestMethod -Method Post -Uri "https://sow-taskmaster-122458747029.us-central1.run.app/api/query" `
    -ContentType 'application/json' -Body (@{question="where is SOW #SOW-XXXXXXXX right now?"} | ConvertTo-Json)
  ```
  Replace `SOW-XXXXXXXX` with the parked/complete case id you created.
- **Say:** "The same state store that drives the agents also answers natural-language questions — that's
  'where is my SOW right now?' for the whole business."

### Scene 5 — Wrap-up (04:15–04:45)

- **Say:** "Production-ready STOP: the multi-agent orchestration, state machine, delegation, HITL queue,
  webhook contract, audit trail, and query engine are real. What's simulated — and clearly marked — are
  the inbox, email thread, the DocuSign callback, and approver responses, all behind clean `ports.py`
  interfaces so a real DocuSign or Gmail adapter swaps in without touching the orchestrator."
- Show the **"Mocked vs Real"** table in the README for 5 seconds, end recording.

---

## 3. Common gotchas during recording

| Symptom | Cause | Fix |
|---|---|---|
| Dashboard shows 0 cases | Cold start / new revision wiped in-memory state | Click **Start demo case** first |
| "Sign now" returns 400 | Case already complete / not awaiting signature | Start a **fresh** case |
| Timeline collapsed | New default for cases/draft sections | Click the header bar to expand |
| Sluggish first click | Cloud Run cold start (~5–20 s) | Keep the instance warm before recording; re-click |

---

## 4. Re-run the local tests (optional, for your records)

```powershell
cd C:\Users\gogul\Lab\SOW-TaskMaster
$env:USE_REAL_LLM="false"
python tests\test_e2e_flows.py        # T1–T5 (lifecycle, webhook, 409 replay, HITL, query)
python tests\test_drafting_redline.py
python tests\test_llm_utils.py
```

Local runs use `data/cases/` for state and don't touch the live deployment.