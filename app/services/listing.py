"""ListingService — list and delist gifts on Telegram's internal marketplace."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.client.mtproto.functions import UpdateStarGiftPriceRequest
from app.client.mtproto.types import InputSavedStarGiftUser, StarsAmount
from app.client.telegram import TelegramClientContext
from app.models.gift import Gift
from app.services.pricing import PricingService
from app.storage.gift_repo import GiftRepository
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.config.settings import Settings

log = get_logger(__name__)


class ListingService:
    def __init__(
        self,
        tg: TelegramClientContext | None,
        gift_repo: GiftRepository,
        pricing: PricingService,
        settings: "Settings",
    ) -> None:
        self._tg = tg
        self._gift_repo = gift_repo
        self._pricing = pricing
        self._settings = settings

    async def list_gift(self, gift: Gift, price_ton: float, dry_run: bool = False) -> None:
        """List a gift for sale at price_ton TON."""
        # Idempotency check — skip if already listed at the same price
        if gift.owner_peer != "self":
            raise ValueError("Only gifts owned by the current account can be listed.")

        if gift.is_for_sale and _prices_equal(gift.resale_price_ton, price_ton):
            log.info(
                "listing.skip.already_listed",
                gift_id=gift.id,
                price_ton=price_ton,
            )
            return

        if (
            not dry_run
            and self._settings.require_ton_rate_for_sales
            and self._settings.ton_to_stars_rate is None
        ):
            raise ValueError("TON_TO_STARS_RATE is required for real listing operations.")

        rate = await self._pricing.get_stars_per_ton(gift.collectible_id)
        stars = self._pricing.ton_to_stars(price_ton, rate)

        log.info(
            "listing.list",
            gift_id=gift.id,
            telegram_gift_id=gift.telegram_gift_id,
            price_ton=price_ton,
            stars=stars,
            dry_run=dry_run,
        )

        if dry_run:
            return

        if gift.msg_id is None:
            raise ValueError(
                f"Gift {gift.id} has no msg_id — run 'gifts scan' first."
            )
        if self._tg is None:
            raise RuntimeError("Telegram client is required for real listing.")
        request = UpdateStarGiftPriceRequest(
            stargift=InputSavedStarGiftUser(msg_id=gift.msg_id),
            resell_amount=StarsAmount(amount=stars, nanos=0),
        )
        await self._tg.invoke(request)

        await self._gift_repo.update_sale_status(
            gift.id,
            is_for_sale=True,
            price_stars=stars,
            price_ton=price_ton,
        )

    async def delist_gift(self, gift: Gift, dry_run: bool = False) -> None:
        """Remove a gift from sale."""
        if gift.owner_peer != "self":
            raise ValueError("Only gifts owned by the current account can be delisted.")

        if not gift.is_for_sale:
            log.info("listing.skip.not_for_sale", gift_id=gift.id)
            return

        log.info(
            "listing.delist",
            gift_id=gift.id,
            telegram_gift_id=gift.telegram_gift_id,
            dry_run=dry_run,
        )

        if dry_run:
            return

        if gift.msg_id is None:
            raise ValueError(
                f"Gift {gift.id} has no msg_id — run 'gifts scan' first."
            )
        if self._tg is None:
            raise RuntimeError("Telegram client is required for real delisting.")
        request = UpdateStarGiftPriceRequest(
            stargift=InputSavedStarGiftUser(msg_id=gift.msg_id),
            resell_amount=StarsAmount(amount=0, nanos=0),
        )
        await self._tg.invoke(request)

        await self._gift_repo.update_sale_status(
            gift.id,
            is_for_sale=False,
            price_stars=None,
            price_ton=None,
        )


def _prices_equal(a: float | None, b: float | None, tol: float = 1e-6) -> bool:
    if a is None or b is None:
        return False
    return math.isclose(a, b, rel_tol=tol)
