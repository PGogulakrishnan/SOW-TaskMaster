"""
Mock Email Integration
========================
Simulates sending/receiving customer emails.
In production, this would connect to an email API (e.g., Gmail, Outlook).
"""

import time
from ports import EmailPort
from config import (
    MOCK_DELAY_SECONDS,
    CUSTOMER_FIRST_RESPONSE,
    CUSTOMER_REDLINE_REQUEST,
    CUSTOMER_SECOND_RESPONSE,
)


class MockEmailThread(EmailPort):  # swap for a real Gmail/Outlook adapter in production
    """Simulated email thread with a customer."""
    
    def __init__(self, customer_email: str = "customer@example.com"):
        self.customer_email = customer_email
        self.messages: list[dict] = []
        self._response_count = 0
    
    def send(self, subject: str, body: str, recipient: str = None) -> dict:
        """Simulate sending an email."""
        time.sleep(MOCK_DELAY_SECONDS)
        
        msg = {
            "direction": "outbound",
            "from": "sow-agent@company.com",
            "to": recipient or self.customer_email,
            "subject": subject,
            "body": body,
            "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.messages.append(msg)
        return msg
    
    def receive_reply(self) -> dict:
        """
        Simulate receiving a customer reply.
        First response is a redline, second is approval.
        """
        time.sleep(MOCK_DELAY_SECONDS)
        
        self._response_count += 1
        
        if self._response_count <= 1:
            # First response: redline
            content = CUSTOMER_FIRST_RESPONSE
            redline = CUSTOMER_REDLINE_REQUEST
        else:
            # Second response: approve
            content = CUSTOMER_SECOND_RESPONSE
            redline = None
        
        msg = {
            "direction": "inbound",
            "from": self.customer_email,
            "to": "sow-agent@company.com",
            "subject": "Re: SOW Review",
            "body": content,
            "redline_request": redline,
            "response_type": content,
            "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.messages.append(msg)
        return msg
    
    def get_thread(self) -> list[dict]:
        """Get the full email thread."""
        return self.messages