from __future__ import annotations

import json
import re
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import certifi


PORTALS_MARKET = "portals"
PORTALS_SORTS = {
    "latest": "listed_at desc",
    "price_asc": "price asc",
    "price_desc": "price desc",
    "gift_id_asc": "external_collection_number asc",
    "gift_id_desc": "external_collection_number desc",
    "model_rarity_asc": "model_rarity asc",
    "model_rarity_desc": "model_rarity desc",
}


class PortalsAuthError(RuntimeError):
    pass


class PortalsApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class PortalsListing:
    external_id: str | None
    tg_id: str | None
    gift_name: str
    model: str | None
    backdrop: str | None
    symbol: str | None
    price_ton: float | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class PortalsFloor:
    gift_name: str
    model: str | None = None
    backdrop: str | None = None
    symbol: str | None = None
    floor_price_ton: float | None = None
    listed_count: int | None = None
    raw: dict[str, Any] | None = None


class PortalsClient:
    def __init__(self, base_url: str, auth_data: str | None) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._auth_data = auth_data
        self._collection_ids_by_short_name: dict[str, str] | None = None

    def search(
        self,
        *,
        gift_name: str | None = None,
        model: str | None = None,
        backdrop: str | None = None,
        symbol: str | None = None,
        sort: str = "price_asc",
        offset: int = 0,
        limit: int = 20,
        min_price: int = 0,
        max_price: int = 100000,
    ) -> list[PortalsListing]:
        if sort not in PORTALS_SORTS:
            raise ValueError(f"Unknown sort: {sort}")
        params = [
            f"offset={offset}",
            f"limit={limit}",
            f"sort_by={quote_plus(PORTALS_SORTS[sort])}",
            "status=listed",
        ]
        if max_price < 100000:
            params.extend([f"min_price={min_price}", f"max_price={max_price}"])
        if gift_name:
            collection_id = self.collection_id(gift_name)
            if collection_id:
                params.append(f"collection_ids={quote_plus(collection_id)}")
            else:
                params.append(f"filter_by_collections={quote_plus(_cap(gift_name))}")
        if model:
            params.append(f"filter_by_models={quote_plus(_cap(model))}")
        if backdrop:
            params.append(f"filter_by_backdrops={quote_plus(_cap(backdrop))}")
        if symbol:
            params.append(f"filter_by_symbols={quote_plus(_cap(symbol))}")

        payload = self._get("nfts/search?" + "&".join(params))
        raw_results = payload.get("results", payload) if isinstance(payload, dict) else payload
        if raw_results is None:
            return []
        if not isinstance(raw_results, list):
            raw_results = [raw_results]
        return [_parse_listing(item) for item in raw_results if isinstance(item, dict)]

    def collection_id(self, gift_name: str) -> str | None:
        short_name = _short_name(gift_name)
        if self._collection_ids_by_short_name is None:
            self._collection_ids_by_short_name = self._load_collection_ids()
        return self._collection_ids_by_short_name.get(short_name)

    def _load_collection_ids(self) -> dict[str, str]:
        payload = self._get("collections?offset=0&limit=500")
        raw_collections = payload.get("collections", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_collections, list):
            return {}

        result: dict[str, str] = {}
        for item in raw_collections:
            if not isinstance(item, dict):
                continue
            collection_id = _string_or_none(item.get("id"))
            short_name = _string_or_none(item.get("short_name") or item.get("name"))
            if collection_id and short_name:
                result[_short_name(short_name)] = collection_id
        return result

    def collection_floors(self) -> list[PortalsFloor]:
        payload = self._get("collections/floors")
        floors = payload.get("floorPrices", payload) if isinstance(payload, dict) else payload
        return _parse_collection_floors(floors)

    def filter_floors(self, gift_name: str) -> list[PortalsFloor]:
        short_name = _short_name(gift_name)
        payload = self._get(f"collections/filters?short_names={quote_plus(short_name)}")
        raw = payload
        if isinstance(payload, dict):
            collections = payload.get("collections")
            floor_prices = payload.get("floor_prices") or payload.get("floorPrices")
            if isinstance(collections, dict) and short_name in collections:
                raw = collections[short_name]
            elif isinstance(floor_prices, dict) and short_name in floor_prices:
                raw = floor_prices[short_name]
        return _parse_attribute_floors(gift_name, raw)

    def _get(self, path: str) -> Any:
        if not self._auth_data:
            raise PortalsAuthError("PORTALS_AUTH_DATA is required for Portals API requests.")
        request = Request(
            self._base_url + path,
            headers={
                "Authorization": self._auth_data,
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://portals-market.com",
                "Referer": "https://portals-market.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
                ),
            },
            method="GET",
        )
        try:
            context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(request, timeout=20, context=context) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise PortalsApiError(f"Portals API returned {exc.code}: {body}") from exc


def _parse_listing(item: dict[str, Any]) -> PortalsListing:
    return PortalsListing(
        external_id=_string_or_none(item.get("id")),
        tg_id=_string_or_none(item.get("tg_id") or item.get("external_collection_number")),
        gift_name=_string_or_none(item.get("name") or item.get("collection_name")) or "-",
        model=_string_or_none(item.get("model")),
        backdrop=_string_or_none(item.get("backdrop")),
        symbol=_string_or_none(item.get("symbol")),
        price_ton=_float_or_none(item.get("price")),
        raw=item,
    )


def _parse_collection_floors(raw: Any) -> list[PortalsFloor]:
    if not raw:
        return []
    floors: list[PortalsFloor] = []
    if isinstance(raw, dict):
        for name, value in raw.items():
            floors.append(
                PortalsFloor(
                    gift_name=str(name),
                    floor_price_ton=_floor_value(value),
                    raw=value if isinstance(value, dict) else {"value": value},
                )
            )
        return floors
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                floors.append(
                    PortalsFloor(
                        gift_name=_string_or_none(
                            item.get("name") or item.get("short_name") or item.get("collection")
                        )
                        or "-",
                        floor_price_ton=_floor_value(item),
                        listed_count=_int_or_none(item.get("count") or item.get("listed_count")),
                        raw=item,
                    )
                )
    return floors


def _parse_attribute_floors(gift_name: str, raw: Any) -> list[PortalsFloor]:
    if not isinstance(raw, dict):
        return []
    floors: list[PortalsFloor] = []
    for key, field in (("models", "model"), ("backdrops", "backdrop"), ("symbols", "symbol")):
        values = raw.get(key) or {}
        if isinstance(values, dict):
            iterable = values.items()
        elif isinstance(values, list):
            iterable = [
                (
                    item.get("name") if isinstance(item, dict) else str(item),
                    item,
                )
                for item in values
            ]
        else:
            continue
        for name, value in iterable:
            kwargs = {
                "gift_name": gift_name,
                "floor_price_ton": _floor_value(value),
                "raw": value if isinstance(value, dict) else {"value": value},
            }
            kwargs[field] = str(name)
            floors.append(PortalsFloor(**kwargs))
    return floors


def _floor_value(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("floor", "floor_price", "price", "min_price"):
            parsed = _float_or_none(value.get(key))
            if parsed is not None:
                return parsed
        return None
    return _float_or_none(value)


def _cap(text: str) -> str:
    words = re.findall(r"\w+(?:'\w+)?", text)
    for word in words:
        if word:
            text = text.replace(word, word[0].upper() + word[1:], 1)
    return text


def _short_name(gift_name: str) -> str:
    return gift_name.replace(" ", "").replace("'", "").replace("’", "").replace("-", "").lower()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
