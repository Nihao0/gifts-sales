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


def test_portals_search_uses_collection_id_when_available():
    client = PortalsClient("https://portals-market.com/api", "tma test")
    calls: list[str] = []

    def fake_get(path: str):
        calls.append(path)
        if path.startswith("collections?"):
            return {
                "collections": [
                    {
                        "id": "fc46d19d-5f25-44c5-8924-5976c2fb790e",
                        "name": "Durov’s Cap",
                        "short_name": "durovscap",
                    }
                ]
            }
        return {"results": []}

    with patch.object(client, "_get", side_effect=fake_get):
        client.search(gift_name="Durov’s Cap", backdrop="Black")

    search_path = calls[-1]
    assert "collection_ids=fc46d19d-5f25-44c5-8924-5976c2fb790e" in search_path
    assert "filter_by_collections" not in search_path
    assert "filter_by_backdrops=Black" in search_path


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


def test_portals_filter_floors_parses_live_collections_shape():
    client = PortalsClient("https://portal-market.com/api", "tma test")

    with patch.object(
        client,
        "_get",
        return_value={
            "collections": {
                "toybear": {
                    "models": [{"name": "Alter Ego", "floor_price": "35", "supply": 14}],
                    "backdrops": [{"name": "Blue", "floor_price": "34"}],
                    "symbols": [{"name": "Star", "floor_price": 42}],
                }
            },
            "collection_floor_price": {"toybear": "34"},
        },
    ):
        floors = client.filter_floors("Toy Bear")

    assert len(floors) == 3
    assert floors[0].model == "Alter Ego"
    assert floors[0].floor_price_ton == 35.0
    assert floors[1].backdrop == "Blue"
    assert floors[2].symbol == "Star"
