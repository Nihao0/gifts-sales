from __future__ import annotations

import json
from urllib.request import Request, urlopen

from app.models.approval import ApprovalRequest


class ApprovalNotifier:
    def __init__(self, bot_token: str | None, chat_id: str | None) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def send_approval_request(self, approval: ApprovalRequest) -> bool:
        if not self.enabled:
            return False

        text = (
            f"Approval #{approval.id}: {approval.action.value}\n"
            f"Gift: {approval.gift.title or approval.gift.telegram_gift_id}\n"
            f"Destination: {approval.destination_peer}\n"
            f"Reason: {approval.reason or '-'}\n\n"
            f"Approve: gifts-sales approvals approve --id {approval.id}\n"
            f"Reject: gifts-sales approvals reject --id {approval.id}"
        )
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        request = Request(
            f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
