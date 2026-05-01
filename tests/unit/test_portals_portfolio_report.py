import json
from datetime import datetime, timezone

from app.cli.markets import _best_floor_match, _gift_attributes, _latest_floor_index
from app.models.gift import Gift
from app.models.market import MarketFloor


def test_gift_attributes_extracts_unique_gift_traits():
    gift = Gift(
        telegram_gift_id="1",
        owner_peer="@visible",
        raw_json=json.dumps(
            {
                "gift": {
                    "attributes": [
                        {"_": "StarGiftAttributeModel", "name": "Crunch Time"},
                        {"_": "StarGiftAttributePattern", "name": "Royal Crown"},
                        {"_": "StarGiftAttributeBackdrop", "name": "Pistachio"},
                    ]
                }
            }
        ),
    )

    assert _gift_attributes(gift) == {
        "model": "Crunch Time",
        "symbol": "Royal Crown",
        "backdrop": "Pistachio",
    }


def test_best_floor_match_uses_highest_matching_attribute_floor():
    now = datetime.now(timezone.utc)
    floors = [
        MarketFloor(
            id=1,
            market="portals",
            gift_name="Desk Calendar",
            model="Crunch Time",
            floor_price_ton=12.0,
            captured_at=now,
        ),
        MarketFloor(
            id=2,
            market="portals",
            gift_name="Desk Calendar",
            symbol="Royal Crown",
            floor_price_ton=30.0,
            captured_at=now,
        ),
    ]

    best = _best_floor_match(
        "Desk Calendar",
        {"model": "Crunch Time", "symbol": "Royal Crown"},
        _latest_floor_index(floors),
    )

    assert best is not None
    floor, source = best
    assert floor.floor_price_ton == 30.0
    assert source == "symbol"
