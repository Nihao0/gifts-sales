from pydantic import BaseModel


class MarketFloorCreateSchema(BaseModel):
    market: str
    gift_name: str
    model: str | None = None
    backdrop: str | None = None
    symbol: str | None = None
    floor_price_ton: float | None = None
    listed_count: int | None = None
    raw_json: str | None = None


class MarketListingCreateSchema(BaseModel):
    market: str
    external_id: str | None = None
    tg_id: str | None = None
    gift_name: str
    model: str | None = None
    backdrop: str | None = None
    symbol: str | None = None
    price_ton: float | None = None
    raw_json: str | None = None
