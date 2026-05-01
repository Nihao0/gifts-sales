"""
TelegramClientContext — async context manager wrapping Telethon's TelegramClient.

Usage:
    async with TelegramClientContext(settings) as tg:
        result = await tg.invoke(SomeRequest(...))
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote

from telethon import TelegramClient
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.tlobject import TLRequest
from telethon.tl.types import InputBotAppShortName, InputPeerSelf, User

import app.client.mtproto  # noqa: F401 — registers custom TL types
from app.client.mtproto.types import (
    SavedStarGift,
    SavedStarGiftsResponse,
    StarGiftMeta,
)
from app.config.settings import Settings
from app.utils.logging import get_logger

log = get_logger(__name__)


class TelegramClientContext:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: TelegramClient | None = None

    async def __aenter__(self) -> "TelegramClientContext":
        s = self._settings
        if s.api_id is None or s.api_hash is None:
            raise RuntimeError("API_ID and API_HASH are required for Telegram operations.")
        self._client = TelegramClient(
            s.session_name,
            s.api_id,
            s.api_hash,
            flood_sleep_threshold=s.flood_sleep_threshold,
        )
        await self._client.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.disconnect()

    @property
    def raw(self) -> TelegramClient:
        assert self._client is not None, "Client not connected"
        return self._client

    async def start(self, phone: str | None = None, password: str | None = None) -> None:
        assert self._client is not None
        if phone is None and self._settings.phone is None:
            raise RuntimeError("PHONE is required for login.")
        await self._client.start(
            phone=phone or self._settings.phone,
            password=password or self._settings.session_password,
        )

    async def get_me(self) -> User:
        assert self._client is not None
        me = await self._client.get_me()
        return me

    async def invoke(self, request: TLRequest) -> Any:
        """Send a raw MTProto request. FloodWaitError propagates to caller."""
        assert self._client is not None
        log.debug("mtproto.invoke", request=type(request).__name__)
        return await self._client(request)

    # ------------------------------------------------------------------
    # High-level gift scanning helpers
    # ------------------------------------------------------------------

    async def get_saved_star_gifts(
        self,
        limit: int = 100,
        peer=None,
    ) -> list[SavedStarGift]:
        """
        Paginate through payments.getSavedStarGifts and return all saved gifts.
        Falls back to parsing the raw response dict when Telethon returns an
        unknown TL type (TypeNotFoundError).
        """
        from app.client.mtproto.functions import GetSavedStarGiftsRequest

        gifts: list[SavedStarGift] = []
        offset = ""

        while True:
            try:
                raw = await self.invoke(
                    GetSavedStarGiftsRequest(
                        peer=peer or InputPeerSelf(),
                        offset=offset,
                        limit=limit,
                    )
                )
                parsed = _parse_saved_gifts_response(raw)
            except Exception as exc:
                # If Telethon can't parse the response, it may return a raw
                # bytes-like object or raise TypeNotFoundError.  In production,
                # the server returns a valid response — log and bail.
                log.error("get_saved_star_gifts.error", error=str(exc))
                raise

            gifts.extend(parsed.gifts)
            log.debug(
                "get_saved_star_gifts.page",
                count=len(parsed.gifts),
                total_so_far=len(gifts),
                has_more=bool(parsed.next_offset),
            )

            if not parsed.next_offset:
                break
            offset = parsed.next_offset

        return gifts

    async def resolve_input_peer(self, username_or_id: str):
        """Resolve a username/link/id into an InputPeer accepted by raw MTProto requests."""
        assert self._client is not None
        entity = await self._client.get_entity(username_or_id)
        return await self._client.get_input_entity(entity)

    async def get_portals_auth_data(self) -> str:
        """Return Telegram Mini App auth data for Portals Market."""
        assert self._client is not None
        bot_entity = await self._client.get_entity("portals")
        bot = await self._client.get_input_entity(bot_entity)
        web_view = await self.invoke(
            RequestAppWebViewRequest(
                peer=bot,
                app=InputBotAppShortName(bot_id=bot, short_name="market"),
                platform="desktop",
            )
        )
        url = getattr(web_view, "url", "")
        if "tgWebAppData=" not in url:
            raise RuntimeError("Portals webview did not return tgWebAppData.")
        init_data = unquote(url.split("tgWebAppData=", 1)[1].split("&tgWebAppVersion", 1)[0])
        return f"tma {init_data}"


# ---------------------------------------------------------------------------
# Response parsing helpers
# ---------------------------------------------------------------------------

def _parse_saved_gifts_response(raw) -> SavedStarGiftsResponse:
    """
    Convert the raw Telethon response object into our typed SavedStarGiftsResponse.

    Telethon may return either a proper TLObject (if its layer supports the type)
    or a generic object with attribute access.  We handle both by reading
    attributes defensively.
    """
    gifts = []
    raw_gifts = getattr(raw, "gifts", []) or []
    for item in raw_gifts:
        gift_obj = getattr(item, "gift", None)
        meta = _parse_star_gift_meta(gift_obj)

        saved_id = getattr(item, "saved_id", None) or 0
        msg_id = getattr(item, "msg_id", None) or 0

        # Resale price: may be a StarsAmount object or an int attribute
        resale_obj = getattr(item, "resale_stars", None) or getattr(item, "resale_price", None)
        resale_stars: int | None = None
        if resale_obj is not None:
            resale_stars = getattr(resale_obj, "amount", None) or int(resale_obj)

        saved = SavedStarGift(
            saved_id=saved_id,
            msg_id=msg_id,
            date=getattr(item, "date", 0),
            gift=meta,
            from_id=_peer_id(getattr(item, "from_id", None)),
            name_hidden=getattr(item, "name_hidden", False),
            unsaved=getattr(item, "unsaved", False),
            can_upgrade=getattr(item, "can_upgrade", False),
            resale_stars=resale_stars,
            raw=_to_dict(item),
        )
        gifts.append(saved)

    return SavedStarGiftsResponse(
        count=getattr(raw, "count", len(gifts)),
        gifts=gifts,
        next_offset=getattr(raw, "next_offset", "") or "",
        users=getattr(raw, "users", []) or [],
    )


def _parse_star_gift_meta(gift_obj) -> StarGiftMeta:
    if gift_obj is None:
        return StarGiftMeta(gift_id=0)
    gift_id = getattr(gift_obj, "id", 0) or 0
    title = getattr(gift_obj, "title", None)
    slug = getattr(gift_obj, "slug", None)
    avail = getattr(gift_obj, "availability_remains", None)
    total = getattr(gift_obj, "availability_total", None)
    stars = getattr(gift_obj, "stars", None)
    return StarGiftMeta(
        gift_id=gift_id,
        title=title,
        slug=slug,
        availability_issued=avail,
        availability_total=total,
        stars=stars,
    )


def _peer_id(peer) -> int | None:
    if peer is None:
        return None
    return getattr(peer, "user_id", None) or getattr(peer, "channel_id", None)


def _to_dict(obj) -> dict:
    try:
        return json.loads(obj.to_json()) if hasattr(obj, "to_json") else {}
    except Exception:
        return {}
