"""
SOW-TaskMaster — Main Entry Point
===================================
Multi-agent SOW (Statement of Work) signing automation system.
Built with Google ADK for the Hackathon Task Master track.

Usage:
    python main.py                       # Run the full demo with sample request
    python main.py --custom              # Run with a custom request (interactive)
    python main.py --scenario high       # High-value deal (>GBP 50K) -> exec approval path
    python main.py --status <id>         # Check status of an existing case
    python main.py --list                # List all cases
    python main.py --blocked             # List cases awaiting a human decision (HITL)
    python main.py --resolve <id> <approve|override|resend|reject> [notes]
    python main.py --query "<question>"  # Natural-language query (Gemini when enabled)
    python main.py --check-llm           # Verify the Gemini credentials work
    python main.py --serve               # Start the web dashboard (FastAPI)
"""

import os
import sys

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force UTF-8 stdout: piped output on Windows defaults to cp1252
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from agents.task_master import TaskMaster
from state_store import StateStore


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
The project includes a 12-month warranty period post-delivery.

Please prepare the SOW for review.

Thanks,
Account Manager
"""

HIGH_VALUE_REQUEST = """
From: account_manager@company.com
Subject: New SOW Request — Enterprise Data Platform

Hi Team,

We have a new project request from Globex Industries.

Project: Enterprise Data Platform Modernisation
Customer: Globex Industries
Budget: 120000 GBP
Timeline: 24 weeks

Scope: Build a unified data platform on Google Cloud: data lake, warehouse,
ETL pipelines, governance, and a self-service analytics layer for 500 users.

Please prepare the SOW for review.

Thanks,
Account Manager
"""


def _print_banner():
    print("=" * 80)
    print("SOW-TaskMaster: Multi-Agent SOW Signing Automation")
    print("Built with Google ADK + Gemini")
    if config.USE_REAL_LLM:
        if config.USING_GCP_BACKEND:
            mode = f"Gemini Enterprise / Vertex AI (project: {config.GCP_PROJECT}, region: {config.GCP_LOCATION})"
        else:
            mode = "Gemini API (Gemini Developer API key)"
        print(f"LLM mode: {mode}")
        print(f"Model:    {config.GEMINI_MODEL}")
    else:
        print("LLM mode: Mock LLM (deterministic demo path)")
        print("No Gemini credentials configured — set .env OR USE_REAL_LLM=false for mock.")
    print("=" * 80)
    print()


# ─── demos ────────────────────────────────────────────────────────────────────

def run_demo():
    _print_banner()
    print("Incoming Request:")
    print("   " + "\n   ".join(SAMPLE_REQUEST.strip().split("\n")))
    print()
    task_master = TaskMaster()
    return task_master.run_full_lifecycle(SAMPLE_REQUEST)


def run_scenario(which: str):
    _print_banner()
    if which == "high":
        print("Scenario: HIGH-VALUE deal — should route to executive approval path.")
        print("   " + "\n   ".join(HIGH_VALUE_REQUEST.strip().split("\n")))
        print()
        task_master = TaskMaster()
        return task_master.run_full_lifecycle(HIGH_VALUE_REQUEST)
    print(f"Unknown scenario: {which} (use 'high')")
    return None


def run_custom():
    _print_banner()
    print("Enter your project request (press Enter twice to finish):")
    lines = []
    while True:
        try:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        except EOFError:
            break
    custom = "\n".join(lines).strip()
    if not custom:
        print("No request provided. Exiting.")
        return
    task_master = TaskMaster()
    return task_master.run_full_lifecycle(custom)


# ─── status / list / HITL ─────────────────────────────────────────────────────

def check_status(case_id: str):
    store = StateStore()
    case = store.load(case_id)
    if case is None:
        print(f"Case {case_id} not found.")
        return
    print()
    print(f"Case Status: {case.case_id}")
    print(f"   Project: {case.project_title}")
    print(f"   Customer: {case.customer_name}")
    print(f"   Stage: {case.current_stage.value}")
    print(f"   Status: {case.status}")
    print(f"   Budget: £{case.budget_gbp:,.2f}" if case.budget_gbp else "   Budget: N/A")
    print(f"   Timeline: {case.requested_delivery_weeks} weeks" if case.requested_delivery_weeks else "   Timeline: N/A")
    if case.escalated_to_human:
        print(f"   HITL: {case.escalation_reason} (decision: {case.decision_id})")
    print()
    if case.timeline:
        print("   Recent Activity:")
        for entry in case.timeline[-5:]:
            print(f"   - [{entry.stage.value}] {entry.agent_name}: {entry.action}")


def list_cases():
    store = StateStore()
    cases = store.list_cases()
    if not cases:
        print("No cases found.")
        return
    print(f"Found {len(cases)} case(s):")
    for cid in cases:
        case = store.load(cid)
        if case:
            mark = " 🔶HITL" if case.escalated_to_human else (" ✅" if case.status == "complete" else "")
            print(f"   {cid} — {case.project_title} ({case.current_stage.value}) [{case.status}]{mark}")


def list_blocked():
    store = StateStore()
    blocked = []
    for cid in store.list_cases():
        case = store.load(cid)
        if case and case.escalated_to_human and case.decision_status == "pending":
            blocked.append(case)
    if not blocked:
        print("No cases awaiting a human decision.")
        return
    print(f"{len(blocked)} case(s) awaiting a human decision:")
    for case in blocked:
        print(f"   {case.case_id} — {case.escalation_reason} (decision: {case.decision_id})")
        print(f"      -> resolve: python main.py --resolve {case.case_id} approve|override|reject")


def resolve_command(case_id: str, decision: str, notes: str = ""):
    task_master = TaskMaster()
    try:
        case = task_master.resolve_case(case_id, decision, notes)
    except ValueError as exc:
        print(f"Error: {exc}")
        return
    print(f"Resolved: {case.case_id} -> status={case.status}, stage={case.current_stage.value}")


# ─── query / LLM checks ───────────────────────────────────────────────────────

def query_db(question: str):
    _print_banner()
    from query_engine import answer
    print(f"Q: {question}")
    print(f"A: {answer(question)}")


def check_llm():
    _print_banner()
    if not (config.GEMINI_API_KEY or config.USING_GCP_BACKEND):
        print("No Gemini credentials configured.")
        print("  Option A (GCP): set GOOGLE_GENAI_USE_ENTERPRISE=1 + GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION in .env")
        print("    then run:  gcloud auth application-default login")
        print("  Option B (key): set GEMINI_API_KEY=<your key> in .env")
        return
    print(f"Testing Gemini with model '{config.GEMINI_MODEL}' ...")
    try:
        from google import genai
        if config.USING_GCP_BACKEND:
            print(f"  backend: Gemini Enterprise / Vertex AI (project {config.GCP_PROJECT}, {config.GCP_LOCATION})")
            client = genai.Client(project=config.GCP_PROJECT, location=config.GCP_LOCATION)
        else:
            client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = client.models.generate_content(model=config.GEMINI_MODEL, contents="Reply with exactly: LLM_OK")
        print("Gemini responded:", getattr(response, "text", "(no text)"))
    except Exception as exc:
        print("Gemini call failed:")
        print(f"   {type(exc).__name__}: {exc}")


def serve():
    import uvicorn
    print(f"Starting dashboard at http://{config.WEB_HOST}:{config.WEB_PORT}/")
    print("Ctrl+C to stop.")
    from web_app import app
    uvicorn.run(app, host=config.WEB_HOST, port=config.WEB_PORT)


# ─── entry point ──────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "--custom":
            run_custom()
        elif cmd == "--scenario" and len(sys.argv) > 2:
            run_scenario(sys.argv[2].lower())
        elif cmd == "--check-llm":
            check_llm()
        elif cmd == "--query" and len(sys.argv) > 2:
            query_db(" ".join(sys.argv[2:]))
        elif cmd == "--resolve" and len(sys.argv) > 3:
            notes = " ".join(sys.argv[4:])
            resolve_command(sys.argv[2], sys.argv[3], notes)
        elif cmd == "--blocked":
            list_blocked()
        elif cmd == "--status" and len(sys.argv) > 2:
            check_status(sys.argv[2])
        elif cmd == "--list":
            list_cases()
        elif cmd == "--serve":
            serve()
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("Usage: python main.py [--custom | --scenario high | --status <id> | --list | --blocked |")
            print("                         --resolve <id> <decision> | --query \"<q>\" | --check-llm | --serve]")
    else:
        run_demo()


if __name__ == "__main__":
    main()