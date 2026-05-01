from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.job import JobStatus, JobType
from app.schemas.job import JobCreateSchema
from app.services.job_queue import JobQueueService
from app.services.pricing import PricingService
from app.services.transfer import TransferService
from app.storage.gift_repo import GiftRepository
from app.storage.job_repo import JobRepository


def make_settings() -> MagicMock:
    settings = MagicMock()
    settings.dry_run = False
    settings.max_job_attempts = 5
    return settings


@pytest.mark.asyncio
async def test_transfer_dry_run_does_not_update_db(db_session, sample_gift):
    settings = make_settings()
    gift_repo = GiftRepository(db_session)
    svc = TransferService(None, gift_repo, settings)

    await svc.transfer_gift(sample_gift, "@portals", dry_run=True)
    await db_session.commit()

    updated = await gift_repo.get_by_id(sample_gift.id)
    assert updated.transferred_to is None
    assert updated.transferred_at is None


@pytest.mark.asyncio
async def test_queue_processes_transfer_job(db_session_factory, sample_gift):
    settings = make_settings()
    tg = AsyncMock()
    tg.resolve_input_peer = AsyncMock(return_value=MagicMock())
    pricing = PricingService(tg, settings)

    async with db_session_factory() as session:
        job_repo = JobRepository(session)
        job, _ = await job_repo.create_if_not_exists(
            JobCreateSchema(
                job_type=JobType.TRANSFER,
                gift_id=sample_gift.id,
                telegram_gift_id=sample_gift.telegram_gift_id,
                destination_peer="@portals",
            )
        )
        job_id = job.id
        await session.commit()

    queue = JobQueueService(db_session_factory, tg, pricing, settings)
    await queue.enqueue(job_id)
    queue.start()
    await queue.join()
    await queue.stop()

    async with db_session_factory() as session:
        gift = await GiftRepository(session).get_by_id(sample_gift.id)
        job = await JobRepository(session).get_by_id(job_id)

    assert gift.transferred_to == "@portals"
    assert gift.transferred_at is not None
    assert job.status == JobStatus.DONE
    tg.resolve_input_peer.assert_awaited_once_with("@portals")
    tg.invoke.assert_awaited_once()
