"""
Query Engine (E5)
==================
Natural-language questions over the case store - "where is SOW #123?" style.
When the real LLM is enabled, Gemini answers from a compact JSON corpus of
all cases; otherwise a deterministic fallback answers case lookups and
basic stats (so FR7 works in mock demo mode too).
"""

import json

from google.adk.agents import LlmAgent

from config import USE_REAL_LLM, GEMINI_MODEL
from state_store import StateStore
from agents.llm_utils import run_agent


query_agent = LlmAgent(
    name="QueryAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Answers natural-language questions about SOW cases from a JSON corpus.",
    instruction="""You are the Query Agent for SOW-TaskMaster.
You are given a JSON corpus of SOW cases and a question. Answer using only
the corpus. Be concise and factual; cite case IDs and figures when possible.
If the corpus cannot answer the question, say so clearly.""",
)


def _build_corpus(store: StateStore = None) -> list[dict]:
    """Compact JSON-friendly view of every case for the LLM."""
    store = store or StateStore()
    rows = []
    for case_id in store.list_cases():
        case = store.load(case_id)
        if case is None:
            continue
        rows.append(
            {
                "case_id": case.case_id,
                "project": case.project_title,
                "customer": case.customer_name,
                "budget_gbp": case.budget_gbp,
                "delivery_weeks": case.requested_delivery_weeks,
                "stage": case.current_stage.value,
                "status": case.status,
                "approval_status": case.approval_status,
                "customer_approved": case.customer_approved,
                "signed_at": case.signed_at,
                "escalated": case.escalated_to_human,
                "redlines": case.customer_redlines,
            }
        )
    return rows


def _fallback_answer(rows: list[dict], question: str) -> str:
    q = question.lower()
    if not rows:
        return "There are no SOW cases in the store yet."
    # Case-specific lookup (FR7): "where is SOW #123?" works without an LLM.
    mentioned = [r for r in rows if r["case_id"].lower() in q]
    if mentioned:
        parts = []
        for r in mentioned:
            detail = (
                f"{r['case_id']} ({r['project'] or 'Unknown project'}) for "
                f"{r['customer'] or 'Unknown customer'} is at stage "
                f"{r['stage']} with status '{r['status']}'"
            )
            if r.get("budget_gbp") is not None:
                detail += f", budget £{r['budget_gbp']:,.0f}"
            if r.get("delivery_weeks") is not None:
                detail += f", delivery {r['delivery_weeks']} weeks"
            if r.get("signed_at"):
                detail += f"; signed at {r['signed_at']}"
            if r.get("escalated"):
                detail += "; ESCALATED to a human for a decision"
            parts.append(detail + ".")
        return " ".join(parts)
    if "complete" in q or "signed" in q:
        n = sum(1 for r in rows if r["status"] == "complete")
        return f"{n} of {len(rows)} case(s) are complete/signed."
    if "blocked" in q or "escalat" in q:
        n = sum(1 for r in rows if r["status"] == "blocked")
        return f"{n} of {len(rows)} case(s) are blocked awaiting a human decision."
    if "stage" in q:
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["stage"]] = counts.get(r["stage"], 0) + 1
        return "Case counts by stage: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    if "total" in q or "how many" in q:
        return f"There are {len(rows)} SOW case(s) in the store."
    return (
        "Enable USE_REAL_LLM for full natural-language answers, or ask a more "
        "specific question like 'how many cases are complete?'."
    )


def answer(question: str, store: StateStore = None) -> str:
    """Answer a natural-language question about the case store."""
    rows = _build_corpus(store or StateStore())
    if not USE_REAL_LLM:
        return _fallback_answer(rows, question)
    corpus = json.dumps(rows, indent=2, default=str)
    prompt = f"CORPUS:\n{corpus}\n\nQUESTION: {question}\nANSWER:"
    try:
        text = run_agent(query_agent, prompt)
        return text.strip() if text else _fallback_answer(rows, question)
    except Exception:
        return _fallback_answer(rows, question)