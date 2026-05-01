"""InventoryService — scan gifts from Telegram and persist to local DB."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.client.telegram import TelegramClientContext
from app.client.mtproto.types import SavedStarGift
from app.models.gift import Gift
from app.schemas.gift import GiftCreateSchema
from app.services.pricing import PricingService
from app.storage.gift_repo import GiftRepository
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.config.settings import Settings

log = get_logger(__name__)


class InventoryService:
    def __init__(
        self,
        tg: TelegramClientContext,
        gift_repo: GiftRepository,
        pricing: PricingService,
        settings: "Settings",
    ) -> None:
        self._tg = tg
        self._gift_repo = gift_repo
        self._pricing = pricing
        self._settings = settings

    async def scan(self, owner_peer: str = "self", peer=None) -> list[Gift]:
        """Fetch all saved gifts from Telegram and upsert into local DB."""
        log.info("inventory.scan.start", owner_peer=owner_peer)
        raw_gifts = await self._tg.get_saved_star_gifts(peer=peer)
        log.info("inventory.scan.fetched", count=len(raw_gifts), owner_peer=owner_peer)

        # Fetch exchange rate once for TON price annotation
        rate: float | None = None
        if raw_gifts:
            try:
                cid = raw_gifts[0].gift.gift_id if raw_gifts[0].gift else None
                rate = await self._pricing.get_stars_per_ton(cid)
            except Exception as exc:
                log.warning("inventory.scan.rate_fetch_failed", error=str(exc))

        persisted: list[Gift] = []
        for index, raw in enumerate(raw_gifts):
            schema = self._parse(raw, rate, owner_peer, index=index)
            gift = await self._gift_repo.upsert(schema)
            persisted.append(gift)

        log.info("inventory.scan.done", persisted=len(persisted))
        return persisted

    def _parse(
        self,
        raw: SavedStarGift,
        rate: float | None,
        owner_peer: str,
        *,
        index: int = 0,
    ) -> GiftCreateSchema:
        resale_ton: float | None = None
        if raw.resale_stars and rate:
            resale_ton = self._pricing.stars_to_ton(raw.resale_stars, rate)

        return GiftCreateSchema(
            telegram_gift_id=_local_gift_identity(raw, owner_peer, index),
            owner_peer=owner_peer,
            msg_id=raw.msg_id,
            collectible_id=raw.gift.gift_id if raw.gift else None,
            slug=raw.gift.slug if raw.gift else None,
            title=raw.gift.title if raw.gift else None,
            availability_issued=raw.gift.availability_issued if raw.gift else None,
            availability_total=raw.gift.availability_total if raw.gift else None,
            is_for_sale=raw.is_for_sale,
            resale_price_stars=raw.resale_stars,
            resale_price_ton=resale_ton,
            raw_json=json.dumps(raw.raw, ensure_ascii=False) if raw.raw else None,
        )


def _local_gift_identity(raw: SavedStarGift, owner_peer: str, index: int = 0) -> str:
    if raw.saved_id:
        local_id = str(raw.saved_id)
    elif raw.msg_id:
        local_id = f"msg:{raw.msg_id}"
    else:
        gift_id = raw.gift.gift_id if raw.gift else 0
        local_id = f"visible:{index}:{gift_id}:{raw.date}"

    if owner_peer == "self":
        return local_id
    return f"{owner_peer}:{local_id}"
