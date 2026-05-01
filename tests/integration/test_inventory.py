"""Integration tests for InventoryService with a real in-memory DB."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.client.mtproto.types import SavedStarGift, StarGiftMeta
from app.services.inventory import InventoryService
from app.services.pricing import PricingService
from app.storage.gift_repo import GiftRepository


def make_saved_gift(saved_id: int, title: str = "Test Gift", resale_stars: int | None = None):
    meta = StarGiftMeta(
        gift_id=saved_id * 100,
        title=title,
        slug=f"TestGift-{saved_id}",
        availability_issued=50,
        availability_total=500,
        stars=100,
    )
    return SavedStarGift(
        saved_id=saved_id,
        msg_id=saved_id + 1000,
        date=1700000000,
        gift=meta,
        resale_stars=resale_stars,
        raw={},
    )


@pytest.mark.asyncio
async def test_scan_persists_gifts(db_session, db_session_factory):
    mock_tg = AsyncMock()
    mock_tg.get_saved_star_gifts = AsyncMock(
        return_value=[
            make_saved_gift(1, "Rocket Gift"),
            make_saved_gift(2, "Background Gift", resale_stars=500),
        ]
    )

    mock_settings = MagicMock()
    mock_settings.ton_to_stars_rate = 200.0

    gift_repo = GiftRepository(db_session)
    pricing = PricingService(mock_tg, mock_settings)
    svc = InventoryService(mock_tg, gift_repo, pricing, mock_settings)

    gifts = await svc.scan()
    await db_session.commit()

    assert len(gifts) == 2
    assert gifts[0].title == "Rocket Gift"
    assert gifts[0].is_for_sale is False
    assert gifts[1].title == "Background Gift"
    assert gifts[1].is_for_sale is True
    assert gifts[1].resale_price_stars == 500
    assert gifts[0].owner_peer == "self"


@pytest.mark.asyncio
async def test_scan_upserts_on_rescan(db_session, db_session_factory):
    mock_tg = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.ton_to_stars_rate = 200.0

    gift_repo = GiftRepository(db_session)
    pricing = PricingService(mock_tg, mock_settings)
    svc = InventoryService(mock_tg, gift_repo, pricing, mock_settings)

    # First scan
    mock_tg.get_saved_star_gifts = AsyncMock(return_value=[make_saved_gift(99, "Old Title")])
    await svc.scan()
    await db_session.commit()

    # Second scan — title changed
    mock_tg.get_saved_star_gifts = AsyncMock(return_value=[make_saved_gift(99, "New Title")])
    await svc.scan()
    await db_session.commit()

    all_gifts = await gift_repo.list_all()
    assert len(all_gifts) == 1
    assert all_gifts[0].title == "New Title"


@pytest.mark.asyncio
async def test_scan_visible_peer_uses_owner_namespace(db_session, db_session_factory):
    mock_tg = AsyncMock()
    mock_tg.get_saved_star_gifts = AsyncMock(return_value=[make_saved_gift(1, "Visible Gift")])
    mock_settings = MagicMock()
    mock_settings.ton_to_stars_rate = 200.0

    gift_repo = GiftRepository(db_session)
    pricing = PricingService(mock_tg, mock_settings)
    svc = InventoryService(mock_tg, gift_repo, pricing, mock_settings)

    gifts = await svc.scan(owner_peer="@visible")
    await db_session.commit()

    assert len(gifts) == 1
    assert gifts[0].owner_peer == "@visible"
    assert gifts[0].telegram_gift_id == "@visible:1"


@pytest.mark.asyncio
async def test_scan_empty(db_session, db_session_factory):
    mock_tg = AsyncMock()
    mock_tg.get_saved_star_gifts = AsyncMock(return_value=[])
    mock_settings = MagicMock()
    mock_settings.ton_to_stars_rate = 200.0

    gift_repo = GiftRepository(db_session)
    pricing = PricingService(mock_tg, mock_settings)
    svc = InventoryService(mock_tg, gift_repo, pricing, mock_settings)

    gifts = await svc.scan()
    assert gifts == []
