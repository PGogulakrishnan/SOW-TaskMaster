"""
Intake Agent
=============
Parses incoming SOW requests and extracts structured fields.
Uses Gemini (via the ADK LlmAgent) when USE_REAL_LLM is True,
otherwise falls back to deterministic regex extraction for the demo.
"""

import re

from google.adk.agents import LlmAgent

from models import SOWCase
from config import USE_REAL_LLM, GEMINI_MODEL
from agents.llm_utils import run_agent, parse_json


# ─── ADK Agent Definition ────────────────────────────────────────────────────

intake_agent = LlmAgent(
    name="IntakeAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Extracts structured fields from unstructured SOW requests.",
    instruction="""You are the Intake Agent for SOW (Statement of Work) processing.
Your job is to parse an incoming project request and extract these fields:
- customer_name: The customer/company name (string)
- project_title: The project name or title (string)
- scope_description: A summary of the project scope (string)
- budget_gbp: The total budget in GBP (number, no currency symbol)
- requested_delivery_weeks: The delivery timeline in weeks (integer)

Return ONLY a valid JSON object with exactly those five keys and nothing else.""",
)


# ─── Deterministic fallback (demo mode) ─────────────────────────────────────

def _extract_fields_mock(raw_text: str) -> dict:
    """Deterministic field extraction using simple regex patterns."""
    result = {
        "customer_name": "Unknown Customer",
        "project_title": "Unknown Project",
        "scope_description": raw_text[:200] if raw_text else "No scope provided",
        "budget_gbp": 30000.0,
        "requested_delivery_weeks": 12,
    }

    # Try to extract customer name (require colon, exclude newlines from capture)
    customer_match = re.search(r"(?:customer|client|company):\s*([A-Z][A-Za-z &]+)", raw_text, re.IGNORECASE)
    if customer_match:
        result["customer_name"] = customer_match.group(1).strip()

    # Try to extract project title (require colon to avoid matching "Project" in subject line)
    title_match = re.search(r"(?:project|engagement):\s*([^\n]+)", raw_text, re.IGNORECASE)
    if title_match:
        result["project_title"] = title_match.group(1).strip()

    # Try to extract budget
    budget_match = re.search(r"[£$€]?([\d,]+(?:\.\d{2})?)\s*(K|k)?\s*(?:GBP|USD|EUR|budget)", raw_text, re.IGNORECASE)
    if budget_match:
        amount = float(budget_match.group(1).replace(",", ""))
        # Check if the K suffix was captured in the match (not just anywhere in the text)
        if budget_match.group(2):
            amount *= 1000
        result["budget_gbp"] = amount

    # Try to extract timeline
    timeline_match = re.search(r"(\d+)\s*(?:weeks?|wks?)", raw_text, re.IGNORECASE)
    if timeline_match:
        result["requested_delivery_weeks"] = int(timeline_match.group(1))

    return result


# ─── Gemini-powered extraction ───────────────────────────────────────────────

def _to_float(value):
    """Coerce an LLM-provided value to float, tolerating commas and symbols."""
    if value is None or value == "":
        return None
    cleaned = str(value).replace(",", "").replace("£", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_fields_with_llm(raw_text: str):
    """Extract structured fields using the Gemini-powered ADK agent."""
    prompt = f"""Extract structured fields from the SOW request below and return them as JSON.

Return ONLY valid JSON with exactly these keys:
- "customer_name": string
- "project_title": string
- "scope_description": string
- "budget_gbp": number (GBP, no currency symbol)
- "requested_delivery_weeks": integer (weeks)

SOW REQUEST:
{raw_text}
"""
    try:
        response = run_agent(intake_agent, prompt)
        obj = parse_json(response)
        if not obj:
            return None

        weeks_raw = str(obj.get("requested_delivery_weeks") or "").strip()
        budget = _to_float(obj.get("budget_gbp"))
        if budget is None or not weeks_raw.isdigit():
            # Missing critical fields -> treat as failure so we fall back
            return None

        return {
            "customer_name": str(obj.get("customer_name") or "Unknown Customer"),
            "project_title": str(obj.get("project_title") or "Unknown Project"),
            "scope_description": str(obj.get("scope_description") or "") or None,
            "budget_gbp": budget,
            "requested_delivery_weeks": int(weeks_raw),
        }
    except Exception:
        return None


# ─── Agent Function ──────────────────────────────────────────────────────────

def process_intake(case: SOWCase, raw_request_text: str) -> SOWCase:
    """
    Process an incoming SOW request and populate the case with extracted fields.
    This is the main function called by the Task Master.
    """
    case.raw_request_text = raw_request_text

    if USE_REAL_LLM:
        extracted = _extract_fields_with_llm(raw_request_text)
        if not extracted:
            extracted = _extract_fields_mock(raw_request_text)  # safety fallback
    else:
        extracted = _extract_fields_mock(raw_request_text)

    # Populate case fields
    case.customer_name = extracted.get("customer_name", "Unknown Customer")
    case.project_title = extracted.get("project_title", "Unknown Project")
    case.scope_description = extracted.get("scope_description") or raw_request_text[:200]
    case.budget_gbp = extracted.get("budget_gbp", 30000.0)
    case.requested_delivery_weeks = extracted.get("requested_delivery_weeks", 12)

    # Log the action
    case.log_action(
        agent_name="IntakeAgent",
        action="Extract structured fields from request",
        reasoning=f"Parsed unstructured request text using {'Gemini LLM' if USE_REAL_LLM else 'deterministic parser'} "
                  "to identify customer, project, scope, budget, and timeline.",
        result=f"Extracted: customer={case.customer_name}, budget=£{case.budget_gbp:,.0f}, timeline={case.requested_delivery_weeks} weeks",
    )

    return case