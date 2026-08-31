"""
Mock Approver Queue Integration
=================================
Simulates routing approval requests to stakeholders.
In production, this would connect to an approval system (e.g., Slack, Jira, email).
"""

import time
from config import MOCK_DELAY_SECONDS, APPROVER_RESPONSE
from ports import ApproverPort


class MockApproverQueue(ApproverPort):  # swap for a real Slack/Jira approval adapter in production
    """Simulated approver queue for tracking approval requests."""
    
    def __init__(self):
        self.pending_approvals: list[dict] = []
        self.completed_approvals: list[dict] = []
    
    def request_approval(self, approver: str, case_id: str, details: dict) -> dict:
        """Send an approval request to a specific approver."""
        time.sleep(MOCK_DELAY_SECONDS)
        
        approval = {
            "approval_id": f"appr_{case_id}_{approver}",
            "approver": approver,
            "case_id": case_id,
            "details": details,
            "status": "pending",
            "requested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.pending_approvals.append(approval)
        return approval
    
    def get_approver_response(self, approval_id: str) -> dict:
        """
        Simulate getting a response from an approver.
        In demo mode, always returns 'approve'.
        """
        time.sleep(MOCK_DELAY_SECONDS)
        
        for approval in self.pending_approvals:
            if approval["approval_id"] == approval_id:
                approval["status"] = APPROVER_RESPONSE
                approval["responded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                approval["comments"] = "Approved — looks good."
                self.completed_approvals.append(approval)
                self.pending_approvals.remove(approval)
                return approval
        
        return {"error": "Approval not found"}
    
    def get_all_responses(self, case_id: str) -> list[dict]:
        """Get all completed approval responses for a case."""
        return [a for a in self.completed_approvals if a["case_id"] == case_id]