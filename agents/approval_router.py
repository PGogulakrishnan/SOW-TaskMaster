"""
Approval Router Agent
======================
Determines who needs to approve based on deal value/risk and tracks responses.
"""

from models import SOWCase
from config import (
    APPROVAL_THRESHOLD_GBP,
    STANDARD_APPROVERS,
    EXECUTIVE_APPROVERS,
    USE_REAL_LLM,
    GEMINI_MODEL,
)
from mocks.approver_queue import MockApproverQueue

# Import ADK
from google.adk.agents import LlmAgent



# ─── ADK Agent Definition ────────────────────────────────────────────────────

approval_router_agent = LlmAgent(
    name="ApprovalRouterAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Routes SOW for internal approval based on deal value and risk.",
    instruction="""You are the Approval Router Agent for SOW (Statement of Work) processing.
Your job is to determine who needs to approve the SOW based on deal value:
- Deals under £50,000: delivery_manager approval only
- Deals £50,000 and over: delivery_manager + vp_delivery approval
Route the approval and track responses.""",
    output_key="approval_result",
)


# ─── Agent Function ──────────────────────────────────────────────────────────

def route_for_approval(case: SOWCase, approver_queue: MockApproverQueue) -> SOWCase:
    """
    Determine approvers and route the SOW for internal approval.
    This is the main function called by the Task Master.
    """
    budget = case.budget_gbp or 0
    
    # Determine approvers based on threshold
    if budget >= APPROVAL_THRESHOLD_GBP:
        approvers = EXECUTIVE_APPROVERS.copy()
        routing_reason = (
            f"Deal value £{budget:,.0f} meets/exceeds £{APPROVAL_THRESHOLD_GBP:,} threshold. "
            f"Requires executive approval from: {', '.join(approvers)}"
        )
    else:
        approvers = STANDARD_APPROVERS.copy()
        routing_reason = (
            f"Deal value £{budget:,.0f} is below £{APPROVAL_THRESHOLD_GBP:,} threshold. "
            f"Standard approval from: {', '.join(approvers)}"
        )
    
    case.approvers = approvers
    case.approval_status = "pending"
    
    # Send approval requests
    for approver in approvers:
        approver_queue.request_approval(
            approver=approver,
            case_id=case.case_id,
            details={
                "project_title": case.project_title,
                "customer_name": case.customer_name,
                "budget_gbp": case.budget_gbp,
                "delivery_weeks": case.requested_delivery_weeks,
            },
        )
    
    # Log the action
    case.log_action(
        agent_name="ApprovalRouterAgent",
        action="Route SOW for internal approval",
        reasoning=routing_reason,
        result=f"Approval requested from {len(approvers)} approver(s): {', '.join(approvers)}",
    )
    
    return case


def collect_approvals(case: SOWCase, approver_queue: MockApproverQueue) -> SOWCase:
    """
    Collect approval responses from all approvers.
    This is called after route_for_approval to simulate receiving responses.
    """
    all_approved = True
    
    for approver in case.approvers:
        approval_id = f"appr_{case.case_id}_{approver}"
        response = approver_queue.get_approver_response(approval_id)
        
        if response.get("status") == "approve":
            case.approval_responses[approver] = "approved"
        else:
            case.approval_responses[approver] = "rejected"
            all_approved = False
    
    case.approval_status = "approved" if all_approved else "rejected"
    
    # Log the action
    case.log_action(
        agent_name="ApprovalRouterAgent",
        action="Collect approval responses",
        reasoning=f"Collected responses from {len(case.approvers)} approver(s). "
                 f"All approved: {all_approved}.",
        result=f"Approval status: {case.approval_status}",
    )
    
    return case