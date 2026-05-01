from unittest.mock import patch

import pytest

from app.markets.portals import PortalsAuthError, PortalsClient


def test_portals_search_requires_auth():
    client = PortalsClient("https://portals-market.com/api", None)

    with pytest.raises(PortalsAuthError):
        client.search(gift_name="Toy Bear")


def test_portals_search_parses_results():
    client = PortalsClient("https://portals-market.com/api", "tma test")

    with patch.object(
        client,
        "_get",
        return_value={
            "results": [
                {
                    "id": "abc",
                    "external_collection_number": 123,
                    "name": "Toy Bear",
                    "model": "Wizard",
                    "backdrop": "Blue",
                    "symbol": "Star",
                    "price": "12.5",
                }
            ]
        },
    ):
        listings = client.search(gift_name="Toy Bear")

    assert len(listings) == 1
    assert listings[0].gift_name == "Toy Bear"
    assert listings[0].model == "Wizard"
    assert listings[0].price_ton == 12.5


def test_portals_filter_floors_parses_attribute_floors():
    client = PortalsClient("https://portals-market.com/api", "tma test")

    with patch.object(
        client,
        "_get",
        return_value={
            "floor_prices": {
                "toybear": {
                    "models": {"Wizard": {"floor": "10"}},
                    "backdrops": {"Blue": {"floor_price": 11}},
                    "symbols": {"Star": 12},
                }
            }
        },
    ):
        floors = client.filter_floors("Toy Bear")

    assert len(floors) == 3
    assert floors[0].gift_name == "Toy Bear"
    assert floors[0].model == "Wizard"
    assert floors[0].floor_price_ton == 10.0
