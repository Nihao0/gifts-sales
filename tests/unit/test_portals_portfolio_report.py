import json
from datetime import datetime, timezone

from app.cli.markets import (
    _best_floor_match,
    _build_portfolio_report_rows,
    _gift_attributes,
    _latest_collection_floor_index,
    _latest_floor_index,
    _portfolio_row_dict,
)
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


def test_portfolio_report_row_explains_all_floor_signals():
    now = datetime.now(timezone.utc)
    gift = Gift(
        id=7,
        telegram_gift_id="7",
        owner_peer="@visible",
        title="Desk Calendar",
        slug="DeskCalendar-273465",
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
    floors = [
        MarketFloor(
            id=1,
            market="portals",
            gift_name="Desk Calendar",
            floor_price_ton=7.0,
            captured_at=now,
        ),
        MarketFloor(
            id=2,
            market="portals",
            gift_name="Desk Calendar",
            model="Crunch Time",
            floor_price_ton=12.0,
            captured_at=now,
        ),
        MarketFloor(
            id=3,
            market="portals",
            gift_name="Desk Calendar",
            symbol="Royal Crown",
            floor_price_ton=30.0,
            captured_at=now,
        ),
        MarketFloor(
            id=4,
            market="portals",
            gift_name="Desk Calendar",
            backdrop="Pistachio",
            floor_price_ton=5.0,
            captured_at=now,
        ),
    ]

    rows = _build_portfolio_report_rows(
        [gift],
        _latest_collection_floor_index(floors),
        _latest_floor_index(floors),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.gift_id == 7
    assert row.title == "Desk Calendar"
    assert row.collection_floor_ton == 7.0
    assert row.model_floor_ton == 12.0
    assert row.symbol_floor_ton == 30.0
    assert row.backdrop_floor_ton == 5.0
    assert row.best_signal == "symbol"
    assert row.best_floor_ton == 30.0
    assert row.confidence == "medium"
    assert row.action == "check exact listing"


def test_portfolio_report_can_include_unmatched_gifts():
    gift = Gift(
        id=8,
        telegram_gift_id="8",
        owner_peer="@visible",
        title="Fresh Socks",
        slug="FreshSocks-1",
        raw_json=json.dumps(
            {"gift": {"attributes": [{"_": "StarGiftAttributeModel", "name": "Classic"}]}}
        ),
    )

    assert _build_portfolio_report_rows([gift], {}, {}) == []

    rows = _build_portfolio_report_rows([gift], {}, {}, include_unmatched=True)

    assert len(rows) == 1
    assert rows[0].title == "Fresh Socks"
    assert rows[0].best_signal == "none"
    assert rows[0].confidence == "unknown"
    assert rows[0].action == "sync market data"


def test_portfolio_row_dict_is_export_friendly():
    row = _build_portfolio_report_rows(
        [
            Gift(
                id=8,
                telegram_gift_id="8",
                owner_peer="@visible",
                title="Fresh Socks",
                slug="FreshSocks-1",
                raw_json=json.dumps({"gift": {"attributes": []}}),
            )
        ],
        {},
        {},
        include_unmatched=True,
    )[0]

    data = _portfolio_row_dict(row)

    assert data["gift_id"] == 8
    assert data["title"] == "Fresh Socks"
    assert data["best_signal"] == "none"
