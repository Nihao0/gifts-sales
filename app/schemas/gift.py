from datetime import datetime

from pydantic import BaseModel


class GiftCreateSchema(BaseModel):
    telegram_gift_id: str
    owner_peer: str = "self"
    msg_id: int | None = None
    collectible_id: int | None = None
    slug: str | None = None
    title: str | None = None
    availability_issued: int | None = None
    availability_total: int | None = None
    is_for_sale: bool = False
    resale_price_stars: int | None = None
    resale_price_ton: float | None = None
    transferred_to: str | None = None
    transferred_at: datetime | None = None
    raw_json: str | None = None


class GiftReadSchema(BaseModel):
    id: int
    telegram_gift_id: str
    owner_peer: str
    msg_id: int | None
    collectible_id: int | None
    slug: str | None
    title: str | None
    availability_issued: int | None
    availability_total: int | None
    is_for_sale: bool
    resale_price_stars: int | None
    resale_price_ton: float | None
    transferred_to: str | None
    transferred_at: datetime | None
    first_seen_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
