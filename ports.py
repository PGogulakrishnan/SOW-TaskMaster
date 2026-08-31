"""
Ports / Interfaces
==================
Clean interface boundaries for the mocked integrations (NFR3).

The mocks in `mocks/` implement these Protocols. In production you would
swap each mock for a real adapter (IMAP/Gmail, DocuSign, Slack, ...) that
satisfies the same Protocol - the rest of the system never changes.
"""

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class InboxPort(Protocol):
    """Receives new SOW requests (email/webhook/form)."""

    def receive_request(
        self, request_text: str, sender: str = "account_manager@company.com"
    ) -> dict: ...

    def get_latest_request(self) -> Optional[dict]: ...


@runtime_checkable
class EmailPort(Protocol):
    """Outbound + inbound customer email thread."""

    def send(self, subject: str, body: str, recipient: Optional[str] = None) -> dict: ...

    def receive_reply(self) -> dict: ...

    def get_thread(self) -> list[dict]: ...


@runtime_checkable
class ESignPort(Protocol):
    """E-signature service (DocuSign / HelloSign style)."""

    def send_for_signature(self, document_text: str, signers: list[str], case_id: str) -> dict: ...

    def check_status(self, envelope_id: str) -> dict: ...

    def get_signed_document(self, envelope_id: str) -> dict: ...


@runtime_checkable
class ApproverPort(Protocol):
    """Internal approver queue (Slack/Jira style)."""

    def request_approval(self, approver: str, case_id: str, details: dict) -> dict: ...

    def get_approver_response(self, approval_id: str) -> dict: ...

    def get_all_responses(self, case_id: str) -> list[dict]: ...