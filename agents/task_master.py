"""
Task Master Agent (Orchestrator)
=================================
Owns the SOW state machine, delegates to supporting agents, handles
human-in-the-loop escalations (FR8), and maintains the audit trail.
The lifecycle is resumable: every stage is a step, and a blocked case
can be resolved by a human and continued from where it stopped.
"""

import uuid
from datetime import datetime

from google.adk.agents import LlmAgent

from models import Escalation, SOWCase
from config import SOWStage, STAGE_ORDER, USE_REAL_LLM, GEMINI_MODEL, SIGNING_MODE
from state_store import StateStore

from agents.intake_agent import process_intake
from agents.drafting_agent import generate_draft
from agents.validation_agent import run_validation
from agents.approval_router import route_for_approval, collect_approvals
from agents.customer_liaison import (
    send_for_customer_review,
    handle_customer_response,
    send_updated_draft,
)
from agents.signature_agent import initiate_signing, confirm_signature
from agents.notifier_agent import notify_stage_transition, notify_completion

from mocks.email import MockEmailThread
from mocks.esign import MockESign
from mocks.approver_queue import MockApproverQueue


task_master_agent = LlmAgent(
    name="TaskMasterAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Orchestrates the full SOW signing lifecycle, delegating to supporting agents.",
    instruction="""You are the Task Master Agent for SOW (Statement of Work) signing automation.
You orchestrate the full lifecycle across 6 stages:
1. INTAKE - Parse incoming request
2. DRAFTING - Generate SOW from template
3. VALIDATION - Run commercial and timeline checks
4. APPROVAL - Route to stakeholders for sign-off
5. CUSTOMER_REVIEW - Send to customer, handle redlines
6. SIGNING - Countersign, file, kickoff
At each stage, delegate to the appropriate supporting agent.
Escalate to a human when a decision cannot be automated.
Maintain an audit trail of all actions.""",
)


# Stage to resume at when a human overrides an escalation at a given stage
_NEXT_STAGE_AFTER = {
    SOWStage.VALIDATION: SOWStage.APPROVAL,
    SOWStage.APPROVAL: SOWStage.CUSTOMER_REVIEW,
    SOWStage.CUSTOMER_REVIEW: SOWStage.SIGNING,
}


class TaskMaster:
    """The Task Master orchestrator. Owns the state machine and delegation."""

    def __init__(self, state_store: StateStore = None, verbose: bool = True):
        self.state_store = state_store or StateStore()
        self.esign = MockESign()
        self.approver_queue = MockApproverQueue()
        self.verbose = verbose

    def _out(self, msg: str = ""):
        if self.verbose:
            print(msg)

    # ── creation / helpers ────────────────────────────────────────────────────

    def create_case(self, raw_request_text: str) -> SOWCase:
        case_id = f"SOW-{uuid.uuid4().hex[:8].upper()}"
        case = SOWCase(case_id=case_id)
        case.raw_request_text = raw_request_text
        case.log_action(
            agent_name="TaskMaster",
            action="Create new SOW case",
            reasoning="New SOW request received. Creating tracked case with unique ID.",
            result=f"Case {case_id} created and ready for processing.",
        )
        self.state_store.save(case)
        return case

    def advance_stage(self, case: SOWCase, new_stage: SOWStage) -> SOWCase:
        old_stage = case.current_stage
        case.current_stage = new_stage
        case.updated_at = datetime.now().isoformat()
        notify_stage_transition(case, old_stage.value, new_stage.value)
        self.state_store.save(case)
        return case

    def escalate(self, case: SOWCase, reason: str, stage: SOWStage) -> SOWCase:
        escalation = Escalation(
            decision_id=f"DEC-{uuid.uuid4().hex[:8].upper()}",
            stage=stage.value,
            reason=reason,
        )
        case.escalations.append(escalation)
        case.status = "blocked"
        case.escalated_to_human = True
        case.escalation_reason = reason
        case.escalation_stage = stage.value
        case.decision_id = escalation.decision_id
        case.decision_status = "pending"
        case.blockers.append(reason)
        case.log_action(
            agent_name="TaskMaster",
            action="Escalate to human",
            reasoning=f"Cannot auto-resolve at {stage.value}: {reason}. Routing to human decision queue.",
            result=f"Case blocked, awaiting human decision ({escalation.decision_id}).",
        )
        self.state_store.save(case)
        return case

    # ── stage steps ───────────────────────────────────────────────────────────

    def _do_intake(self, case: SOWCase) -> SOWCase:
        self._out("📋 Stage 1: INTAKE")
        self._out(f"   Case ID: {case.case_id}")
        case = process_intake(case, case.raw_request_text)
        self._out(f"   ✅ {case.timeline[-1].result}")
        self._out()
        return case

    def _do_drafting(self, case: SOWCase) -> SOWCase:
        self.advance_stage(case, SOWStage.DRAFTING)
        self._out("📝 Stage 2: DRAFTING")
        case = generate_draft(case)
        self._out(f"   ✅ {case.timeline[-1].result}")
        self._out()
        return case

    def _do_validation(self, case: SOWCase) -> SOWCase:
        self.advance_stage(case, SOWStage.VALIDATION)
        self._out("🔍 Stage 3: VALIDATION")
        case = run_validation(case)
        self._out(f"   ✅ {case.timeline[-1].result}")
        for _, check in case.validation_results.items():
            mark = "✅ PASS" if check["passed"] else "❌ FAIL"
            self._out(f"      {mark} — {check['check_name']}: {check['reasoning']}")
        if not case.validation_passed:
            self._out("   ⚠️  Validation flagged issues — escalating to human review.")
            self.escalate(case, "Validation checks failed", SOWStage.VALIDATION)
            return case
        self._out()
        return case

    def _do_approval(self, case: SOWCase) -> SOWCase:
        self.advance_stage(case, SOWStage.APPROVAL)
        self._out("✍️  Stage 4: INTERNAL APPROVAL")
        case = route_for_approval(case, self.approver_queue)
        self._out(f"   ✅ {case.timeline[-1].result}")
        case = collect_approvals(case, self.approver_queue)
        self._out(f"   ✅ {case.timeline[-1].result}")
        if case.approval_status != "approved":
            self._out("   ❌ Approval rejected — escalating to human review.")
            self.escalate(case, "Approval rejected", SOWStage.APPROVAL)
            return case
        self._out()
        return case

    def _do_customer_review(self, case: SOWCase) -> SOWCase:
        self.advance_stage(case, SOWStage.CUSTOMER_REVIEW)
        self._out("📧 Stage 5: CUSTOMER REVIEW")
        email = MockEmailThread(
            customer_email=(
                f"contact@{case.customer_name.lower().replace(' ', '')}.com"
                if case.customer_name else "customer@example.com"
            )
        )
        case = send_for_customer_review(case, email)
        self._out(f"   ✅ {case.timeline[-1].result}")
        case = handle_customer_response(case, email)
        self._out(f"   ✅ {case.timeline[-1].result}")
        if case.customer_review_status == "redline":
            self._out("   🔄 Redline received — updating draft...")
            case = generate_draft(case)
            case = send_updated_draft(case, email)
            self._out(f"   ✅ {case.timeline[-1].result}")
            case = handle_customer_response(case, email)
            self._out(f"   ✅ {case.timeline[-1].result}")
        if not case.customer_approved:
            self._out("   ❌ Customer did not approve — escalating to human review.")
            self.escalate(case, "Customer did not approve SOW", SOWStage.CUSTOMER_REVIEW)
            return case
        self._out()
        return case

    def _do_signing(self, case: SOWCase, resume_after_signature: bool = False) -> SOWCase:
        if case.current_stage != SOWStage.SIGNING:
            self.advance_stage(case, SOWStage.SIGNING)
        self._out("🖊️  Stage 6: SIGNING")
        if resume_after_signature:
            # Webhook callback already marked the envelope signed — just confirm & file.
            case = confirm_signature(case, self.esign)
            self._out()
            return case
        case = initiate_signing(case, self.esign)
        self._out(f"   ✅ {case.timeline[-1].result}")
        if SIGNING_MODE == "webhook":
            case.status = "awaiting_signature"
            self._out("   ⏳ Waiting for e-signature webhook callback...")
            self.state_store.save(case)
            return case
        case = confirm_signature(case, self.esign)
        self._out(f"   ✅ {case.timeline[-1].result}")
        self._out()
        return case

    def _do_complete(self, case: SOWCase) -> SOWCase:
        self.advance_stage(case, SOWStage.COMPLETE)
        case.status = "complete"
        notify_completion(case)
        self.state_store.save(case)
        return case

    # ── driver (resumable) ───────────────────────────────────────────────────

    def run_full_lifecycle(self, raw_request_text: str) -> SOWCase:
        """Create a case and run the full lifecycle from INTAKE."""
        case = self.create_case(raw_request_text)
        return self.run_lifecycle_from(case, start_stage=SOWStage.INTAKE)

    def run_lifecycle_from(
        self,
        case: SOWCase,
        start_stage: SOWStage = None,
        resume_after_signature: bool = False,
    ) -> SOWCase:
        """Continue a case from a given (or current) stage until it blocks or finishes."""
        if start_stage is None:
            start_stage = case.current_stage
        exact = STAGE_ORDER.index(start_stage)
        for stage in STAGE_ORDER[exact:]:
            if case.status in ("blocked", "rejected", "complete", "awaiting_signature"):
                break
            if stage == SOWStage.INTAKE:
                case = self._do_intake(case)
            elif stage == SOWStage.DRAFTING:
                case = self._do_drafting(case)
            elif stage == SOWStage.VALIDATION:
                case = self._do_validation(case)
            elif stage == SOWStage.APPROVAL:
                case = self._do_approval(case)
            elif stage == SOWStage.CUSTOMER_REVIEW:
                case = self._do_customer_review(case)
            elif stage == SOWStage.SIGNING:
                case = self._do_signing(case, resume_after_signature=resume_after_signature)
            elif stage == SOWStage.COMPLETE:
                case = self._do_complete(case)
            self.state_store.save(case)
        if case.status == "complete":
            self._print_summary(case)
        else:
            self._out(f"⏸️  Case {case.case_id} paused at {case.current_stage.value} (status={case.status}).")
            if case.escalated_to_human:
                self._out(f"   Escalated: {case.escalation_reason}")
                self._out("   Resolve via: python main.py --resolve <CASE_ID> approve|override|resend|reject")
        return case

    # ── human-in-the-loop resolution (FR8) ───────────────────────────────────

    def resolve_case(self, case_id: str, decision: str, notes: str = "") -> SOWCase:
        """Resolve a blocked case. Returns the (possibly continued) case."""
        case = self.state_store.load(case_id)
        if case is None:
            raise ValueError(f"Case {case_id} not found")
        if not case.escalated_to_human:
            raise ValueError(f"Case {case_id} is not escalated")
        decision = decision.strip().lower()

        if decision in ("approve", "override"):
            if case.escalation_stage == SOWStage.VALIDATION.value:
                case.validation_passed = True  # human override of deterministic checks
            resume_stage = _NEXT_STAGE_AFTER.get(SOWStage(case.escalation_stage), SOWStage.SIGNING)
            self._record_decision(case, decision, notes, "override approved")
            case.escalated_to_human = False
            case.status = "active"
            case.blockers = []
            self.state_store.save(case)
            return self.run_lifecycle_from(case, start_stage=resume_stage)
        elif decision == "resend":
            # Only meaningful for customer review: reset and retry the loop
            self._record_decision(case, decision, notes, "resending for customer review")
            case.escalated_to_human = False
            case.status = "active"
            case.blockers = []
            case.customer_review_status = "pending"
            case.customer_approved = False
            self.state_store.save(case)
            return self.run_lifecycle_from(case, start_stage=SOWStage.CUSTOMER_REVIEW)
        elif decision == "reject":
            self._record_decision(case, decision, notes, "case rejected by human")
            case.status = "rejected"
            self.state_store.save(case)
            return case
        else:
            raise ValueError("decision must be one of: approve, override, resend, reject")

    def _record_decision(self, case: SOWCase, decision: str, notes: str, summary: str):
        for esc in case.escalations:
            if esc.decision_id == case.decision_id:
                esc.decision = decision
                esc.notes = notes or None
                esc.resolved_at = datetime.now().isoformat()
        case.decision_status = "resolved"
        case.log_action(
            agent_name="Human",
            action=f"Resolve escalation — {decision}",
            reasoning=notes or f"Human decision recorded: {summary}.",
            result=f"Escalation {case.decision_id} resolved ({decision}); {summary}.",
        )

    # ── summary ───────────────────────────────────────────────────────────────

    def _print_summary(self, case: SOWCase):
        self._out("=" * 80)
        self._out("SOW LIFECYCLE COMPLETE — SUMMARY")
        self._out("=" * 80)
        self._out()
        self._out(f"  Case ID:         {case.case_id}")
        self._out(f"  Project:         {case.project_title}")
        self._out(f"  Customer:        {case.customer_name}")
        self._out(f"  Budget:          £{case.budget_gbp:,.2f}")
        self._out(f"  Timeline:        {case.requested_delivery_weeks} weeks")
        self._out(f"  Final Status:    {case.status.upper()}")
        self._out(f"  Signed At:       {case.signed_at}")
        self._out()
        self._out("-" * 80)
        self._out("AGENT ACTION TIMELINE (Explainability Log)")
        self._out("-" * 80)
        for i, entry in enumerate(case.timeline, 1):
            self._out(f"  {i:2d}. [{entry.stage.value}] {entry.agent_name}")
            self._out(f"      Action: {entry.action}")
            self._out(f"      Reasoning: {entry.reasoning}")
            self._out(f"      Result: {entry.result}")
            self._out()
        self._out("=" * 80)
        self._out(f"Total agent actions: {len(case.timeline)}")
        self._out(f"Case data saved to: data/cases/{case.case_id}.json")
        self._out("=" * 80)