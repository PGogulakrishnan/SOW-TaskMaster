"""
Signature Agent
================
Triggers e-signature, confirms completion, and files the final document.
"""

from datetime import datetime
from models import SOWCase
from mocks.esign import MockESign
from config import USE_REAL_LLM, GEMINI_MODEL

# Import ADK
from google.adk.agents import LlmAgent



# ─── ADK Agent Definition ────────────────────────────────────────────────────

signature_agent = LlmAgent(
    name="SignatureAgent",
    model=GEMINI_MODEL if USE_REAL_LLM else "mock",
    description="Manages the e-signature process and final document filing.",
    instruction="""You are the Signature Agent for SOW (Statement of Work) processing.
Your job is to:
1. Send the final SOW for e-signature
2. Confirm signature completion
3. File the final signed document
4. Trigger project kickoff""",
    output_key="signature_result",
)


# ─── Agent Function ──────────────────────────────────────────────────────────

def initiate_signing(case: SOWCase, esign: MockESign) -> SOWCase:
    """
    Send the final SOW for e-signature.
    This is the main function called by the Task Master.
    """
    signers = [
        f"signer@{case.customer_name.lower().replace(' ', '')}.com" if case.customer_name else "customer@example.com",
        "company_signatory@company.com",
    ]
    
    envelope = esign.send_for_signature(
        document_text=case.draft_sow_text or "SOW Document",
        signers=signers,
        case_id=case.case_id,
    )
    
    case.signature_status = "sent"
    
    # Log the action
    case.log_action(
        agent_name="SignatureAgent",
        action="Send SOW for e-signature",
        reasoning="Customer has approved the SOW. Initiating e-signature process with all parties.",
        result=f"E-signature envelope created: {envelope['envelope_id']}",
    )
    
    return case


def confirm_signature(case: SOWCase, esign: MockESign) -> SOWCase:
    """
    Check and confirm signature completion.
    For demo, this always returns signed.
    """
    # Find the envelope for this case
    envelope = None
    for env in esign.envelopes:
        if env["case_id"] == case.case_id:
            envelope = env
            break
    
    if envelope:
        status = esign.check_status(envelope["envelope_id"])
        
        if status.get("status") == "signed":
            case.signature_status = "signed"
            case.signed_at = datetime.now().isoformat()
            
            # Log the action
            case.log_action(
                agent_name="SignatureAgent",
                action="Confirm signature completion",
                reasoning="E-signature process completed. All parties have signed the SOW.",
                result=f"SOW signed at {case.signed_at}. Case is now complete.",
            )
        else:
            case.signature_status = "pending"
            case.log_action(
                agent_name="SignatureAgent",
                action="Check signature status",
                reasoning="Signature still pending. Waiting for all parties to sign.",
                result="Signature not yet complete.",
            )
    else:
        case.log_action(
            agent_name="SignatureAgent",
            action="Check signature status",
            reasoning="No envelope found for this case.",
            result="Error: No e-signature envelope found.",
        )
    
    return case