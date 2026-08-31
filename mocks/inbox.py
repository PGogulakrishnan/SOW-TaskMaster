"""
Mock Inbox Integration
========================
Simulates receiving a SOW request via email/webhook.
In production, this would connect to an email API or webhook endpoint.
"""

import time
from config import MOCK_DELAY_SECONDS
from ports import InboxPort


class MockInbox(InboxPort):  # swap for a real email/webhook adapter in production
    """Simulated inbox for receiving SOW requests."""
    
    def __init__(self):
        self.received_requests: list[dict] = []
    
    def receive_request(self, request_text: str, sender: str = "account_manager@company.com") -> dict:
        """
        Simulate receiving a new SOW request.
        Returns a structured request object.
        """
        time.sleep(MOCK_DELAY_SECONDS)
        
        request = {
            "sender": sender,
            "subject": "New SOW Request",
            "body": request_text,
            "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "message_id": f"msg_{int(time.time() * 1000)}",
        }
        self.received_requests.append(request)
        return request
    
    def get_latest_request(self) -> dict | None:
        """Get the most recent request."""
        if self.received_requests:
            return self.received_requests[-1]
        return None