"""
SOW-TaskMaster Data Models
============================
Pydantic models for the SOW signing automation system.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

from config import SOWStage


class AgentAction(BaseModel):
    """A single action taken by an agent, logged for explainability."""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    agent_name: str
    action: str
    reasoning: str
    result: str
    stage: SOWStage


class Escalation(BaseModel):
    """A human-in-the-loop decision request (FR8)."""
    decision_id: str
    stage: str
    reason: str
    raised_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    decision: Optional[str] = None          # approve | override | resend | reject
    notes: Optional[str] = None
    resolved_at: Optional[str] = None


class SOWCase(BaseModel):
    """The full state of a SOW case as it moves through the lifecycle."""
    case_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Current state
    current_stage: SOWStage = SOWStage.INTAKE
    # active | blocked | awaiting_signature | complete | rejected
    status: str = "active"

    # Intake data (populated by IntakeAgent)
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    scope_description: Optional[str] = None
    budget_gbp: Optional[float] = None
    requested_delivery_weeks: Optional[int] = None
    raw_request_text: Optional[str] = None

    # Drafting data (populated by DraftingAgent)
    draft_sow_text: Optional[str] = None
    draft_version: int = 0

    # Validation results (populated by ValidationAgent)
    validation_results: dict[str, Any] = Field(default_factory=dict)
    validation_passed: bool = False
    validation_summary: str = ""

    # Approval data (populated by ApprovalRouterAgent)
    approvers: list[str] = Field(default_factory=list)
    approval_status: Optional[str] = None
    approval_responses: dict[str, str] = Field(default_factory=dict)

    # Customer review data (populated by CustomerLiaisonAgent)
    customer_review_status: Optional[str] = None
    customer_redlines: list[str] = Field(default_factory=list)
    customer_approved: bool = False

    # Signature data (populated by SignatureAgent)
    signature_status: Optional[str] = None
    signed_at: Optional[str] = None

    # Full timeline of all agent actions (explainability)
    timeline: list[AgentAction] = Field(default_factory=list)

    # Blockers / human-in-the-loop escalations
    blockers: list[str] = Field(default_factory=list)
    escalations: list[Escalation] = Field(default_factory=list)
    escalated_to_human: bool = False
    escalation_reason: Optional[str] = None
    escalation_stage: Optional[str] = None
    decision_id: Optional[str] = None
    decision_status: Optional[str] = None

    def log_action(self, agent_name: str, action: str, reasoning: str, result: str):
        """Helper to log an agent action to the timeline."""
        entry = AgentAction(
            agent_name=agent_name,
            action=action,
            reasoning=reasoning,
            result=result,
            stage=self.current_stage,
        )
        self.timeline.append(entry)
        self.updated_at = datetime.now().isoformat()