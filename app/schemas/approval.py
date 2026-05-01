from pydantic import BaseModel

from app.models.approval import ApprovalAction, ApprovalStatus


class ApprovalCreateSchema(BaseModel):
    action: ApprovalAction
    gift_id: int
    destination_peer: str
    reason: str | None = None
    policy_name: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
