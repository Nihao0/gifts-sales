from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus, make_dedupe_key
from app.schemas.job import JobCreateSchema


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_if_not_exists(self, data: JobCreateSchema) -> tuple[Job, bool]:
        """
        Returns (job, created).
        - If a non-failed job with the same dedupe_key exists, returns it (created=False).
        - If a failed job exists, resets it to PENDING (reuse to respect UNIQUE constraint).
        - Otherwise inserts a new job.
        """
        dedupe_key = make_dedupe_key(
            data.job_type,
            data.telegram_gift_id,
            data.price_ton,
            data.destination_peer,
        )
        result = await self._session.execute(
            select(Job).where(Job.dedupe_key == dedupe_key)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            if existing.status != JobStatus.FAILED:
                return existing, False
            # Reset failed job for a fresh attempt
            now = datetime.now(timezone.utc)
            existing.status = JobStatus.PENDING
            existing.retry_after = None
            existing.error_info = None
            existing.attempts = 0
            existing.max_attempts = data.max_attempts
            existing.destination_peer = data.destination_peer
            existing.updated_at = now
            await self._session.flush()
            return existing, True

        now = datetime.now(timezone.utc)
        job = Job(
            job_type=data.job_type,
            gift_id=data.gift_id,
            status=JobStatus.PENDING,
            dedupe_key=dedupe_key,
            price_ton=data.price_ton,
            destination_peer=data.destination_peer,
            attempts=0,
            max_attempts=data.max_attempts,
            created_at=now,
            updated_at=now,
        )
        self._session.add(job)
        await self._session.flush()
        return job, True

    async def get_by_id(self, job_id: int) -> Job | None:
        result = await self._session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def get_all(self, status: JobStatus | None = None) -> list[Job]:
        q = select(Job).order_by(Job.id)
        if status is not None:
            q = q.where(Job.status == status)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def get_pending(self) -> list[Job]:
        """Returns PENDING jobs ready to run (retry_after is null or in the past)."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(Job).where(
                Job.status == JobStatus.PENDING,
            ).order_by(Job.id)
        )
        jobs = result.scalars().all()
        return [
            j for j in jobs
            if j.retry_after is None or _as_utc(j.retry_after) <= now
        ]

    async def get_failed(self) -> list[Job]:
        return await self.get_all(JobStatus.FAILED)

    async def mark_running(self, job_id: int) -> None:
        await self._update(job_id, status=JobStatus.RUNNING)

    async def mark_done(self, job_id: int) -> None:
        await self._update(job_id, status=JobStatus.DONE, error_info=None)

    async def mark_failed(self, job_id: int, error: str) -> None:
        job = await self.get_by_id(job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_info = error
            job.attempts += 1
            job.updated_at = datetime.now(timezone.utc)
            await self._session.flush()

    async def mark_skipped(self, job_id: int, reason: str) -> None:
        await self._update(job_id, status=JobStatus.SKIPPED, error_info=reason)

    async def schedule_retry(self, job_id: int, retry_after: datetime, error: str) -> None:
        job = await self.get_by_id(job_id)
        if job:
            job.status = JobStatus.PENDING
            job.retry_after = retry_after
            job.error_info = error
            job.attempts += 1
            job.updated_at = datetime.now(timezone.utc)
            await self._session.flush()

    async def reset_for_retry(self, job_id: int) -> None:
        await self._update(
            job_id,
            status=JobStatus.PENDING,
            retry_after=None,
            error_info=None,
        )

    async def _update(self, job_id: int, **fields) -> None:
        job = await self.get_by_id(job_id)
        if job:
            for k, v in fields.items():
                setattr(job, k, v)
            job.updated_at = datetime.now(timezone.utc)
            await self._session.flush()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
