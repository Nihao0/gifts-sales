import pytest

from app.schemas.market import MarketFloorCreateSchema
from app.storage.market_repo import MarketRepository


@pytest.mark.asyncio
async def test_market_repo_adds_and_lists_latest_floors(db_session):
    repo = MarketRepository(db_session)
    await repo.add_floor(
        MarketFloorCreateSchema(
            market="portals",
            gift_name="Toy Bear",
            model="Wizard",
            floor_price_ton=10.0,
        )
    )
    await db_session.commit()

    floors = await repo.latest_floors(gift_name="Toy Bear")

    assert len(floors) == 1
    assert floors[0].market == "portals"
    assert floors[0].gift_name == "Toy Bear"
    assert floors[0].model == "Wizard"
    assert floors[0].floor_price_ton == 10.0
