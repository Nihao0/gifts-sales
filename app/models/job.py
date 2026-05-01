import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class JobType(str, enum.Enum):
    LIST = "list"
    DELIST = "delist"
    TRANSFER = "transfer"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_retry_after", "status", "retry_after"),
        Index("ix_jobs_gift_id", "gift_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    job_type: Mapped[JobType] = mapped_column(Enum(JobType), nullable=False)
    gift_id: Mapped[int] = mapped_column(Integer, ForeignKey("gifts.id"), nullable=False)
    gift: Mapped["Gift"] = relationship("Gift", lazy="joined")  # noqa: F821

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, nullable=False
    )

    # Idempotency key:
    # - "list:{telegram_gift_id}:{price_ton:.6f}"
    # - "delist:{telegram_gift_id}"
    # - "transfer:{telegram_gift_id}:{destination_peer}"
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    price_ton: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_peer: Mapped[str | None] = mapped_column(String(128), nullable=True)

    retry_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    error_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Job id={self.id} type={self.job_type.value} "
            f"status={self.status.value} gift_id={self.gift_id}>"
        )


def make_dedupe_key(
    job_type: JobType,
    telegram_gift_id: str,
    price_ton: float | None,
    destination_peer: str | None = None,
) -> str:
    if job_type == JobType.LIST:
        return f"list:{telegram_gift_id}:{price_ton:.6f}"
    if job_type == JobType.TRANSFER:
        return f"transfer:{telegram_gift_id}:{destination_peer}"
    return f"delist:{telegram_gift_id}"
