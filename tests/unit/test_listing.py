from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.listing import ListingService
from app.services.pricing import PricingService
from app.storage.gift_repo import GiftRepository


def make_settings() -> MagicMock:
    settings = MagicMock()
    settings.ton_to_stars_rate = 200.0
    settings.require_ton_rate_for_sales = True
    return settings


@pytest.mark.asyncio
async def test_list_dry_run_does_not_update_db(db_session, sample_gift):
    settings = make_settings()
    tg = AsyncMock()
    gift_repo = GiftRepository(db_session)
    pricing = PricingService(None, settings)
    svc = ListingService(None, gift_repo, pricing, settings)

    await svc.list_gift(sample_gift, 10.0, dry_run=True)
    await db_session.commit()

    updated = await gift_repo.get_by_id(sample_gift.id)
    assert updated.is_for_sale is False
    assert updated.resale_price_ton is None
    tg.invoke.assert_not_called()


@pytest.mark.asyncio
async def test_delist_dry_run_does_not_update_db(db_session, sample_gift):
    settings = make_settings()
    gift_repo = GiftRepository(db_session)
    await gift_repo.update_sale_status(sample_gift.id, True, 2000, 10.0)
    await db_session.commit()

    svc = ListingService(None, gift_repo, PricingService(None, settings), settings)
    await svc.delist_gift(sample_gift, dry_run=True)
    await db_session.commit()

    updated = await gift_repo.get_by_id(sample_gift.id)
    assert updated.is_for_sale is True
    assert updated.resale_price_ton == 10.0
