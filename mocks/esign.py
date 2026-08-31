"""
Mock E-Signature Integration
==============================
Simulates DocuSign-style e-signature flow.
In production, this would connect to DocuSign/HelloSign API.
"""

import time
import uuid
from config import MOCK_DELAY_SECONDS
from ports import ESignPort


class MockESign(ESignPort):  # swap for a real DocuSign/HelloSign adapter in production
    """Simulated e-signature service."""
    
    def __init__(self):
        self.envelopes: list[dict] = []
    
    def send_for_signature(
        self,
        document_text: str,
        signers: list[str],
        case_id: str,
    ) -> dict:
        """Simulate sending a document for e-signature."""
        time.sleep(MOCK_DELAY_SECONDS)
        
        envelope = {
            "envelope_id": f"env_{uuid.uuid4().hex[:8]}",
            "case_id": case_id,
            "document_hash": hash(document_text) & 0xFFFFFFFF,
            "signers": signers,
            "status": "sent",
            "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.envelopes.append(envelope)
        return envelope
    
    def check_status(self, envelope_id: str) -> dict:
        """Simulate checking signature status — always returns signed for demo."""
        time.sleep(MOCK_DELAY_SECONDS)
        
        for env in self.envelopes:
            if env["envelope_id"] == envelope_id:
                # In demo mode, always return signed
                env["status"] = "signed"
                env["signed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                return env
        
        return {"error": "Envelope not found"}
    
    def get_signed_document(self, envelope_id: str) -> dict:
        """Simulate retrieving the signed document."""
        time.sleep(MOCK_DELAY_SECONDS)
        
        for env in self.envelopes:
            if env["envelope_id"] == envelope_id:
                return {
                    "envelope_id": envelope_id,
                    "status": "signed",
                    "document": "SIGNED_DOCUMENT_CONTENT",
                    "certificate_of_completion": f"cert_{uuid.uuid4().hex[:8]}",
                }
        
        return {"error": "Envelope not found"}