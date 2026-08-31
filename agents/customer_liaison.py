"""
Customer Liaison Agent
=======================
Handles customer-facing communication, including the redline/negotiation loop.
Emails are drafted by Gemini when the real LLM is enabled.
"""

from google.adk.agents import LlmAgent
from models import SOWCase
from mocks.email import MockEmailThread
from config import USE_REAL_LLM, GEMINI_MODEL
from agents.llm_utils import run_agent


customer_liaison_agent = LlmAgent(
    name="CustomerLiaisonAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Manages customer communication and handles redline negotiations.",
    instruction="""You are the Customer Liaison Agent for SOW (Statement of Work) processing.
Your job is to write professional, warm and concise customer emails.
Return your reply as: SUBJECT on the first line, then the email BODY.
Do not add markdown fences.""",
)


# ─── email composition ───────────────────────────────────────────────────────

def _compose_email(case: SOWCase, template_subject: str, template_body: str):
    """Gemini-composed email when the real LLM is enabled; template otherwise."""
    if not USE_REAL_LLM:
        return template_subject, template_body
    prompt = (
        "Compose a customer email for the case below.\n"
        f"CUSTOMER: {case.customer_name}\nPROJECT: {case.project_title}\n"
        f"REFERENCE: {case.case_id} (version {case.draft_version})\n"
        f"BUDGET: £{case.budget_gbp:,.0f}\nTIMELINE: {case.requested_delivery_weeks} weeks\n"
        f"REDLINES: {case.customer_redlines or 'none'}\n"
        "Return SUBJECT on the first line, then the BODY. No markdown fences.\n"
        "SUBJECT:"
    )
    try:
        raw = run_agent(customer_liaison_agent, prompt)
        if raw:
            lines = raw.split("\n", 1)
            subject = lines[0].strip().strip('"')
            body = lines[1].strip() if len(lines) > 1 else raw
            if subject.lower().startswith("subject:"):
                subject = subject.split(":", 1)[1].strip()
            if subject and body:
                return subject, body
    except Exception:
        pass
    return template_subject, template_body


# ─── agent functions ──────────────────────────────────────────────────────────

def send_for_customer_review(case: SOWCase, email_thread: MockEmailThread) -> SOWCase:
    """Send the SOW draft to the customer for review."""
    template_subject = f"SOW for Review: {case.project_title} (Ref: {case.case_id})"
    template_body = (
        f"Dear {case.customer_name} Team,\n\n"
        f"Please find attached the Statement of Work for \"{case.project_title}\".\n\n"
        "Key Details:\n"
        f"- Budget: £{case.budget_gbp:,.2f}\n"
        f"- Delivery Timeline: {case.requested_delivery_weeks} weeks\n"
        "- Warranty: 12 months\n\n"
        "Please review and let us know if you have any questions or require any changes.\n\n"
        "Best regards,\nSOW Automation Team"
    )
    subject, body = _compose_email(case, template_subject, template_body)
    email_thread.send(subject=subject, body=body)
    case.customer_review_status = "pending"
    case.log_action(
        agent_name="CustomerLiaisonAgent",
        action="Send SOW draft to customer for review",
        reasoning=f"SOW draft v{case.draft_version} is internally approved; email "
                  f"composed by {'Gemini' if USE_REAL_LLM else 'template'}.",
        result=f"Email '{subject}' sent to customer with SOW draft v{case.draft_version}",
    )
    return case


def handle_customer_response(case: SOWCase, email_thread: MockEmailThread) -> SOWCase:
    """Handle the customer's response — approval or redline request."""
    reply = email_thread.receive_reply()
    if reply.get("response_type") == "redline":
        redline_text = reply.get("redline_request", "No specific changes mentioned.")
        case.customer_redlines.append(redline_text)
        case.customer_review_status = "redline"
        case.log_action(
            agent_name="CustomerLiaisonAgent",
            action="Process customer redline request",
            reasoning=f"Customer requested changes: {redline_text}. Update the draft and resend.",
            result=f"Redline recorded: {redline_text}",
        )
    elif reply.get("response_type") == "approve":
        case.customer_review_status = "approved"
        case.customer_approved = True
        case.log_action(
            agent_name="CustomerLiaisonAgent",
            action="Record customer approval",
            reasoning="Customer reviewed and approved the SOW. No further changes needed.",
            result="Customer approved the SOW — ready for signing.",
        )
    return case


def send_updated_draft(case: SOWCase, email_thread: MockEmailThread) -> SOWCase:
    """Send an updated SOW draft after incorporating redlines."""
    template_subject = f"Updated SOW for Review: {case.project_title} (Ref: {case.case_id})"
    template_body = (
        f"Dear {case.customer_name} Team,\n\n"
        "Thank you for your feedback. We have updated the SOW to address your request:\n\n"
        "Change Made:\n"
        f"- {case.customer_redlines[-1] if case.customer_redlines else 'Updated per your request'}\n\n"
        "Please review the updated SOW and let us know if this is acceptable.\n\n"
        "Best regards,\nSOW Automation Team"
    )
    subject, body = _compose_email(case, template_subject, template_body)
    email_thread.send(subject=subject, body=body)
    case.log_action(
        agent_name="CustomerLiaisonAgent",
        action="Send updated SOW draft after redline",
        reasoning="Incorporated customer redline and resent for final approval.",
        result=f"Updated SOW draft v{case.draft_version} sent to customer ('{subject}')",
    )
    return case