from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
from app.schemas.approval import ApprovalCreateSchema


class ApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_if_not_exists(self, data: ApprovalCreateSchema) -> tuple[ApprovalRequest, bool]:
        query = select(ApprovalRequest).where(
            ApprovalRequest.action == data.action,
            ApprovalRequest.gift_id == data.gift_id,
            ApprovalRequest.destination_peer == data.destination_peer,
            ApprovalRequest.status.in_((ApprovalStatus.PENDING, ApprovalStatus.APPROVED)),
        )
        result = await self._session.execute(query)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing, False

        now = datetime.now(timezone.utc)
        approval = ApprovalRequest(
            action=data.action,
            status=data.status,
            gift_id=data.gift_id,
            destination_peer=data.destination_peer,
            reason=data.reason,
            policy_name=data.policy_name,
            created_at=now,
            updated_at=now,
        )
        self._session.add(approval)
        await self._session.flush()
        return approval, True

    async def get_by_id(self, approval_id: int) -> ApprovalRequest | None:
        result = await self._session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, status: ApprovalStatus | None = None) -> list[ApprovalRequest]:
        query = select(ApprovalRequest).order_by(ApprovalRequest.id)
        if status is not None:
            query = query.where(ApprovalRequest.status == status)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_approved_for_execution(self) -> list[ApprovalRequest]:
        result = await self._session.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.status == ApprovalStatus.APPROVED,
                ApprovalRequest.action == ApprovalAction.TRANSFER_PORTALS,
            )
            .order_by(ApprovalRequest.id)
        )
        return list(result.scalars().all())

    async def approve(self, approval_id: int) -> None:
        await self._set_status(approval_id, ApprovalStatus.APPROVED)

    async def reject(self, approval_id: int) -> None:
        await self._set_status(approval_id, ApprovalStatus.REJECTED)

    async def mark_executed(self, approval_id: int, job_id: int) -> None:
        approval = await self.get_by_id(approval_id)
        if approval is not None:
            approval.status = ApprovalStatus.EXECUTED
            approval.job_id = job_id
            approval.updated_at = datetime.now(timezone.utc)
            await self._session.flush()

    async def _set_status(self, approval_id: int, status: ApprovalStatus) -> None:
        approval = await self.get_by_id(approval_id)
        if approval is not None:
            approval.status = status
            approval.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
