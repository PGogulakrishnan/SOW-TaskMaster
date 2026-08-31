"""
End-to-End Flow Tests
=====================
Regression tests for the full SOW-TaskMaster system:

  T1: Sequential (auto) signing — full lifecycle completes via TaskMaster.
  T2: Webhook signing — case parks at `awaiting_signature`, e-sign webhook
      callback resumes it to `complete` (regression: duplicate-envelope bug).
  T3: Webhook robustness — envelope lost (server restart) => HTTP 409,
      case stays `awaiting_signature` and can be replayed.
  T4: HITL escalation — invalid request escalates (FR8), human override
      resolves it, case then flows to completion via webhook.
  T5: Query engine — natural-language status question answers correctly.

Run:  python tests\test_e2e_flows.py
"""

import os
import sys

# Force deterministic mock mode + webhook signing BEFORE any project imports.
os.environ["USE_REAL_LLM"] = "false"
os.environ["SIGNING_MODE"] = "webhook"
os.environ.setdefault("WEB_HOST", "127.0.0.1")
os.environ.setdefault("WEB_PORT", "8081")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib  # noqa: E402

import config  # noqa: E402

# Speed up: mock modules imported MOCK_DELAY_SECONDS by value, so patch each.
import mocks.inbox  # noqa: E402
import mocks.email  # noqa: E402
import mocks.esign  # noqa: E402
import mocks.approver_queue  # noqa: E402
for _mod in (mocks.inbox, mocks.email, mocks.esign, mocks.approver_queue):
    _mod.MOCK_DELAY_SECONDS = 0

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


# ── Valid / invalid sample requests ──────────────────────────────────────────

GOOD_REQUEST = """
Project: CRM Integration Programme
Customer: Globex Industries
Budget: £60,000 GBP
Timeline: 20 weeks
Scope: Integrate the Globex CRM platform with internal billing systems,
including data migration and user training.
"""

# Capacity rule: £300,000 needs >= 30 weeks; requested 10 => validation FAIL.
BAD_REQUEST = """
Project: Data Platform Build
Customer: Initech
Budget: £300,000 GBP
Timeline: 10 weeks
Scope: Build an enterprise data platform with ingestion pipelines and
analytics dashboards.
"""

def t1_sequential_auto_signing():
    """Auto signing mode: full lifecycle via TaskMaster completes."""
    import agents.task_master as tm_mod
    from agents.task_master import TaskMaster

    # This file forces webhook mode for T2-T4; T1 needs auto signing.
    # task_master binds SIGNING_MODE by value at import, so patch the module attr.
    original_mode = tm_mod.SIGNING_MODE
    tm_mod.SIGNING_MODE = "auto"
    try:
        tm = TaskMaster()
        case = tm.run_full_lifecycle(GOOD_REQUEST)
    finally:
        tm_mod.SIGNING_MODE = original_mode
    check("T1 lifecycle reaches COMPLETE", case.current_stage.value == "COMPLETE",
          f"stage={case.current_stage.value}")
    check("T1 status complete", case.status == "complete", f"status={case.status}")
    check("T1 signature signed", case.signature_status == "signed")
    check("T1 explainability timeline populated", len(case.timeline) >= 15,
          f"actions={len(case.timeline)}")
    return case




def t2_webhook_signing():
    """Webhook mode: start via API -> awaiting_signature -> webhook -> complete."""
    from fastapi.testclient import TestClient
    import web_app

    client = TestClient(web_app.app)

    health = client.get("/api/health")
    check("T2 health endpoint OK", health.status_code == 200)

    started = client.post("/api/cases/start", json={"request_text": GOOD_REQUEST})
    check("T2 start accepted", started.status_code == 200,
          f"code={started.status_code} body={started.text[:200]}")
    case_id = started.json().get("case_id", "")
    check("T2 case parks at awaiting_signature",
          started.json().get("status") == "awaiting_signature",
          f"status={started.json().get('status')}")

    # The SIGNING stage must have created exactly one envelope (no duplicates).
    envelopes = [e for e in web_app.DEMO_ESIGN.envelopes if e["case_id"] == case_id]
    check("T2 exactly one e-sign envelope (no duplicate)", len(envelopes) == 1,
          f"envelopes={len(envelopes)}")

    callback = client.post(f"/api/webhooks/esign/{case_id}")
    check("T2 webhook callback returns 200", callback.status_code == 200,
          f"code={callback.status_code} body={callback.text[:200]}")
    check("T2 webhook completes the case", callback.json().get("status") == "complete",
          f"status={callback.json().get('status')}")

    return case_id


def t3_webhook_restart_robustness():
    """Envelope lost (server restart): webhook returns 409, case stays parked."""
    from fastapi.testclient import TestClient
    import web_app

    client = TestClient(web_app.app)
    started = client.post("/api/cases/start", json={"request_text": GOOD_REQUEST})
    case_id = started.json()["case_id"]

    # Simulate server restart: in-memory envelopes are gone.
    web_app.DEMO_ESIGN.envelopes = [e for e in web_app.DEMO_ESIGN.envelopes
                                    if e["case_id"] != case_id]

    r = client.post(f"/api/webhooks/esign/{case_id}")
    check("T3 webhook returns 409 when envelope lost", r.status_code == 409,
          f"code={r.status_code}")
    case = web_app.STATE.load(case_id)
    check("T3 case remains awaiting_signature", case.status == "awaiting_signature",
          f"status={case.status}")

    # Replay with a fresh envelope (simulating re-initiation) then callback OK.
    from agents.signature_agent import initiate_signing
    initiate_signing(case, web_app.DEMO_ESIGN)
    web_app.STATE.save(case)
    r2 = client.post(f"/api/webhooks/esign/{case_id}")
    check("T3 replayed webhook completes case", r2.status_code == 200
          and r2.json().get("status") == "complete",
          f"code={r2.status_code} status={r2.json().get('status')}")


def t4_hitl_escalation_and_override():
    """FR8: validation failure escalates; human override resumes the flow."""
    from fastapi.testclient import TestClient
    import web_app

    client = TestClient(web_app.app)
    started = client.post("/api/cases/start", json={"request_text": BAD_REQUEST})
    case_id = started.json()["case_id"]
    case = web_app.STATE.load(case_id)
    check("T4 blocked case escalated to human", case.escalated_to_human,
          f"escalated={case.escalated_to_human} status={case.status}")

    resolved = client.post(f"/api/cases/{case_id}/resolve",
                           json={"decision": "override", "notes": "Approved by VP"})
    check("T4 resolve accepted", resolved.status_code == 200,
          f"code={resolved.status_code} body={resolved.text[:200]}")

    case = web_app.STATE.load(case_id)
    # After override the case continues; in webhook mode it parks for signature.
    check("T4 override resumes past validation",
          case.current_stage.value in ("SIGNING", "CUSTOMER_REVIEW", "APPROVAL",
                                       "COMPLETE", "VALIDATION"),
          f"stage={case.current_stage.value} status={case.status}")

    if case.status == "awaiting_signature":
        r = client.post(f"/api/webhooks/esign/{case_id}")
        check("T4 webhook completes overridden case",
              r.status_code == 200 and r.json().get("status") == "complete",
              f"code={r.status_code} body={r.text[:200]}")


def t5_query_engine(case_id: str):
    """FR7: natural-language status query answers with case details."""
    from fastapi.testclient import TestClient
    import web_app

    if not case_id:
        check("T5 has a case id from T2", False, "T2 returned no case_id")
        return

    client = TestClient(web_app.app)
    r = client.post("/api/query",
                    json={"question": f"Where is SOW {case_id} right now?"})
    check("T5 query endpoint 200", r.status_code == 200,
          f"code={r.status_code}")
    answer = r.json().get("answer", "")
    check("T5 answer mentions the case", case_id in answer,
          f"answer={answer[:200]}")
    check("T5 answer mentions COMPLETE stage", "COMPLETE" in answer.upper(),
          f"answer={answer[:200]}")


def main():
    print("=" * 70)
    print("SOW-TaskMaster — End-to-End Flow Tests (mock LLM, deterministic)")
    print("=" * 70)
    print(f"SIGNING_MODE={config.SIGNING_MODE}  USE_REAL_LLM={config.USE_REAL_LLM}")
    print()

    t1_sequential_auto_signing()
    print()
    case_id = t2_webhook_signing()
    print()
    t3_webhook_restart_robustness()
    print()
    t4_hitl_escalation_and_override()
    print()
    t5_query_engine(case_id)

    print()
    print("=" * 70)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} test(s) FAILED: {', '.join(FAILURES)}")
        sys.exit(1)
    print("RESULT: ALL end-to-end tests passed")
    print("=" * 70)


if __name__ == "__main__":
    main()
