"""
Web App + Dashboard (E1) and mock e-sign webhook (E7)
========================================================
FastAPI app that serves the dashboard and exposes REST endpoints for the
human-in-the-loop decision queue (FR8) and the simulated DocuSign webhook.

Run:  python web_app.py   (serves on http://127.0.0.1:8080)
"""

import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import config
from agents.task_master import TaskMaster
from agents.signature_agent import confirm_signature
from mocks.esign import MockESign
from state_store import StateStore


app = FastAPI(title="SOW-TaskMaster API", version="1.0.0")

# A task master used for starting new cases from the UI.
DEMO_TASK_MASTER = TaskMaster(verbose=False)
STATE = StateStore()
# The same mock e-sign instance the demo task master uses, so the webhook
# can mark envelopes signed.
DEMO_ESIGN = DEMO_TASK_MASTER.esign


SAMPLE_REQUEST = """
From: account_manager@company.com
Subject: New SOW Request — Cloud Migration Project

Hi Team,

We have a new project request from Acme Corporation.

Project: Cloud Migration and Infrastructure Modernisation
Customer: Acme Corporation
Budget: 45000 GBP
Timeline: 16 weeks

Scope: Migrate Acme on-premise infrastructure to AWS, including database
migration, application re-platforming, and staff training.
Please prepare the SOW for review.

Thanks,
Account Manager
"""


# ── pydantic request bodies ────────────────────────────────────────────────

class StartRequest(BaseModel):
    request_text: str = ""


class ResolveRequest(BaseModel):
    decision: str
    notes: str = ""


class QueryRequest(BaseModel):
    question: str


# ── helpers ─────────────────────────────────────────────────────────────────

def _to_json(case) -> dict:
    data = case.model_dump()
    data["timeline"] = [
        {
            "timestamp": e.timestamp,
            "stage": e.stage.value,
            "agent_name": e.agent_name,
            "action": e.action,
            "reasoning": e.reasoning,
            "result": e.result,
        }
        for e in case.timeline
    ]
    data["current_stage"] = case.current_stage.value
    # compact version for list view
    return data


def _list_view(case):
    data = _to_json(case)
    for drop in ("timeline", "raw_request_text", "draft_sow_text", "validation_results"):
        data.pop(drop, None)
    return data


def _stats() -> dict:
    counts = {"active": 0, "blocked": 0, "awaiting_signature": 0, "complete": 0, "rejected": 0}
    for cid in STATE.list_cases():
        case = STATE.load(cid)
        if case and case.status in counts:
            counts[case.status] += 1
    return counts


# ── web routes ──────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dashboard.html"))

@app.get("/api/health")
def health():
    return {"ok": True, "llm": config.USE_REAL_LLM, "model": config.GEMINI_MODEL}


@app.get("/api/cases")
def list_cases(stage: str = "", status: str = ""):
    cases = []
    for cid in STATE.list_cases():
        case = STATE.load(cid)
        if case is None:
            continue
        if stage and case.current_stage.value != stage:
            continue
        if status and case.status != status:
            continue
        cases.append(_list_view(case))
    return {"cases": cases, "stats": _stats()}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    case = STATE.load(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return _to_json(case)


@app.post("/api/cases/start")
def start_case(req: StartRequest = None):
    text = (req.request_text if req and req.request_text else SAMPLE_REQUEST).strip()
    case = DEMO_TASK_MASTER.run_full_lifecycle(text)
    return {"case_id": case.case_id, "status": case.status, "stage": case.current_stage.value}


@app.post("/api/cases/{case_id}/resolve")
def resolve_case(case_id: str, req: ResolveRequest):
    try:
        case = DEMO_TASK_MASTER.resolve_case(case_id, req.decision, req.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"case_id": case.case_id, "status": case.status, "stage": case.current_stage.value}


@app.post("/api/webhooks/esign/{case_id}")
def esign_webhook(case_id: str):
    """Simulated DocuSign callback: marks the envelope signed and completes the case."""
    case = STATE.load(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    if case.status != "awaiting_signature":
        raise HTTPException(status_code=400, detail="Case is not awaiting signature")

    case = confirm_signature(case, DEMO_ESIGN)
    if case.signature_status != "signed":
        # Envelope not found (e.g. server restarted and in-memory envelopes were
        # lost) — keep the case parked so the webhook can be replayed.
        case.status = "awaiting_signature"
        STATE.save(case)
        raise HTTPException(
            status_code=409,
            detail="Signature could not be confirmed (envelope not found); "
            "case remains awaiting_signature",
        )
    case.status = "active"
    # TaskMaster resumes from SIGNING, skipping the webhook gate
    DEMO_TASK_MASTER.run_lifecycle_from(
        case, start_stage=config.SOWStage.SIGNING, resume_after_signature=True
    )
    return {"case_id": case_id, "status": case.status}


@app.post("/api/query")
def ask(req: QueryRequest):
    from query_engine import answer
    return {"answer": answer(req.question, STATE)}


# ── main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"SOW-TaskMaster dashboard: http://{config.WEB_HOST}:{config.WEB_PORT}/")
    print(f"LLM mode: {'Gemini Enterprise/Vertex' if config.USING_GCP_BACKEND else ('Gemini API' if config.GEMINI_API_KEY else 'Mock')}")
    uvicorn.run(app, host=config.WEB_HOST, port=config.WEB_PORT)