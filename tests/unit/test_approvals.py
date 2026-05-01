import pytest

from app.models.approval import ApprovalAction, ApprovalStatus
from app.schemas.approval import ApprovalCreateSchema
from app.storage.approval_repo import ApprovalRepository


@pytest.mark.asyncio
async def test_approval_create_approve_reject(db_session, sample_gift):
    repo = ApprovalRepository(db_session)
    approval, created = await repo.create_if_not_exists(
        ApprovalCreateSchema(
            action=ApprovalAction.TRANSFER_PORTALS,
            gift_id=sample_gift.id,
            destination_peer="@portals",
            reason="test",
        )
    )
    await db_session.commit()

    assert created is True
    assert approval.status == ApprovalStatus.PENDING

    duplicate, duplicate_created = await repo.create_if_not_exists(
        ApprovalCreateSchema(
            action=ApprovalAction.TRANSFER_PORTALS,
            gift_id=sample_gift.id,
            destination_peer="@portals",
            reason="test",
        )
    )
    assert duplicate_created is False
    assert duplicate.id == approval.id

    await repo.approve(approval.id)
    await db_session.commit()

    approved = await repo.get_by_id(approval.id)
    assert approved.status == ApprovalStatus.APPROVED
