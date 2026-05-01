"""Unit tests for job idempotency — dedupe_key generation and skip logic."""
import pytest

from app.models.job import JobStatus, JobType, make_dedupe_key
from app.schemas.job import JobCreateSchema


class TestDedupeKey:
    def test_list_key_includes_price(self):
        key = make_dedupe_key(JobType.LIST, "abc123", 10.0)
        assert key == "list:abc123:10.000000"

    def test_list_key_precision(self):
        key = make_dedupe_key(JobType.LIST, "abc123", 10.123456789)
        assert key.startswith("list:abc123:")
        # 6 decimal places
        assert key == "list:abc123:10.123457"

    def test_delist_key_no_price(self):
        key = make_dedupe_key(JobType.DELIST, "abc123", None)
        assert key == "delist:abc123"

    def test_transfer_key_includes_destination(self):
        key = make_dedupe_key(JobType.TRANSFER, "abc123", None, "@portals")
        assert key == "transfer:abc123:@portals"

    def test_different_prices_different_keys(self):
        k1 = make_dedupe_key(JobType.LIST, "abc123", 10.0)
        k2 = make_dedupe_key(JobType.LIST, "abc123", 20.0)
        assert k1 != k2

    def test_different_gift_different_keys(self):
        k1 = make_dedupe_key(JobType.LIST, "abc123", 10.0)
        k2 = make_dedupe_key(JobType.LIST, "xyz999", 10.0)
        assert k1 != k2


class TestJobRepoIdempotency:
    @pytest.mark.asyncio
    async def test_create_twice_returns_same(self, job_repo, sample_gift, db_session):
        schema = JobCreateSchema(
            job_type=JobType.LIST,
            gift_id=sample_gift.id,
            telegram_gift_id=sample_gift.telegram_gift_id,
            price_ton=10.0,
            max_attempts=5,
        )
        job1, created1 = await job_repo.create_if_not_exists(schema)
        await db_session.commit()

        job2, created2 = await job_repo.create_if_not_exists(schema)
        await db_session.commit()

        assert created1 is True
        assert created2 is False
        assert job1.id == job2.id

    @pytest.mark.asyncio
    async def test_different_price_creates_new(self, job_repo, sample_gift, db_session):
        schema1 = JobCreateSchema(
            job_type=JobType.LIST,
            gift_id=sample_gift.id,
            telegram_gift_id=sample_gift.telegram_gift_id,
            price_ton=10.0,
        )
        schema2 = JobCreateSchema(
            job_type=JobType.LIST,
            gift_id=sample_gift.id,
            telegram_gift_id=sample_gift.telegram_gift_id,
            price_ton=20.0,
        )
        job1, c1 = await job_repo.create_if_not_exists(schema1)
        await db_session.commit()

        job2, c2 = await job_repo.create_if_not_exists(schema2)
        await db_session.commit()

        assert c1 is True
        assert c2 is True
        assert job1.id != job2.id

    @pytest.mark.asyncio
    async def test_failed_job_allows_recreation(self, job_repo, sample_gift, db_session):
        schema = JobCreateSchema(
            job_type=JobType.LIST,
            gift_id=sample_gift.id,
            telegram_gift_id=sample_gift.telegram_gift_id,
            price_ton=10.0,
        )
        job1, _ = await job_repo.create_if_not_exists(schema)
        await job_repo.mark_failed(job1.id, "test error")
        await db_session.commit()

        job2, created = await job_repo.create_if_not_exists(schema)
        await db_session.commit()

        # The failed job is reset in-place (same DB row) to respect UNIQUE constraint
        assert created is True
        assert job2.id == job1.id
        assert job2.status == JobStatus.PENDING
        assert job2.error_info is None

    @pytest.mark.asyncio
    async def test_delist_job_idempotent(self, job_repo, sample_gift, db_session):
        schema = JobCreateSchema(
            job_type=JobType.DELIST,
            gift_id=sample_gift.id,
            telegram_gift_id=sample_gift.telegram_gift_id,
        )
        job1, c1 = await job_repo.create_if_not_exists(schema)
        await db_session.commit()
        job2, c2 = await job_repo.create_if_not_exists(schema)
        await db_session.commit()

        assert c1 is True
        assert c2 is False
        assert job1.id == job2.id

    @pytest.mark.asyncio
    async def test_transfer_job_idempotent_by_destination(self, job_repo, sample_gift, db_session):
        schema = JobCreateSchema(
            job_type=JobType.TRANSFER,
            gift_id=sample_gift.id,
            telegram_gift_id=sample_gift.telegram_gift_id,
            destination_peer="@portals",
        )
        job1, c1 = await job_repo.create_if_not_exists(schema)
        await db_session.commit()
        job2, c2 = await job_repo.create_if_not_exists(schema)
        await db_session.commit()

        assert c1 is True
        assert c2 is False
        assert job1.id == job2.id
