from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gift import Gift
from app.schemas.gift import GiftCreateSchema


class GiftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, data: GiftCreateSchema) -> Gift:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(Gift).where(
                Gift.telegram_gift_id == data.telegram_gift_id,
                Gift.owner_peer == data.owner_peer,
            )
        )
        gift = result.scalar_one_or_none()
        if gift is None:
            gift = Gift(
                telegram_gift_id=data.telegram_gift_id,
                owner_peer=data.owner_peer,
                first_seen_at=now,
                updated_at=now,
            )
            self._session.add(gift)

        for field, value in data.model_dump(exclude={"telegram_gift_id", "owner_peer"}).items():
            setattr(gift, field, value)
        gift.updated_at = now
        await self._session.flush()
        return gift

    async def get_by_telegram_id(self, telegram_gift_id: str) -> Gift | None:
        result = await self._session.execute(
            select(Gift).where(Gift.telegram_gift_id == telegram_gift_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, gift_id: int) -> Gift | None:
        result = await self._session.execute(select(Gift).where(Gift.id == gift_id))
        return result.scalar_one_or_none()

    async def list_all(self, owner_peer: str | None = None) -> list[Gift]:
        query = select(Gift).order_by(Gift.id)
        if owner_peer is not None:
            query = query.where(Gift.owner_peer == owner_peer)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_for_sale(self) -> list[Gift]:
        result = await self._session.execute(
            select(Gift).where(Gift.is_for_sale == True).order_by(Gift.id)  # noqa: E712
        )
        return list(result.scalars().all())

    async def update_sale_status(
        self,
        gift_id: int,
        is_for_sale: bool,
        price_stars: int | None,
        price_ton: float | None,
    ) -> None:
        gift = await self.get_by_id(gift_id)
        if gift is None:
            raise ValueError(f"Gift {gift_id} not found")
        gift.is_for_sale = is_for_sale
        gift.resale_price_stars = price_stars
        gift.resale_price_ton = price_ton
        gift.updated_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def mark_transferred(self, gift_id: int, destination_peer: str) -> None:
        gift = await self.get_by_id(gift_id)
        if gift is None:
            raise ValueError(f"Gift {gift_id} not found")
        now = datetime.now(timezone.utc)
        gift.is_for_sale = False
        gift.resale_price_stars = None
        gift.resale_price_ton = None
        gift.transferred_to = destination_peer
        gift.transferred_at = now
        gift.updated_at = now
        await self._session.flush()
