"""
JobQueueService — single-writer async job queue.

Only one coroutine (run_forever) ever calls ListingService, ensuring no
concurrent MTProto write operations on the same account.

FLOOD_WAIT handling:
  - If FloodWaitError.seconds <= settings.flood_sleep_threshold, Telethon
    sleeps automatically and the call succeeds.
  - If above threshold, we catch it here, persist retry_after in the DB,
    and do NOT put the job back in the in-memory queue immediately.
    The job is re-enqueued on next startup or by enqueue_pending_from_db().
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from telethon.errors import FloodWaitError

from app.models.job import JobStatus, JobType
from app.services.listing import ListingService
from app.services.transfer import TransferService
from app.storage.gift_repo import GiftRepository
from app.storage.job_repo import JobRepository
from app.utils.logging import get_logger
from app.utils.retry import compute_retry_after, is_retry_due, should_retry

if TYPE_CHECKING:
    from app.config.settings import Settings

log = get_logger(__name__)


class JobQueueService:
    def __init__(
        self,
        session_factory,
        tg,
        pricing,
        settings: "Settings",
        *,
        dry_run: bool | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._tg = tg
        self._pricing = pricing
        self._settings = settings
        self._dry_run = dry_run
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def enqueue(self, job_id: int) -> None:
        await self._queue.put(job_id)

    async def join(self) -> None:
        await self._queue.join()

    async def enqueue_pending_from_db(self) -> int:
        """Load pending+due jobs from DB into the queue. Returns count enqueued."""
        async with self._session_factory() as session:
            repo = JobRepository(session)
            pending = await repo.get_pending()
        count = 0
        for job in pending:
            await self._queue.put(job.id)
            count += 1
        if count:
            log.info("job_queue.enqueued_pending", count=count)
        return count

    def start(self) -> asyncio.Task:
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run_forever(), name="job-queue-worker")
        return self._task

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()

    async def run_forever(self) -> None:
        log.info("job_queue.started")
        while not self._stop_event.is_set():
            try:
                job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await self._process_job(job_id)
            except Exception as exc:
                log.error("job_queue.unhandled_error", job_id=job_id, error=str(exc))
            finally:
                self._queue.task_done()
        log.info("job_queue.stopped")

    async def _process_job(self, job_id: int) -> None:
        async with self._session_factory() as session:
            job_repo = JobRepository(session)
            gift_repo = GiftRepository(session)

            listing = ListingService(self._tg, gift_repo, self._pricing, self._settings)
            transfer = TransferService(self._tg, gift_repo, self._settings)

            job = await job_repo.get_by_id(job_id)
            if job is None:
                log.warning("job_queue.job_not_found", job_id=job_id)
                return

            if not is_retry_due(job):
                log.debug(
                    "job_queue.retry_not_due",
                    job_id=job_id,
                    retry_after=str(job.retry_after),
                )
                return

            if job.status in (JobStatus.DONE, JobStatus.SKIPPED):
                log.debug("job_queue.already_terminal", job_id=job_id, status=job.status)
                return

            await job_repo.mark_running(job_id)
            gift = await gift_repo.get_by_id(job.gift_id)

            if gift is None:
                await job_repo.mark_failed(job_id, "Gift not found in local DB")
                await session.commit()
                return

            dry_run = self._settings.dry_run if self._dry_run is None else self._dry_run

            try:
                if job.job_type == JobType.LIST:
                    if job.price_ton is None:
                        raise ValueError("List job requires price_ton")
                    await listing.list_gift(gift, job.price_ton, dry_run=dry_run)
                elif job.job_type == JobType.DELIST:
                    await listing.delist_gift(gift, dry_run=dry_run)
                else:
                    if job.destination_peer is None:
                        raise ValueError("Transfer job requires destination_peer")
                    await transfer.transfer_gift(
                        gift,
                        job.destination_peer,
                        dry_run=dry_run,
                    )

                await job_repo.mark_done(job_id)
                log.info("job_queue.job_done", job_id=job_id, type=job.job_type.value)

            except FloodWaitError as exc:
                if should_retry(job):
                    retry_at = compute_retry_after(exc.seconds)
                    await job_repo.schedule_retry(job_id, retry_at, error=str(exc))
                    log.warning(
                        "job_queue.flood_wait_scheduled",
                        job_id=job_id,
                        wait_seconds=exc.seconds,
                        retry_after=str(retry_at),
                    )
                else:
                    await job_repo.mark_failed(
                        job_id, f"max_attempts exceeded after FLOOD_WAIT: {exc}"
                    )
                    log.error("job_queue.max_attempts_exceeded", job_id=job_id)

            except Exception as exc:
                err = str(exc)
                if should_retry(job):
                    await job_repo.schedule_retry(
                        job_id,
                        compute_retry_after(30),
                        error=err,
                    )
                    log.warning("job_queue.job_error_scheduled_retry", job_id=job_id, error=err)
                else:
                    await job_repo.mark_failed(job_id, err)
                    log.error("job_queue.job_failed", job_id=job_id, error=err)

            await session.commit()
