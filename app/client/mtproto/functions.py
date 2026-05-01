"""
Hand-written TLRequest subclasses for Telegram Star Gifts MTProto functions.

These are not present in Telethon's generated layer (173), so we implement
_bytes() manually and parse responses via raw binary reading or by
relying on Telethon's generic reader after monkey-patching tlobjects.
"""
from __future__ import annotations

import struct
from typing import Any

from telethon.tl.tlobject import TLObject, TLRequest

from .serialization import pack_int, pack_long, serialize_bytes
from .types import StarsAmount


# ---------------------------------------------------------------------------
# payments.getSavedStarGifts
# TL: payments.getSavedStarGifts#a319e569 flags:# exclude_unsaved:flags.0?true
#       exclude_saved:flags.1?true exclude_unlimited:flags.2?true
#       exclude_unique:flags.4?true sort_by_value:flags.5?true
#       collection_id:flags.6?int exclude_upgradable:flags.7?true
#       exclude_unupgradable:flags.8?true peer:InputPeer offset:string limit:int
#       = payments.SavedStarGifts
# ---------------------------------------------------------------------------

class GetSavedStarGiftsRequest(TLRequest):
    CONSTRUCTOR_ID = 0xA319E569
    SUBCLASS_OF_ID = 0x0

    def __init__(
        self,
        peer: TLObject,
        offset: str = "",
        limit: int = 100,
        exclude_unsaved: bool = False,
        exclude_saved: bool = False,
        exclude_unlimited: bool = False,
        exclude_unique: bool = False,
        sort_by_value: bool = False,
        collection_id: int | None = None,
        exclude_upgradable: bool = False,
        exclude_unupgradable: bool = False,
    ) -> None:
        self.peer = peer
        self.offset = offset
        self.limit = limit
        self.exclude_unsaved = exclude_unsaved
        self.exclude_saved = exclude_saved
        self.exclude_unlimited = exclude_unlimited
        self.exclude_unique = exclude_unique
        self.sort_by_value = sort_by_value
        self.collection_id = collection_id
        self.exclude_upgradable = exclude_upgradable
        self.exclude_unupgradable = exclude_unupgradable

    def _bytes(self) -> bytes:
        flags = 0
        if self.exclude_unsaved:
            flags |= 1 << 0
        if self.exclude_saved:
            flags |= 1 << 1
        if self.exclude_unlimited:
            flags |= 1 << 2
        if self.exclude_unique:
            flags |= 1 << 4
        if self.sort_by_value:
            flags |= 1 << 5
        if self.collection_id is not None:
            flags |= 1 << 6
        if self.exclude_upgradable:
            flags |= 1 << 7
        if self.exclude_unupgradable:
            flags |= 1 << 8
        payload = (
            struct.pack("<I", self.CONSTRUCTOR_ID)
            + pack_int(flags)
        )
        if self.collection_id is not None:
            payload += pack_int(self.collection_id)
        return (
            payload
            + bytes(self.peer)
            + serialize_bytes(self.offset)
            + pack_int(self.limit)
        )

    @staticmethod
    def _read(reader) -> Any:
        # Response is parsed by _parse_saved_star_gifts_response in telegram.py
        return reader.tgread_object()


# ---------------------------------------------------------------------------
# payments.updateStarGiftPrice
# TL: payments.updateStarGiftPrice#edbe6ccb
#       stargift:InputSavedStarGift resell_amount:StarsAmount = Updates
# ---------------------------------------------------------------------------

class UpdateStarGiftPriceRequest(TLRequest):
    CONSTRUCTOR_ID = 0xEDBE6CCB
    SUBCLASS_OF_ID = 0x0

    def __init__(self, stargift: TLObject, resell_amount: StarsAmount) -> None:
        self.stargift = stargift
        self.resell_amount = resell_amount

    def _bytes(self) -> bytes:
        return (
            struct.pack("<I", self.CONSTRUCTOR_ID)
            + bytes(self.stargift)
            + bytes(self.resell_amount)
        )

    @staticmethod
    def _read(reader) -> Any:
        return reader.tgread_object()


# Backwards-compatible import name for older code/tests.
UpdateStarGiftResalePriceRequest = UpdateStarGiftPriceRequest


# ---------------------------------------------------------------------------
# payments.transferStarGift
# TL: payments.transferStarGift#7f18176a
#       stargift:InputSavedStarGift to_id:InputPeer = Updates
# ---------------------------------------------------------------------------

class TransferStarGiftRequest(TLRequest):
    CONSTRUCTOR_ID = 0x7F18176A
    SUBCLASS_OF_ID = 0x0

    def __init__(self, stargift: TLObject, to_id: TLObject) -> None:
        self.stargift = stargift
        self.to_id = to_id

    def _bytes(self) -> bytes:
        return (
            struct.pack("<I", self.CONSTRUCTOR_ID)
            + bytes(self.stargift)
            + bytes(self.to_id)
        )

    @staticmethod
    def _read(reader) -> Any:
        return reader.tgread_object()


# ---------------------------------------------------------------------------
# payments.getStarGiftResaleOptions
# TL: payments.getStarGiftResaleOptions#12c32abe star_gift_id:long
#       = Vector<StarsAmount>
# ---------------------------------------------------------------------------

class GetStarGiftResaleOptionsRequest(TLRequest):
    CONSTRUCTOR_ID = 0x12C32ABE
    SUBCLASS_OF_ID = 0x0

    def __init__(self, star_gift_id: int) -> None:
        self.star_gift_id = star_gift_id

    def _bytes(self) -> bytes:
        return (
            struct.pack("<I", self.CONSTRUCTOR_ID)
            + pack_long(self.star_gift_id)
        )

    @staticmethod
    def _read(reader) -> Any:
        return reader.tgread_object()


# ---------------------------------------------------------------------------
# payments.getUniqueStarGift
# TL: payments.getUniqueStarGift#6a4fa3c8 slug:string = payments.UniqueStarGift
# ---------------------------------------------------------------------------

class GetUniqueStarGiftRequest(TLRequest):
    CONSTRUCTOR_ID = 0x6A4FA3C8
    SUBCLASS_OF_ID = 0x0

    def __init__(self, slug: str) -> None:
        self.slug = slug

    def _bytes(self) -> bytes:
        return (
            struct.pack("<I", self.CONSTRUCTOR_ID)
            + serialize_bytes(self.slug)
        )

    @staticmethod
    def _read(reader) -> Any:
        return reader.tgread_object()
