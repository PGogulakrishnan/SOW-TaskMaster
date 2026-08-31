"""
Notifier Agent
===============
Sends status updates to stakeholders throughout the SOW lifecycle.
Messages can be polished by Gemini when the real LLM is enabled.
"""

from google.adk.agents import LlmAgent
from models import SOWCase
from config import USE_REAL_LLM, GEMINI_MODEL
from agents.llm_utils import run_agent


notifier_agent = LlmAgent(
    name="NotifierAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Sends status updates and notifications to stakeholders.",
    instruction="""You are the Notifier Agent for SOW (Statement of Work) processing.
Rewrite the given status update into one polished notification line for
stakeholders (Slack/email style). Keep it under 40 words.
Return ONLY the notification text - no markdown fences.""",
)


def _polish(case: SOWCase, draft_message: str) -> str:
    """Ask Gemini to polish a notification; fall back to the draft on failure."""
    if not USE_REAL_LLM:
        return draft_message
    try:
        text = run_agent(
            notifier_agent,
            f"Case {case.case_id}, stage {case.current_stage.value}: {draft_message}\nNotification:",
        )
        return text[:300].strip() if text else draft_message
    except Exception:
        return draft_message


def notify_stakeholders(case: SOWCase, message: str, recipients: list[str] = None) -> SOWCase:
    """Log a stakeholder notification on the case timeline."""
    if recipients is None:
        recipients = ["account_manager@company.com", "delivery_team@company.com"]
    notification = {
        "case_id": case.case_id,
        "stage": case.current_stage.value,
        "status": case.status,
        "message": message,
        "recipients": recipients,
        "timestamp": case.updated_at,
    }
    # In a real system this sends via Slack/email; for the demo it is logged.
    case.log_action(
        agent_name="NotifierAgent",
        action="Send stakeholder notification",
        reasoning=f"Status update for {case.current_stage.value}: {message}",
        result=f"Notification sent to {len(recipients)} recipient(s)",
    )
    return case


def notify_stage_transition(case: SOWCase, old_stage: str, new_stage: str) -> SOWCase:
    """Notify stakeholders about a stage transition (optionally Gemini-polished)."""
    draft = f"SOW #{case.case_id} ({case.project_title}) has moved from {old_stage} to {new_stage}."
    return notify_stakeholders(case, _polish(case, draft))


def notify_completion(case: SOWCase) -> SOWCase:
    """Notify all stakeholders that the SOW is fully signed and complete."""
    draft = (
        f"SOW #{case.case_id} ({case.project_title}) is now FULLY SIGNED! "
        f"Project kickoff can begin. Budget: £{case.budget_gbp:,.0f}, "
        f"Timeline: {case.requested_delivery_weeks} weeks."
    )
    return notify_stakeholders(case, _polish(case, draft))