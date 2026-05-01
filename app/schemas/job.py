from datetime import datetime

from pydantic import BaseModel

from app.models.job import JobStatus, JobType


class JobCreateSchema(BaseModel):
    job_type: JobType
    gift_id: int
    telegram_gift_id: str
    price_ton: float | None = None
    destination_peer: str | None = None
    max_attempts: int = 5


class JobReadSchema(BaseModel):
    id: int
    job_type: JobType
    gift_id: int
    status: JobStatus
    dedupe_key: str
    price_ton: float | None
    destination_peer: str | None
    retry_after: datetime | None
    attempts: int
    max_attempts: int
    error_info: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
