from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.job import Job


def compute_retry_after(seconds: int, jitter_seconds: int = 5) -> datetime:
    """Returns UTC datetime after which the job may be retried."""
    return datetime.now(timezone.utc) + timedelta(seconds=seconds + jitter_seconds)


def should_retry(job: "Job") -> bool:
    return job.attempts < job.max_attempts


def is_retry_due(job: "Job") -> bool:
    if job.retry_after is None:
        return True
    now = datetime.now(timezone.utc)
    retry_after = job.retry_after
    if retry_after.tzinfo is None:
        retry_after = retry_after.replace(tzinfo=timezone.utc)
    return retry_after <= now
