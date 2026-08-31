"""
Validation Agent
=================
Runs automated commercial and timeline/delivery-feasibility checks.
Checks are deterministic (rule-based) for demo reliability (NFR1); when the
real LLM is enabled, Gemini produces a short executive summary around them.
"""

import json

from google.adk.agents import LlmAgent

from models import SOWCase
from config import (
    MIN_MARGIN_PERCENT,
    MAX_DELIVERY_WEEKS,
    WEEKS_PER_10K_GBP,
    USE_REAL_LLM,
    GEMINI_MODEL,
)
from agents.llm_utils import run_agent


validation_agent = LlmAgent(
    name="ValidationAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Runs commercial and timeline validation checks on SOW drafts.",
    instruction="""You are the Validation Agent for SOW (Statement of Work) processing.
Your job is to produce a clear, human-friendly executive summary of the
automated validation checks: what passed, what failed or was flagged, and
why it matters for the delivery manager. Keep it to 3-4 sentences.""",
)


# ─── summaries ───────────────────────────────────────────────────────────────

def _default_summary(case: SOWCase, results: dict) -> str:
    passed = sum(1 for r in results.values() if r["passed"])
    total = len(results)
    lines = [
        f"{passed}/{total} automated checks passed for SOW {case.case_id} "
        f"({case.project_title or 'untitled'})."
    ]
    for _, r in results.items():
        state = "PASS" if r["passed"] else "FLAG"
        lines.append(f"{state} - {r['check_name']}: {r['reasoning']}")
    return "\n".join(lines)


def _summarize_with_llm(case: SOWCase) -> str:
    prompt = (
        "Summarise these SOW validation results for a delivery manager in 3-4 sentences:\n"
        f"CASE: {case.case_id} ({case.project_title}), budget £{case.budget_gbp:,.0f}, "
        f"{case.requested_delivery_weeks} weeks requested.\n"
        f"RESULTS:\n{json.dumps(case.validation_results, indent=2)}\n"
        "SUMMARY:"
    )
    try:
        text = run_agent(validation_agent, prompt)
        return text[:800] if text else ""
    except Exception:
        return ""


# ─── agent function ───────────────────────────────────────────────────────────

def run_validation(case: SOWCase) -> SOWCase:
    """Run all deterministic validation checks; enrich summary via Gemini."""
    results = {}
    all_passed = True

    budget = case.budget_gbp or 0
    estimated_cost = budget * 0.70
    margin = budget - estimated_cost
    margin_percent = (margin / budget * 100) if budget > 0 else 0
    margin_check = {
        "check_name": "Commercial Margin",
        "rule": f"Margin must be >= {MIN_MARGIN_PERCENT}%",
        "actual_value": f"{margin_percent:.1f}%",
        "threshold": f"{MIN_MARGIN_PERCENT}%",
        "passed": margin_percent >= MIN_MARGIN_PERCENT,
        "reasoning": f"Estimated cost £{estimated_cost:,.0f} vs budget £{budget:,.0f} = {margin_percent:.1f}% margin. "
                     f"{'Meets' if margin_percent >= MIN_MARGIN_PERCENT else 'Below'} minimum threshold.",
    }
    results["commercial_margin"] = margin_check
    if not margin_check["passed"]:
        all_passed = False

    delivery_weeks = case.requested_delivery_weeks or 0
    timeline_check = {
        "check_name": "Timeline Feasibility",
        "rule": f"Delivery must be <= {MAX_DELIVERY_WEEKS} weeks",
        "actual_value": f"{delivery_weeks} weeks",
        "threshold": f"{MAX_DELIVERY_WEEKS} weeks",
        "passed": delivery_weeks <= MAX_DELIVERY_WEEKS,
        "reasoning": f"Requested delivery in {delivery_weeks} weeks. "
                     f"{'Within' if delivery_weeks <= MAX_DELIVERY_WEEKS else 'Exceeds'} max of {MAX_DELIVERY_WEEKS} weeks.",
    }
    results["timeline_feasibility"] = timeline_check
    if not timeline_check["passed"]:
        all_passed = False

    min_weeks_needed = (budget / 10000) * WEEKS_PER_10K_GBP
    capacity_check = {
        "check_name": "Capacity Check",
        "rule": f"Need >= {WEEKS_PER_10K_GBP} week(s) per £10K budget",
        "actual_value": f"{delivery_weeks} weeks for £{budget:,.0f}",
        "threshold": f"{min_weeks_needed:.0f} weeks minimum",
        "passed": delivery_weeks >= min_weeks_needed,
        "reasoning": f"Budget of £{budget:,.0f} requires at least {min_weeks_needed:.0f} weeks. "
                     f"Requested {delivery_weeks} weeks — "
                     f"{'sufficient' if delivery_weeks >= min_weeks_needed else 'insufficient'} capacity.",
    }
    results["capacity_check"] = capacity_check
    if not capacity_check["passed"]:
        all_passed = False

    case.validation_results = results
    case.validation_passed = all_passed
    if USE_REAL_LLM:
        case.validation_summary = _summarize_with_llm(case) or _default_summary(case, results)
    else:
        case.validation_summary = _default_summary(case, results)

    passed_count = sum(1 for r in results.values() if r["passed"])
    total_count = len(results)
    case.log_action(
        agent_name="ValidationAgent",
        action="Run automated validation checks",
        reasoning=f"Executed {total_count} rule-based checks: commercial margin, timeline feasibility, and capacity. "
                 f"{passed_count}/{total_count} passed.",
        result=f"Validation {'PASSED' if all_passed else 'FLAGGED'} — {passed_count}/{total_count} checks passed.",
    )
    return case