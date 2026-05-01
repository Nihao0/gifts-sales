from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import MarketFloor, MarketListing
from app.schemas.market import MarketFloorCreateSchema, MarketListingCreateSchema


class MarketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_floor(self, data: MarketFloorCreateSchema) -> MarketFloor:
        floor = MarketFloor(
            **data.model_dump(),
            captured_at=datetime.now(timezone.utc),
        )
        self._session.add(floor)
        await self._session.flush()
        return floor

    async def add_listing(self, data: MarketListingCreateSchema) -> MarketListing:
        listing = MarketListing(
            **data.model_dump(),
            captured_at=datetime.now(timezone.utc),
        )
        self._session.add(listing)
        await self._session.flush()
        return listing

    async def latest_floors(
        self,
        market: str = "portals",
        gift_name: str | None = None,
        limit: int = 100,
    ) -> list[MarketFloor]:
        query = (
            select(MarketFloor)
            .where(MarketFloor.market == market)
            .order_by(MarketFloor.captured_at.desc(), MarketFloor.id.desc())
            .limit(limit)
        )
        if gift_name is not None:
            query = query.where(MarketFloor.gift_name == gift_name)
        result = await self._session.execute(query)
        return list(result.scalars().all())
