"""
Custom TLObject subclasses for Telegram Star Gifts responses.

These types are not present in Telethon's generated layer, so we hand-write
them here and register them via monkey-patch in __init__.py.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

from telethon.tl.tlobject import TLObject

from .serialization import pack_int, pack_long


# ---------------------------------------------------------------------------
# StarsAmount
# TL: starsAmount#73c4a31 amount:long nanos:int = StarsAmount
# ---------------------------------------------------------------------------

class StarsAmount(TLObject):
    CONSTRUCTOR_ID = 0x073C4A31
    SUBCLASS_OF_ID = 0x0

    def __init__(self, amount: int, nanos: int = 0) -> None:
        self.amount = amount
        self.nanos = nanos

    def _bytes(self) -> bytes:
        return (
            struct.pack("<I", self.CONSTRUCTOR_ID)
            + pack_long(self.amount)
            + pack_int(self.nanos)
        )

    @classmethod
    def from_reader(cls, reader) -> "StarsAmount":
        amount = reader.read_long()
        nanos = reader.read_int()
        return cls(amount=amount, nanos=nanos)

    def __repr__(self) -> str:
        return f"StarsAmount(amount={self.amount}, nanos={self.nanos})"


# ---------------------------------------------------------------------------
# InputSavedStarGiftUser
# TL: inputSavedStarGiftUser#69279795 msg_id:int = InputSavedStarGift
# ---------------------------------------------------------------------------

class InputSavedStarGiftUser(TLObject):
    CONSTRUCTOR_ID = 0x69279795
    SUBCLASS_OF_ID = 0x0

    def __init__(self, msg_id: int) -> None:
        self.msg_id = msg_id

    def _bytes(self) -> bytes:
        return (
            struct.pack("<I", self.CONSTRUCTOR_ID)
            + pack_int(self.msg_id)
        )

    @classmethod
    def from_reader(cls, reader):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# StarGift (collectible metadata)
# TL: starGiftUnique#... id:long ...
# We store a simplified representation parsed from the raw saved gift.
# ---------------------------------------------------------------------------

@dataclass
class StarGiftMeta:
    """Parsed metadata from the starGift object inside a savedStarGift."""
    gift_id: int
    title: str | None = None
    slug: str | None = None
    availability_issued: int | None = None
    availability_total: int | None = None
    stars: int | None = None


# ---------------------------------------------------------------------------
# SavedStarGift (parsed entry from getSavedStarGifts)
# ---------------------------------------------------------------------------

@dataclass
class SavedStarGift:
    """Parsed entry from payments.SavedStarGifts.gifts[]."""
    saved_id: int          # unique ID of this saved gift
    msg_id: int            # message ID in the saved gifts inbox
    date: int              # unix timestamp
    gift: StarGiftMeta
    from_id: int | None = None
    name_hidden: bool = False
    unsaved: bool = False
    can_upgrade: bool = False
    transfer_stars: int | None = None
    # Resale fields (flags.10+)
    can_export_at: int | None = None
    resale_stars: int | None = None  # current resale price in stars
    raw: dict = field(default_factory=dict)

    @property
    def is_for_sale(self) -> bool:
        return self.resale_stars is not None and self.resale_stars > 0


# ---------------------------------------------------------------------------
# SavedStarGiftsResponse
# ---------------------------------------------------------------------------

@dataclass
class SavedStarGiftsResponse:
    count: int
    gifts: list[SavedStarGift]
    next_offset: str
    users: list[Any]
