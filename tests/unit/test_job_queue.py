from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.job import JobStatus, JobType
from app.schemas.job import JobCreateSchema
from app.services.job_queue import JobQueueService
from app.services.pricing import PricingService
from app.storage.gift_repo import GiftRepository
from app.storage.job_repo import JobRepository


def make_settings() -> MagicMock:
    settings = MagicMock()
    settings.dry_run = False
    settings.ton_to_stars_rate = 200.0
    settings.require_ton_rate_for_sales = True
    return settings


@pytest.mark.asyncio
async def test_queue_processes_job_with_fresh_session(db_session_factory, sample_gift):
    settings = make_settings()
    tg = AsyncMock()
    pricing = PricingService(tg, settings)

    async with db_session_factory() as session:
        job_repo = JobRepository(session)
        job, _ = await job_repo.create_if_not_exists(
            JobCreateSchema(
                job_type=JobType.LIST,
                gift_id=sample_gift.id,
                telegram_gift_id=sample_gift.telegram_gift_id,
                price_ton=10.0,
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

    assert gift.is_for_sale is True
    assert gift.resale_price_stars == 2000
    assert gift.resale_price_ton == 10.0
    assert job.status == JobStatus.DONE
    tg.invoke.assert_awaited_once()
