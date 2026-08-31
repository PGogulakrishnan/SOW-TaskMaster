"""
Drafting Agent
===============
Generates SOW draft documents from templates and extracted case data.
Uses Gemini (via the ADK LlmAgent) when USE_REAL_LLM is True, otherwise
fills the template deterministically for the demo.
"""

import re
from datetime import datetime
from pathlib import Path

from google.adk.agents import LlmAgent

from models import SOWCase
from config import USE_REAL_LLM, GEMINI_MODEL
from agents.llm_utils import run_agent


# ─── ADK Agent Definition ────────────────────────────────────────────────────

drafting_agent = LlmAgent(
    name="DraftingAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Generates SOW draft documents from templates and case data.",
    instruction="""You are the Drafting Agent for SOW (Statement of Work) processing.
Your job is to generate a professional SOW document using the provided template
and case data. Fill in every placeholder with the appropriate values from the
case and apply any customer redlines (e.g. an extended warranty period).
Return ONLY the final SOW document text.""",
)


# ─── Agent Function ──────────────────────────────────────────────────────────

def generate_draft(case: SOWCase, template_path: str = "templates/sow_template.txt") -> SOWCase:
    """Generate a SOW draft from the template and case data."""
    # Read the template
    template_file = Path(template_path)
    if template_file.exists():
        template = template_file.read_text(encoding="utf-8")
    else:
        template = _get_inline_template()

    # Determine warranty period (customer redline may extend it)
    # e.g. "extend the warranty from 12 months to 24 months" -> the target
    # period is the LAST number mentioned.
    warranty_months = 12
    for redline in case.customer_redlines:
        if "warranty" in redline.lower():
            months_found = re.findall(r"(\d+)\s*months?", redline.lower())
            if months_found:
                warranty_months = int(months_found[-1])

    # Generate the draft via Gemini when enabled, else fill deterministically
    draft = _generate_with_llm(case, template, warranty_months) if USE_REAL_LLM else None
    if not draft:
        draft = _fill_template(case, template, warranty_months)

    # Update case
    case.draft_sow_text = draft
    case.draft_version += 1

    # Log the action
    case.log_action(
        agent_name="DraftingAgent",
        action="Generate SOW draft from template",
        reasoning=f"Populated SOW template with extracted case data using "
                  f"{'Gemini LLM' if USE_REAL_LLM else 'deterministic fill'}. "
                  f"Warranty set to {warranty_months} months based on customer requirements.",
        result=f"Generated SOW draft v{case.draft_version} ({len(draft)} characters)",
    )

    return case


# ─── Gemini-powered drafting ─────────────────────────────────────────────────

def _generate_with_llm(case: SOWCase, template: str, warranty_months: int):
    """Ask the DraftingAgent (Gemini) to produce the SOW document."""
    prompt = f"""Generate a professional Statement of Work (SOW) document for the case below.
Fill in every {{placeholder}} in the template and apply the customer redlines.
Return ONLY the final document text - no commentary, no markdown fences.

CASE DATA:
- Project title: {case.project_title}
- Customer: {case.customer_name}
- SOW reference: {case.case_id}
- Version: {case.draft_version + 1}
- Date: {datetime.now().strftime("%Y-%m-%d")}
- Scope: {case.scope_description}
- Budget: £{case.budget_gbp or 0:,.2f}
- Delivery timeline: {case.requested_delivery_weeks} weeks
- Warranty period: {warranty_months} months
- Customer redlines: {case.customer_redlines or "none"}

TEMPLATE:
{template}

FINAL SOW:"""
    try:
        text = run_agent(drafting_agent, prompt)
        # Only accept if the LLM actually produced a document (no unfilled placeholders)
        if text and "{{" not in text:
            return text
    except Exception:
        pass
    return None


# ─── Deterministic template fill (demo mode) ─────────────────────────────────

def _fill_template(case: SOWCase, template: str, warranty_months: int) -> str:
    """Fill the SOW template placeholders with case data."""
    draft = template.replace("{{project_title}}", case.project_title or "Unknown Project")
    draft = draft.replace("{{customer_name}}", case.customer_name or "Unknown Customer")
    draft = draft.replace("{{case_id}}", case.case_id)
    draft = draft.replace("{{version}}", str(case.draft_version + 1))
    draft = draft.replace("{{date}}", datetime.now().strftime("%Y-%m-%d"))
    draft = draft.replace("{{scope_description}}", case.scope_description or "No scope provided")
    draft = draft.replace("{{budget_gbp:,.2f}}", f"{case.budget_gbp or 0:,.2f}")
    draft = draft.replace("{{delivery_weeks}}", str(case.requested_delivery_weeks or 12))
    draft = draft.replace("{{warranty_months}}", str(warranty_months))
    return draft


def _get_inline_template() -> str:
    """Fallback inline template if the template file is not found."""
    return """STATEMENT OF WORK

Project: {{project_title}}
Customer: {{customer_name}}
Reference: {{case_id}}
Version: {{version}}
Date: {{date}}

1. SCOPE
{{scope_description}}

2. COMMERCIAL TERMS
Budget: £{{budget_gbp:,.2f}}
Timeline: {{delivery_weeks}} weeks
Warranty: {{warranty_months}} months

3. SIGNATURES
For {{customer_name}}:  ________________
For Company:            ________________
"""